"""GradeLab pipeline entry: staged (parse → extract → check → validate → report)."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any


def _cred(context: dict) -> dict[str, Any] | None:
    c = context.get("credentials")
    if c is None:
        return None
    if isinstance(c, dict):
        return c
    return None


def _parse_action(submission_dir: Path, ipynb_path: Path) -> bool:
    from llm_notebook_grader.parse_cells import parse_ipynb
    from llm_notebook_grader.data_layout import get_next_revision, add_action_file

    parsed_cells = parse_ipynb(filepath=str(ipynb_path))
    revision = get_next_revision(submission_dir, "parse")
    output_filename = f"parse_{revision}.json"
    output_path = submission_dir / output_filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed_cells, f, indent=2, ensure_ascii=False)
    add_action_file(submission_dir, "parse", output_filename)
    return True


def _grades_from_check_results(results: list[dict]) -> tuple[list[dict], float]:
    tasks_out = []
    marks = []
    for r in results:
        if r.get("failed"):
            tid = str(r.get("task_id", "?"))
            tasks_out.append({
                "task_id": tid,
                "score": 0.0,
                "max_score": 10.0,
                "status": "error",
                "comment": str(r.get("error", "check failed")),
            })
            marks.append(0.0)
            continue
        tid = str(r.get("task_id", "?"))
        mark = float(r.get("mark", 0.0))
        marks.append(mark)
        status = "pass" if mark >= 1.0 else ("partial" if mark > 0 else "fail")
        tasks_out.append({
            "task_id": tid,
            "score": min(1.0, max(0.0, mark)),
            "max_score": 10.0,
            "status": status,
            "comment": r.get("interpretation"),
        })
    total = sum(marks) / len(marks) if marks else 0.0
    return tasks_out, total


def run(context: dict) -> dict:
    student_files = context.get("student_files") or []
    scratch = Path(context["scratch_dir"])
    cred = _cred(context)
    cfg = context.get("config") or {}
    reasoning = cfg.get("reasoning", "standard") or "standard"
    retry = int(cfg.get("retry", 3) or 3)
    debug = bool(cfg.get("debug", False))

    course = "gradelab"
    homework = "hw"
    data_dir = scratch / "data"
    homework_dir = data_dir / course / homework
    homework_dir.mkdir(parents=True, exist_ok=True)

    student_ids = [Path(p).stem for p in student_files]

    if not cred:
        results = []
        for sid in student_ids:
            results.append({
                "student_id": sid,
                "tasks": [{
                    "task_id": "error",
                    "score": 0.0,
                    "max_score": 10.0,
                    "status": "error",
                    "comment": "No inference profile selected for this run",
                }],
                "total_score": 0.0,
                "report": None,
                "metadata": {"reason": "no_credentials"},
            })
        return {"results": results, "metadata": {"reason": "no_inference_profile"}}

    if cred.get("is_dummy"):
        results = []
        for sid in student_ids:
            results.append({
                "student_id": sid,
                "tasks": [{
                    "task_id": "1",
                    "score": 1.0,
                    "max_score": 10.0,
                    "status": "pass",
                    "comment": "Dummy staged pipeline — no API calls",
                }],
                "total_score": 1.0,
                "report": f"Staged dummy report for {sid}\nИтого: 10.0 / 10",
                "metadata": {"dummy": True, "validation_skipped": True},
            })
        return {
            "results": results,
            "metadata": {
                "pipeline": "llm_notebook_staged",
                "dummy": True,
                "validation_skipped": len(student_files) < 2,
            },
        }

    from llm_notebook_grader.task_extraction import extract_tasks_with_model
    from llm_notebook_grader.task_checking import check_tasks_with_model
    from llm_notebook_grader.validation import validate_cross_student
    from llm_notebook_grader.reporting import generate_report
    from llm_notebook_grader.data_layout import add_homework_action, get_latest_action_file

    profile = "gradelab"
    submissions: list[dict] = []
    staged_ok: set[str] = set()

    for p in student_files:
        sid = Path(p).stem
        sub = data_dir / course / "submissions" / sid
        sub.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, sub / "source.ipynb")
        _parse_action(sub, sub / "source.ipynb")

        ok, _ = extract_tasks_with_model(
            submission_dir=sub,
            provider=cred["provider"],
            model=cred["model"],
            api_key=cred["api_key"],
            yc_folder=cred.get("yc_folder"),
            reasoning=reasoning,
            profile=profile,
            debug=debug,
        )
        if not ok:
            continue

        ok_chk, _ = check_tasks_with_model(
            submission_dir=sub,
            provider=cred["provider"],
            model=cred["model"],
            api_key=cred["api_key"],
            yc_folder=cred.get("yc_folder"),
            reasoning=reasoning,
            profile=profile,
            debug=debug,
            retry=retry,
        )
        if not ok_chk:
            continue
        staged_ok.add(sid)
        submissions.append({"course": course, "hash": sid, "homework": homework})

    validation_meta: dict[str, Any] = {"skipped": False}
    if len(student_files) >= 2:
        ok_v, val_result = asyncio.run(
            validate_cross_student(
                submissions=submissions,
                data_dir=data_dir,
                provider=cred["provider"],
                model=cred["model"],
                api_key=cred["api_key"],
                yc_folder=cred.get("yc_folder"),
                reasoning=reasoning,
                profile=profile,
                debug=debug,
            )
        )
        if ok_v and val_result:
            val_result["validation_metadata"]["homework"] = homework
            from llm_notebook_grader.data_layout import get_next_homework_revision

            rev = get_next_homework_revision(homework_dir, "validate", profile)
            out_name = f"validate_{profile}_{rev}.json"
            out_path = homework_dir / out_name
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(val_result, f, indent=2, ensure_ascii=False)
            add_homework_action(homework_dir, "validate", out_name)
            validation_meta = {"skipped": False, "file": out_name}
        else:
            validation_meta = {"skipped": True, "reason": "validate_failed"}
    else:
        validation_meta = {"skipped": True, "reason": "need_at_least_two_students"}

    results = []
    for p in student_files:
        sid = Path(p).stem
        sub = data_dir / course / "submissions" / sid
        if sid not in staged_ok:
            results.append({
                "student_id": sid,
                "tasks": [{
                    "task_id": "error",
                    "score": 0.0,
                    "max_score": 10.0,
                    "status": "error",
                    "comment": "Extract or check stage failed",
                }],
                "total_score": 0.0,
                "report": None,
                "metadata": None,
            })
            continue
        check_file = None
        for name in ("check", "full-check"):
            cf = get_latest_action_file(sub, name)
            if cf and cf.exists():
                check_file = cf
                break

        if not check_file or not check_file.exists():
            results.append({
                "student_id": sid,
                "tasks": [{
                    "task_id": "error",
                    "score": 0.0,
                    "max_score": 10.0,
                    "status": "error",
                    "comment": "No check output",
                }],
                "total_score": 0.0,
                "report": None,
                "metadata": None,
            })
            continue

        with open(check_file, "r", encoding="utf-8") as f:
            chk = json.load(f)
        chk_results = chk["results"] if isinstance(chk, dict) and "results" in chk else chk
        tasks_gl, total = _grades_from_check_results(chk_results if isinstance(chk_results, list) else [])

        ok_r, _ = generate_report(
            submission_dir=sub,
            course=course,
            homework=homework,
            data_dir=data_dir,
            provider=cred["provider"],
            model=cred["model"],
            api_key=cred["api_key"],
            yc_folder=cred.get("yc_folder"),
            reasoning=reasoning,
            profile=profile,
            debug=debug,
        )
        report_text = None
        if ok_r:
            rep = get_latest_action_file(sub, "report")
            if rep and rep.exists():
                report_text = rep.read_text(encoding="utf-8")

        results.append({
            "student_id": sid,
            "tasks": tasks_gl,
            "total_score": total,
            "report": report_text,
            "metadata": {"staged": True},
        })

    return {
        "results": results,
        "metadata": {
            "pipeline": "llm_notebook_staged",
            "validation": validation_meta,
        },
    }
