"""Run lifecycle (MongoDB)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi import BackgroundTasks, HTTPException

from app.config import get_settings
from app.mongo_repo import (
    pipeline_get,
    run_get,
    run_insert,
    run_list,
    run_results_for_run,
    run_results_insert_many,
    run_update,
    viewer_get,
    viewer_upsert,
)
from app.executor_docker import pipeline_image_for_run, run_pipeline_via_docker, should_use_docker
from app.schemas import (
    CompareEntry,
    CompareResponse,
    InferenceCredentials,
    RunContext,
    RunCreate,
    RunRead,
    ViewerAdjustmentPayload,
    ViewerAdjustmentResponse,
)
from app.services import llm_proxy_client as inference_profile_svc
from app.services.realm_materialize import materialize_homework
from app.pipeline_run_config import merge_pipeline_run_config
from app.services.pipeline_runner import parse_pipeline_stdout, run_pipeline_subprocess


def run_doc_to_read(run_doc: dict, pl_doc: dict | None, hw_doc: dict | None, ip_doc: dict | None) -> RunRead:
    def pname():
        if pl_doc:
            return pl_doc.get("name")
        return run_doc.get("pipeline_name_snapshot")

    def hname():
        return hw_doc.get("name") if hw_doc else None

    return RunRead(
        id=run_doc["_id"],
        pipeline_id=run_doc.get("pipeline_id"),
        homework_id=run_doc["homework_id"],
        pipeline_name=pname(),
        homework_name=hname(),
        inference_profile_id=run_doc.get("inference_profile_id"),
        inference_profile_name=ip_doc.get("name") if ip_doc else None,
        inference_provider=ip_doc.get("provider") if ip_doc else None,
        inference_model=ip_doc.get("model") if ip_doc else None,
        inference_is_dummy=bool(ip_doc.get("is_dummy")) if ip_doc else None,
        status=run_doc["status"],
        created_at=run_doc.get("created_at"),
        started_at=run_doc.get("started_at"),
        finished_at=run_doc.get("finished_at"),
        error_message=run_doc.get("error_message"),
        run_metadata=run_doc.get("run_metadata"),
        pipeline_config=run_doc.get("pipeline_config"),
    )


def create_run(run_create: RunCreate, background_tasks: BackgroundTasks) -> RunRead:
    from app.mongo_store import get_mongo_db

    db = get_mongo_db()
    if run_create.pipeline_id:
        pl = pipeline_get(run_create.pipeline_id)
    elif run_create.pipeline_name and run_create.pipeline_version:
        pl = db.pipelines.find_one(
            {"name": run_create.pipeline_name, "version": run_create.pipeline_version}
        )
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide pipeline_id or both pipeline_name and pipeline_version",
        )
    if pl is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if pl.get("status") != "installed":
        raise HTTPException(status_code=422, detail=f"Pipeline status is '{pl.get('status')}', must be 'installed'")

    hw = db.homeworks.find_one({"_id": run_create.homework_id})
    if hw is None:
        raise HTTPException(status_code=404, detail="Homework not found")

    inference_profile_id = run_create.inference_profile_id
    if inference_profile_id:
        inference_profile_svc.get_profile(inference_profile_id)

    run_id = str(uuid.uuid4())
    now = datetime.utcnow()
    settings = get_settings()
    doc = {
        "_id": run_id,
        "pipeline_id": pl["_id"],
        "pipeline_name_snapshot": pl.get("name"),
        "pipeline_version_snapshot": pl.get("version"),
        "homework_id": run_create.homework_id,
        "inference_profile_id": inference_profile_id,
        "status": "queued" if settings.RUN_EXECUTOR == "arq" else "pending",
        "created_at": now,
        "retry_count": 0,
        "max_retries": 5,
    }
    if run_create.pipeline_config is not None:
        doc["pipeline_config"] = run_create.pipeline_config
    run_insert(doc)
    if settings.RUN_EXECUTOR == "arq":
        from app.queue_util import enqueue_execute_run

        background_tasks.add_task(enqueue_execute_run, run_id)
    else:
        background_tasks.add_task(execute_run, run_id)
    ip = None
    if inference_profile_id:
        ip = db.inference_profiles.find_one({"_id": inference_profile_id})
    return run_doc_to_read(doc, pl, hw, ip)


def execute_run(run_id: str) -> None:
    from app.mongo_store import get_mongo_db

    settings = get_settings()
    dbm = get_mongo_db()
    try:
        run = run_get(run_id)
        if run is None:
            return
        run_update(run_id, {"status": "running", "started_at": datetime.utcnow()})

        pl = pipeline_get(run["pipeline_id"]) if run.get("pipeline_id") else None
        if pl is None:
            run_update(
                run_id,
                {
                    "status": "failed",
                    "error_message": "Pipeline was removed or is no longer available before execution could complete.",
                    "finished_at": datetime.utcnow(),
                },
            )
            return

        hw = dbm.homeworks.find_one({"_id": run["homework_id"]})
        if not hw:
            run_update(
                run_id,
                {"status": "failed", "error_message": "Homework missing", "finished_at": datetime.utcnow()},
            )
            return

        scratch_dir = settings.RUNS_DIR / run_id / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        homework_scratch = scratch_dir / "homework"
        try:
            homework_dir, students_dir, student_files = materialize_homework(
                run["homework_id"], homework_scratch
            )
        except Exception as mat_exc:
            run_update(
                run_id,
                {
                    "status": "failed",
                    "error_message": f"Failed to materialize homework: {mat_exc}",
                    "finished_at": datetime.utcnow(),
                },
            )
            return
        gold_dir = homework_dir / "gold"

        resolved_ip = None
        creds = None
        if run.get("inference_profile_id"):
            resolved_ip = inference_profile_svc.get_profile(run["inference_profile_id"])
            if settings.LLMPROXY_URL:
                creds = InferenceCredentials(
                    provider="llm_proxy",
                    model=resolved_ip.model,
                    api_key=settings.LLMPROXY_SERVICE_TOKEN or "",
                    yc_folder=resolved_ip.yc_folder,
                    profile_id=run["inference_profile_id"],
                    profile_name=resolved_ip.name,
                    is_dummy=bool(resolved_ip.is_dummy),
                )
            else:
                creds = inference_profile_svc.profile_to_credentials(resolved_ip)

        user_pc = run.get("pipeline_config")
        if isinstance(user_pc, str):
            user_pc = json.loads(user_pc)
        run_config = merge_pipeline_run_config(user_pc if isinstance(user_pc, dict) else None)
        if resolved_ip is not None:
            for key in ("temperature", "top_p", "seed", "effort", "max_tokens", "openrouter_provider"):
                val = getattr(resolved_ip, key, None)
                if val is not None:
                    run_config[key] = val
        context = RunContext(
            run_id=run_id,
            homework_dir=str(homework_dir),
            students_dir=str(students_dir),
            gold_dir=str(gold_dir),
            student_files=student_files,
            scratch_dir=str(scratch_dir),
            config=run_config,
            credentials=creds,
        )

        ctx_path = scratch_dir / "run_context.json"
        ctx_path.write_text(context.model_dump_json())

        venv_python = settings.PIPELINE_VENVS_DIR / pl["name"] / "bin" / "python"
        cmd = [
            str(venv_python),
            "-m",
            "gradelab_runner",
            "--context",
            str(ctx_path),
            "--entry-module",
            pl["entry_module"],
            "--entry-function",
            pl["entry_function"],
        ]

        extra_env: dict[str, str] = {}
        if settings.LLMPROXY_URL and run.get("inference_profile_id"):
            extra_env["LLMPROXY_URL"] = settings.LLMPROXY_URL
            extra_env["LLMPROXY_SERVICE_TOKEN"] = settings.LLMPROXY_SERVICE_TOKEN or ""
            extra_env["GRADELAB_INFERENCE_PROFILE_ID"] = run["inference_profile_id"]

        # Worker/deployment-layer throttle knobs: set on the executor service,
        # forwarded into the spawned pipeline container so rate control lives in
        # infra config, not pipeline code.
        for _k in (
            "LLM_NOTEBOOK_NG_MAX_CONCURRENCY",
            "LLM_NOTEBOOK_NG_MAX_RPS",
            "LLM_NOTEBOOK_NG_LOG_REQUESTS",
        ):
            _v = os.environ.get(_k)
            if _v:
                extra_env[_k] = _v

        img = pl.get("runner_image") or pipeline_image_for_run()
        if should_use_docker() and img:
            result = run_pipeline_via_docker(
                image=img,
                venv_python=venv_python,
                context_path=ctx_path,
                entry_module=pl["entry_module"],
                entry_function=pl["entry_function"],
                run_id=run_id,
                extra_env=extra_env,
            )
        else:
            result = run_pipeline_subprocess(cmd, extra_env=extra_env or None)

        if result.returncode != 0:
            raise RuntimeError(
                f"Pipeline subprocess exited with code {result.returncode} "
                "(stderr was streamed to server logs)"
            )

        output = parse_pipeline_stdout(result.stdout)
        rdocs = []
        for student_result in output.results:
            rdocs.append(
                {
                    "_id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "student_id": student_result.student_id,
                    "total_score": student_result.total_score,
                    "tasks_json": json.dumps([t.model_dump() for t in student_result.tasks]),
                    "report": student_result.report,
                    "result_metadata": json.dumps(student_result.metadata)
                    if student_result.metadata is not None
                    else None,
                }
            )
        run_results_insert_many(rdocs)
        run_update(
            run_id,
            {
                "status": "completed",
                "finished_at": datetime.utcnow(),
                "run_metadata": output.metadata,
            },
        )
    except Exception as exc:
        try:
            run_update(
                run_id,
                {"status": "failed", "error_message": str(exc), "finished_at": datetime.utcnow()},
            )
        except Exception:
            pass


def list_runs(
    pipeline_id: str | None = None,
    homework_id: str | None = None,
    status: str | None = None,
) -> list[RunRead]:
    from app.mongo_store import get_mongo_db

    dbm = get_mongo_db()
    out: list[RunRead] = []
    for r in run_list(pipeline_id=pipeline_id, homework_id=homework_id, status=status):
        pl = pipeline_get(r["pipeline_id"]) if r.get("pipeline_id") else None
        hw = dbm.homeworks.find_one({"_id": r["homework_id"]})
        ip = None
        if r.get("inference_profile_id"):
            ip = dbm.inference_profiles.find_one({"_id": r["inference_profile_id"]})
        out.append(run_doc_to_read(r, pl, hw, ip))
    return out


def get_run(run_id: str) -> RunRead:
    from app.mongo_store import get_mongo_db

    r = run_get(run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Run not found")
    dbm = get_mongo_db()
    pl = pipeline_get(r["pipeline_id"]) if r.get("pipeline_id") else None
    hw = dbm.homeworks.find_one({"_id": r["homework_id"]})
    ip = None
    if r.get("inference_profile_id"):
        ip = dbm.inference_profiles.find_one({"_id": r["inference_profile_id"]})
    return run_doc_to_read(r, pl, hw, ip)


def get_run_results(run_id: str) -> list[SimpleNamespace]:
    get_run(run_id)
    out = []
    for row in run_results_for_run(run_id):
        tasks_json = row.get("tasks_json")
        if tasks_json is None and isinstance(row.get("tasks"), list):
            tasks_json = json.dumps(row["tasks"])
        if tasks_json is None:
            tasks_json = "[]"
        meta_s = row.get("result_metadata")
        if meta_s is None and row.get("metadata") is not None:
            meta_s = json.dumps(row["metadata"])
        out.append(
            SimpleNamespace(
                id=row["_id"],
                run_id=run_id,
                student_id=row["student_id"],
                total_score=row["total_score"],
                tasks_json=tasks_json,
                report=row.get("report"),
                result_metadata=meta_s,
            )
        )
    return out


def get_viewer_adjustments(run_id: str) -> ViewerAdjustmentResponse:
    get_run(run_id)
    row = viewer_get(run_id)
    if row is None:
        return ViewerAdjustmentResponse(payload=ViewerAdjustmentPayload(), updated_at=None)
    try:
        data = json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError):
        return ViewerAdjustmentResponse(payload=ViewerAdjustmentPayload(), updated_at=row.get("updated_at"))
    try:
        payload = ViewerAdjustmentPayload.model_validate(data)
    except Exception:
        payload = ViewerAdjustmentPayload()
    return ViewerAdjustmentResponse(payload=payload, updated_at=row.get("updated_at"))


def put_viewer_adjustments(run_id: str, payload: ViewerAdjustmentPayload) -> ViewerAdjustmentResponse:
    get_run(run_id)
    now = datetime.utcnow()
    viewer_upsert(run_id, json.dumps(payload.model_dump()), now)
    return ViewerAdjustmentResponse(payload=payload, updated_at=now)


def compare_runs(run_ids: list[str]) -> dict:
    if len(run_ids) != 2:
        raise HTTPException(status_code=422, detail="Exactly two run_ids are required")
    run_a = get_run(run_ids[0])
    run_b = get_run(run_ids[1])
    results_a = {rr.student_id: rr for rr in get_run_results(run_a.id)}
    results_b = {rr.student_id: rr for rr in get_run_results(run_b.id)}
    all_students = sorted(set(results_a.keys()) | set(results_b.keys()))
    entries: list[CompareEntry] = []
    for student_id in all_students:
        a = results_a.get(student_id)
        b = results_b.get(student_id)
        a_tasks = json.loads(a.tasks_json) if a else []
        b_tasks = json.loads(b.tasks_json) if b else []
        entries.append(
            CompareEntry(
                student_id=student_id,
                run_a_score=a.total_score if a else None,
                run_b_score=b.total_score if b else None,
                run_a_tasks=a_tasks,
                run_b_tasks=b_tasks,
            )
        )
    return CompareResponse(run_a=run_a, run_b=run_b, entries=entries).model_dump()
