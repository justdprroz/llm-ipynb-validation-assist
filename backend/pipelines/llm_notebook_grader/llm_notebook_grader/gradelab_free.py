"""GradeLab pipeline entry: free (no reference notebook) grading."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _cred(context: dict) -> dict[str, Any] | None:
    c = context.get("credentials")
    if isinstance(c, dict):
        return c
    return None


def _marks_to_gradelab_tasks(task_results: list[dict]) -> tuple[list[dict], float]:
    tasks_out = []
    for t in task_results:
        tid = str(t.get("task_id", "?"))
        mark = float(t.get("mark", 0.0))
        status = "pass" if mark >= 1.0 else ("partial" if mark > 0 else "fail")
        if t.get("failed"):
            status = "error"
        tasks_out.append({
            "task_id": tid,
            "score": min(1.0, max(0.0, mark)),
            "max_score": 10.0,
            "status": status,
            "comment": t.get("interpretation") or t.get("error"),
        })
    total = (
        sum(float(t.get("mark", 0.0)) for t in task_results) / len(task_results)
        if task_results else 0.0
    )
    return tasks_out, total


def run(context: dict) -> dict:
    """GradeLab free pipeline — no reference notebook required."""
    student_files = context.get("student_files") or []
    scratch = Path(context["scratch_dir"])
    cred = _cred(context)
    student_tuples = [(Path(p).stem, Path(p)) for p in student_files]

    if not cred:
        return {
            "results": [
                {
                    "student_id": sid,
                    "tasks": [{
                        "task_id": "error", "score": 0.0, "max_score": 10.0,
                        "status": "error", "comment": "No inference profile selected for this run",
                    }],
                    "total_score": 0.0, "report": None,
                    "metadata": {"reason": "no_credentials"},
                }
                for sid, _ in student_tuples
            ],
            "metadata": {"reason": "no_inference_profile"},
        }

    if cred.get("is_dummy"):
        return {
            "results": [
                {
                    "student_id": sid,
                    "tasks": [{
                        "task_id": "1", "score": 1.0, "max_score": 10.0,
                        "status": "pass", "comment": "Dummy profile — no API call",
                    }],
                    "total_score": 1.0,
                    "report": f"Привет {sid}! (dummy run)\nИтого: 10.0 / 10",
                    "metadata": {"dummy": True},
                }
                for sid, _ in student_tuples
            ],
            "metadata": {"pipeline": "llm_notebook_free", "dummy": True},
        }

    from llm_notebook_grader.free import execute_free_gradelab
    from llm_notebook_grader.instant import _sampling_triple

    cfg_all = context.get("config") or {}
    effort = cfg_all.get("effort", "normal") or "normal"
    debug = bool(cfg_all.get("debug", False))
    retry = int(cfg_all.get("retry", 3) or 3)
    concurrency = int(cfg_all.get("concurrency", 8) or 8)
    temperature, infer_seed, top_p = _sampling_triple(cfg_all)
    raw_or = cfg_all.get("openrouter_provider")
    openrouter_provider = raw_or if isinstance(raw_or, dict) and len(raw_or) > 0 else None

    task_map, all_results, low_conf, failed = execute_free_gradelab(
        student_tuples=student_tuples,
        output_dir=scratch,
        provider=cred["provider"],
        model=cred["model"],
        api_key=cred["api_key"],
        yc_folder=cred.get("yc_folder"),
        effort=effort,
        debug=debug,
        retry=retry,
        concurrency=concurrency,
        temperature=temperature,
        infer_seed=infer_seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider,
    )

    results = []
    for sid, _ in student_tuples:
        tr = all_results.get(sid, [])
        if not tr:
            results.append({
                "student_id": sid,
                "tasks": [{
                    "task_id": "error", "score": 0.0, "max_score": 10.0,
                    "status": "error", "comment": "Task extraction or grading failed",
                }],
                "total_score": 0.0, "report": None,
                "metadata": {"failed": True},
            })
            continue
        tasks_gl, total = _marks_to_gradelab_tasks(tr)
        report_path = scratch / f"{sid}.txt"
        report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else None
        results.append({
            "student_id": sid,
            "tasks": tasks_gl,
            "total_score": total,
            "report": report_text,
            "metadata": {"failed": sid in failed},
        })

    # Normalize: all successful students get the same task set; fill missing with 0/fail.
    all_task_ids: set[str] = set()
    for r in results:
        for t in r["tasks"]:
            if t["task_id"] != "error":
                all_task_ids.add(t["task_id"])

    if all_task_ids:
        def _sort_key(tid: str) -> tuple:
            return (int(tid),) if tid.isdigit() else (float("inf"), tid)

        for r in results:
            existing = {t["task_id"] for t in r["tasks"]}
            for tid in all_task_ids:
                if tid not in existing:
                    r["tasks"].append({
                        "task_id": tid,
                        "score": 0.0,
                        "max_score": 10.0,
                        "status": "fail",
                        "comment": "Задача не найдена в тетрадке студента",
                    })
            r["tasks"].sort(key=lambda t: _sort_key(t["task_id"]))
            non_error = [t for t in r["tasks"] if t["task_id"] != "error"]
            if non_error:
                r["total_score"] = sum(t["score"] for t in non_error) / len(non_error)

    return {
        "results": results,
        "metadata": {
            "pipeline": "llm_notebook_free",
            "low_confidence": low_conf,
            "failed_students": failed,
        },
    }
