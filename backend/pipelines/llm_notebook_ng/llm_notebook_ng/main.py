"""GradeLab entry point for llm-notebook-ng.

Stage 0 ingest/safeguard → A structure → B sample reconcile → C rubric
(HQ bootstrap) → D grade → E layered cross-checks → F assemble.

Confidence is a separate axis from the mark; it is carried in
StudentResult.metadata.ng (the TaskResult schema has no confidence field — see
INTERFACE-NOTE.md). Both mark and confidence are ternary {0, 0.5, 1}.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from pathlib import Path
from typing import Any

from llm_notebook_ng import structure
from llm_notebook_ng.cache import load_cache, save_cache
from llm_notebook_ng.grading import grade_task
from llm_notebook_ng.inference import sampling_triple
from llm_notebook_ng.notebook import (
    cells_by_id,
    derive_skeleton,
    find_gold_and_blank,
    parse_notebook,
    slice_cells,
)
from llm_notebook_ng.report import build_report
from llm_notebook_ng.prompts import PROMPT_VERSION
from llm_notebook_ng.rubric import build_rubrics
from llm_notebook_ng.schema import MAX_SCORE, TaskSpec, status_from_mark
from llm_notebook_ng.validation import validate


# ── context helpers ──


def _cred(context: dict) -> dict[str, Any] | None:
    c = context.get("credentials")
    return c if isinstance(c, dict) else None


def _error_results(student_ids: list[str], comment: str, reason: str) -> dict:
    return {
        "results": [
            {
                "student_id": sid,
                "tasks": [
                    {
                        "task_id": "error",
                        "score": 0.0,
                        "max_score": MAX_SCORE,
                        "status": "error",
                        "comment": comment,
                    }
                ],
                "total_score": 0.0,
                "report": None,
                "metadata": {"reason": reason},
            }
            for sid in student_ids
        ],
        "metadata": {"pipeline": "llm_notebook_ng", "reason": reason},
    }


def _dummy_results(student_ids: list[str]) -> dict:
    return {
        "results": [
            {
                "student_id": sid,
                "tasks": [
                    {
                        "task_id": "1",
                        "score": 1.0,
                        "max_score": MAX_SCORE,
                        "status": "pass",
                        "comment": "Dummy profile — no API call",
                    }
                ],
                "total_score": 1.0,
                "report": f"Привет {sid}! (dummy run)\nИтого: 10.0 / 10",
                "metadata": {"dummy": True},
            }
            for sid in student_ids
        ],
        "metadata": {"pipeline": "llm_notebook_ng", "dummy": True},
    }


# ── orchestration ──


async def _run_async(context: dict) -> dict:
    t_start = time.time()
    student_files = context.get("student_files") or []
    scratch = Path(context["scratch_dir"])
    scratch.mkdir(parents=True, exist_ok=True)
    cred = _cred(context)
    cfg = context.get("config") or {}

    student_ids = [Path(p).stem for p in student_files]
    if not student_files:
        return {
            "results": [],
            "metadata": {"pipeline": "llm_notebook_ng", "reason": "no_students"},
        }
    if not cred:
        return _error_results(
            student_ids,
            "No inference profile selected for this run",
            "no_inference_profile",
        )
    if cred.get("is_dummy"):
        return _dummy_results(student_ids)

    effort = str(cfg.get("effort", "normal") or "normal")
    retry = int(cfg.get("retry", 3) or 3)
    concurrency = int(cfg.get("concurrency", 8) or 8)
    # Operator throttle set at the worker/deployment (executor) layer, not in
    # the run config: a hard ceiling on parallel LLM requests. 0 = no ceiling.
    _conc_cap = int(os.environ.get("LLM_NOTEBOOK_NG_MAX_CONCURRENCY", "0") or 0)
    if _conc_cap > 0:
        concurrency = min(concurrency, _conc_cap)
    sample_size = int(cfg.get("sample_size", 5) or 5)
    max_output_chars = int(cfg.get("max_output_chars", 2000) or 2000)
    max_image_dim = int(cfg.get("max_image_dim", 1568) or 1568)
    max_image_bytes = int(
        cfg.get("max_image_bytes", 8 * 1024 * 1024) or 8 * 1024 * 1024
    )
    image_consistency_samples = int(cfg.get("image_consistency_samples", 2) or 2)
    enable_validation = bool(cfg.get("enable_validation", True))
    temperature, seed, top_p = sampling_triple(cfg)
    raw_or = cfg.get("openrouter_provider")
    openrouter_provider = raw_or if isinstance(raw_or, dict) and raw_or else None

    infer = dict(
        provider=cred["provider"],
        model=cred["model"],
        api_key=cred["api_key"],
        yc_folder=cred.get("yc_folder"),
        retry=retry,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider,
    )
    img_kwargs = {
        "max_image_dim": max_image_dim,
        "max_image_bytes": max_image_bytes,
        "max_images": 8,
    }
    sem = asyncio.Semaphore(max(1, concurrency))
    safeguards = {"html_stripped": 0, "outputs_truncated": 0, "images_found": 0}

    # Stage 0 — parse students + resolve gold/blank.
    students: list[tuple[str, list[dict]]] = []
    for p in student_files:
        cells, stats = parse_notebook(p, max_output_chars=max_output_chars)
        for k in safeguards:
            safeguards[k] += stats.get(k, 0)
        students.append((Path(p).stem, cells))
    students.sort(key=lambda x: x[0])
    student_cells = dict(students)

    gold_dir = Path(context.get("gold_dir", ""))
    gold_paths, blank_path = find_gold_and_blank(gold_dir)

    rng = random.Random(seed if seed is not None else 42)
    sample_ids = sorted(
        rng.sample([s for s, _ in students], min(sample_size, len(students)))
    )

    gold_cells: list[dict] = []
    skeleton_aligned_with_gold = False
    if blank_path is not None:
        skeleton_cells, _ = parse_notebook(
            blank_path, max_output_chars=max_output_chars
        )
        if gold_paths:
            gold_cells, _ = parse_notebook(
                gold_paths[0], max_output_chars=max_output_chars
            )
        mode = "blank+gold" if gold_paths else "blank"
    elif gold_paths:
        gold_cells, _ = parse_notebook(gold_paths[0], max_output_chars=max_output_chars)
        skeleton_cells = derive_skeleton(gold_cells)
        skeleton_aligned_with_gold = True
        mode = "gold"
    else:
        # Free-mode: no reference. Skeleton derived from a sampled student.
        base_sid = sample_ids[0] if sample_ids else students[0][0]
        skeleton_cells = derive_skeleton(student_cells[base_sid])
        mode = "free"

    cache = load_cache(scratch)
    fingerprint = (
        f"v{PROMPT_VERSION}|{cred['model']}|{effort}|{mode}|"
        f"{sample_size}|{len(students)}"
    )
    if cache.get("fingerprint") != fingerprint:
        cache = {"fingerprint": fingerprint}

    # Stage A — canonical structure.
    if cache.get("structure"):
        st = cache["structure"]
        specs = [TaskSpec(**s) for s in st["specs"]]
        context_ids = st["context_ids"]
    else:
        extracted = await structure.extract_structure(skeleton_cells, **infer)
        if extracted is None:
            return _error_results(
                student_ids, "Failed to extract task structure", "structure_failed"
            )
        specs, context_ids, _ = extracted
        cache["structure"] = {
            "specs": [vars(s) for s in specs],
            "context_ids": context_ids,
        }
        save_cache(scratch, cache)

    skeleton_index = cells_by_id(skeleton_cells)
    gold_index = cells_by_id(gold_cells)

    # SHARED CONTEXT must be the REAL imports/setup, never the blanked skeleton
    # (otherwise the grader thinks numpy is never imported and penalizes every
    # task). Cell ids are preserved by derive_skeleton, so the same context_ids
    # index back into the real source notebook.
    if mode == "gold":
        context_cells = slice_cells(gold_index, context_ids)
    elif mode == "free":
        base_sid = sample_ids[0] if sample_ids else students[0][0]
        context_cells = slice_cells(cells_by_id(student_cells[base_sid]), context_ids)
    else:  # blank / blank+gold — skeleton IS the real blank notebook
        context_cells = slice_cells(skeleton_index, context_ids)

    student_setup = {
        sid: structure.student_setup_cells(cells, specs)
        for sid, cells in student_cells.items()
    }

    blank_by_task: dict[str, list[dict]] = {}
    gold_by_task: dict[str, list[dict]] = {}
    for s in specs:
        blank_by_task[s.task_id] = slice_cells(skeleton_index, s.skeleton_cell_ids)
        if skeleton_aligned_with_gold:
            gold_by_task[s.task_id] = slice_cells(gold_index, s.skeleton_cell_ids)
        elif gold_cells:
            gold_by_task[s.task_id] = structure.locate_student_task_cells(s, gold_cells)
        else:
            gold_by_task[s.task_id] = []

    # Stage B — sample reconciliation.
    sample_maps = (
        await asyncio.gather(
            *[
                structure.extract_student_tasks(student_cells[sid], **infer)
                for sid in sample_ids
            ]
        )
        if sample_ids
        else []
    )
    drift = structure.reconcile(specs, [m for m in sample_maps if m])

    # Stage C — rubric (HQ bootstrap), cached.
    if cache.get("rubrics"):
        rubrics = cache["rubrics"]
        rubric_meta = cache.get("rubric_meta", {})
    else:
        rubrics, rubric_meta = await build_rubrics(
            specs,
            gold_by_task=gold_by_task,
            blank_by_task=blank_by_task,
            context_cells=context_cells,
            shared_setup=context_cells,
            sample=[(sid, student_cells[sid]) for sid in sample_ids],
            sem=sem,
            effort=effort,
            img_kwargs=img_kwargs,
            **infer,
        )
        cache["rubrics"] = rubrics
        cache["rubric_meta"] = rubric_meta
        save_cache(scratch, cache)

    # Stage D — grade all students × tasks.
    student_task_cells: dict[str, dict[str, list[dict]]] = {}
    results: dict[str, dict[str, dict]] = {}
    cached_grades = cache.get("grades", {})

    async def grade_student(sid: str) -> None:
        cells = student_cells[sid]
        per_task: dict[str, list[dict]] = {}
        if sid in cached_grades:
            results[sid] = {tid: dict(g) for tid, g in cached_grades[sid].items()}
            for s in specs:
                per_task[s.task_id] = structure.locate_student_task_cells(s, cells)
            student_task_cells[sid] = per_task
            return

        async def one(spec: TaskSpec) -> tuple[str, dict]:
            tcells = structure.locate_student_task_cells(spec, cells)
            per_task[spec.task_id] = tcells
            async with sem:
                g = await grade_task(
                    spec,
                    rubrics.get(spec.task_id, {}),
                    context_cells=context_cells,
                    gold_cells=gold_by_task.get(spec.task_id, []),
                    blank_cells=blank_by_task.get(spec.task_id, []),
                    student_cells=tcells,
                    student_setup_cells=student_setup.get(sid),
                    effort=effort,
                    img_kwargs=img_kwargs,
                    **infer,
                )
            return spec.task_id, g

        graded = await asyncio.gather(*[one(s) for s in specs])
        results[sid] = dict(graded)
        student_task_cells[sid] = per_task

    await asyncio.gather(*[grade_student(sid) for sid in student_cells])
    cache["grades"] = results
    save_cache(scratch, cache)

    # Stage E — layered cross-checks.
    if cache.get("validated"):
        val_counts = cache.get("validation_counts", {"cached": True})
    elif enable_validation and len(students) >= 1:
        val_counts = await validate(
            results,
            specs,
            rubrics=rubrics,
            gold_by_task=gold_by_task,
            blank_by_task=blank_by_task,
            context_cells=context_cells,
            student_task_cells=student_task_cells,
            student_setup=student_setup,
            sem=sem,
            effort=effort,
            img_kwargs=img_kwargs,
            image_consistency_samples=image_consistency_samples,
            **infer,
        )
        cache["grades"] = results
        cache["validated"] = True
        cache["validation_counts"] = val_counts
        save_cache(scratch, cache)
    else:
        for tasks in results.values():
            for g in tasks.values():
                g.setdefault("reference_distance", g.get("confidence", 0.0))
                g.setdefault("cross_check_agreement", 1.0)
                g["status"] = status_from_mark(g["mark"], failed=g.get("failed", False))
        val_counts = {"skipped": True}

    # Stage F — assemble GradeLab output.
    out_results = []
    low_conf_index = []
    for sid in sorted(results):
        tasks_out = []
        ng_tasks = {}
        marks = []
        for spec in specs:
            g = results[sid].get(spec.task_id)
            if g is None:
                g = {
                    "task_id": spec.task_id,
                    "mark": 0.0,
                    "confidence": 0.0,
                    "interpretation": "Не оценено",
                    "issues": [],
                    "failed": True,
                    "is_image": spec.expects_image,
                    "manual_review": True,
                    "flags": ["missing_grade"],
                    "reference_distance": 0.0,
                    "cross_check_agreement": 0.0,
                    "approach": "?",
                    "matched_criteria": [],
                    "evidence_cell_ids": [],
                }
            # Infra failures (provider throttling, unparseable) are NOT the
            # student's fault — keep them visible as error/manual_review but
            # exclude them from the grade average.
            if not g.get("failed"):
                marks.append(g["mark"])
            comment = g.get("interpretation", "")
            if g.get("issues"):
                comment = (comment + " | " + "; ".join(g["issues"])).strip(" |")
            if g.get("manual_review"):
                comment = f"[на проверку] {comment}"
            tasks_out.append(
                {
                    "task_id": str(spec.task_id),
                    "score": g["mark"],
                    "max_score": MAX_SCORE,
                    "status": g.get("status")
                    or status_from_mark(g["mark"], failed=g.get("failed", False)),
                    "comment": comment or None,
                }
            )
            ng_tasks[str(spec.task_id)] = {
                "confidence": g.get("confidence", 0.0),
                "reference_distance": g.get(
                    "reference_distance", g.get("confidence", 0.0)
                ),
                "cross_check_agreement": g.get("cross_check_agreement", 1.0),
                "image_boolean": bool(g.get("is_image")),
                "manual_review": bool(g.get("manual_review")),
                "regraded": bool(g.get("regraded")),
                "prior_mark": g.get("prior_mark"),
                "approach": g.get("approach"),
                "matched_criteria": g.get("matched_criteria", []),
                "evidence_cell_ids": g.get("evidence_cell_ids", []),
                "output_type_seen": g.get("output_type_seen"),
                "flags": g.get("flags", []),
            }
            if g.get("confidence", 0.0) <= 0.5 or g.get("manual_review"):
                low_conf_index.append(
                    {
                        "student": sid,
                        "task_id": str(spec.task_id),
                        "mark": g["mark"],
                        "confidence": g.get("confidence", 0.0),
                    }
                )

        total = sum(marks) / len(marks) if marks else 0.0
        conf_vals = [ng_tasks[t]["confidence"] for t in ng_tasks]
        grades_list = [
            results[sid][s.task_id] for s in specs if s.task_id in results[sid]
        ]
        out_results.append(
            {
                "student_id": sid,
                "tasks": tasks_out,
                "total_score": total,
                "report": build_report(sid, grades_list),
                "metadata": {
                    "ng": {
                        "tasks": ng_tasks,
                        "summary": {
                            "confidence_score": (
                                sum(conf_vals) / len(conf_vals) if conf_vals else 0.0
                            ),
                            "low_confidence_count": sum(
                                1 for v in conf_vals if v <= 0.5
                            ),
                            "manual_review_count": sum(
                                1 for t in ng_tasks.values() if t["manual_review"]
                            ),
                            "regraded_count": sum(
                                1 for t in ng_tasks.values() if t["regraded"]
                            ),
                            "graded_task_count": len(marks),
                            "infra_failed_count": len(specs) - len(marks),
                        },
                    }
                },
            }
        )

    pipeline_meta = {
        "pipeline": "llm_notebook_ng",
        "mode": mode,
        "provider": cred["provider"],
        "model": cred["model"],
        "sampling": {"temperature": temperature, "seed": seed, "top_p": top_p},
        "effort": effort,
        "task_count": len(specs),
        "tasks": [
            {
                "task_id": s.task_id,
                "description": s.description,
                "output_type": s.output_type,
            }
            for s in specs
        ],
        "rubric_digest": {
            s.task_id: rubrics.get(s.task_id, {}).get("summary", "") for s in specs
        },
        "rubric": rubric_meta,
        "sample_students": sample_ids,
        "structure": drift,
        "validation": val_counts,
        "safeguards": {
            **safeguards,
            "images_found_total": safeguards.get("images_found", 0),
        },
        "low_confidence": low_conf_index,
        "elapsed_seconds": round(time.time() - t_start, 1),
    }
    return {"results": out_results, "metadata": pipeline_meta}


def run(context: dict) -> dict:
    return asyncio.run(_run_async(context))
