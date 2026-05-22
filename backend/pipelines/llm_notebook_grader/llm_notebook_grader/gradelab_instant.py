"""GradeLab pipeline entry: instant (reference-based) grading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _cred(context: dict) -> dict[str, Any] | None:
    c = context.get("credentials")
    if c is None:
        return None
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
        if task_results
        else 0.0
    )
    return tasks_out, total


def run(context: dict) -> dict:
    """GradeLab instant pipeline."""
    gold_dir = Path(context["gold_dir"])
    student_files = context.get("student_files") or []
    scratch = Path(context["scratch_dir"])
    cred = _cred(context)

    gold_notebooks = sorted(gold_dir.glob("*.ipynb"))
    if not gold_notebooks:
        return {
            "results": [
                {
                    "student_id": Path(p).stem,
                    "tasks": [{
                        "task_id": "error",
                        "score": 0.0,
                        "max_score": 10.0,
                        "status": "error",
                        "comment": "No reference notebook in gold_dir",
                    }],
                    "total_score": 0.0,
                    "report": None,
                    "metadata": None,
                }
                for p in student_files
            ],
            "metadata": {"error": "no_gold_notebook"},
        }

    reference_path = gold_notebooks[0]
    student_tuples = [(Path(p).stem, Path(p)) for p in student_files]

    if not cred:
        results = []
        for sid, _ in student_tuples:
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
        for sid, _ in student_tuples:
            results.append({
                "student_id": sid,
                "tasks": [{
                    "task_id": "1",
                    "score": 1.0,
                    "max_score": 10.0,
                    "status": "pass",
                    "comment": "Dummy profile — no API call",
                }],
                "total_score": 1.0,
                "report": f"Привет {sid}! (dummy run)\nИтого: 10.0 / 10",
                "metadata": {"dummy": True},
            })
        return {
            "results": results,
            "metadata": {"pipeline": "llm_notebook_instant", "dummy": True},
        }

    from llm_notebook_grader.instant import execute_instant_gradelab, _sampling_triple

    effort = (context.get("config") or {}).get("effort", "normal") or "normal"
    debug = bool((context.get("config") or {}).get("debug", False))
    retry = int((context.get("config") or {}).get("retry", 3) or 3)
    concurrency = int((context.get("config") or {}).get("concurrency", 8) or 8)
    cfg_all = context.get("config") or {}
    temperature, infer_seed, top_p = _sampling_triple(cfg_all)
    raw_or = cfg_all.get("openrouter_provider")
    openrouter_provider = raw_or if isinstance(raw_or, dict) and len(raw_or) > 0 else None

    task_map, all_results, low_conf, failed = execute_instant_gradelab(
        reference_path=reference_path,
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

    if task_map is None:
        return {
            "results": [
                {
                    "student_id": sid,
                    "tasks": [{
                        "task_id": "error",
                        "score": 0.0,
                        "max_score": 10.0,
                        "status": "error",
                        "comment": "Failed to extract task structure from reference",
                    }],
                    "total_score": 0.0,
                    "report": None,
                    "metadata": None,
                }
                for sid, _ in student_tuples
            ],
            "metadata": {"error": "task_map_failed"},
        }

    results = []
    for sid, _ in student_tuples:
        tr = all_results.get(sid, [])
        tasks_gl, total = _marks_to_gradelab_tasks(tr)
        report_path = scratch / f"{sid}.txt"
        report_text = None
        if report_path.exists():
            report_text = report_path.read_text(encoding="utf-8")
        results.append({
            "student_id": sid,
            "tasks": tasks_gl,
            "total_score": total,
            "report": report_text,
            "metadata": {"failed": sid in failed},
        })

    return {
        "results": results,
        "metadata": {
            "pipeline": "llm_notebook_instant",
            "low_confidence": low_conf,
            "failed_students": failed,
        },
    }
