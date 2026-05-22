"""Stage E: layered cross-checks.

- cohort outlier detection → targeted re-grade with cohort context
- low-confidence non-image tasks → targeted re-grade
- image tasks → self-consistency (independent second sample)

Final confidence = min(reference-distance confidence, cross-check agreement):
reference-distance is primary, downgraded when checks disagree (Hybrid).
"""

from __future__ import annotations

import asyncio
import statistics
from collections import Counter

from llm_notebook_ng.grading import grade_task
from llm_notebook_ng.schema import TaskSpec, status_from_mark


def _agreement(old: float, new: float) -> float:
    diff = abs(old - new)
    if diff == 0.0:
        return 1.0
    if diff <= 0.5:
        return 0.5
    return 0.0


def _cohort_note(marks: list[float]) -> str:
    dist = ", ".join(f"{m}×{n}" for m, n in sorted(Counter(marks).items()))
    return f"Cohort marks for this task: {dist}; median={statistics.median(marks)}."


def _finalize(g: dict, *, reference_distance: float, agreement: float) -> None:
    g["reference_distance"] = reference_distance
    g["cross_check_agreement"] = agreement
    if not g.get("is_image"):
        g["confidence"] = min(reference_distance, agreement)
    g["status"] = status_from_mark(g["mark"], failed=g.get("failed", False))


async def validate(
    results: dict[str, dict[str, dict]],
    specs: list[TaskSpec],
    *,
    rubrics: dict[str, dict],
    gold_by_task: dict[str, list[dict]],
    blank_by_task: dict[str, list[dict]],
    context_cells: list[dict],
    student_task_cells: dict[str, dict[str, list[dict]]],
    student_setup: dict[str, list[dict]] | None = None,
    sem: asyncio.Semaphore,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: str | None,
    effort: str,
    retry: int,
    temperature: float,
    seed: int | None,
    top_p: float,
    openrouter_provider: dict | None,
    img_kwargs: dict,
    image_consistency_samples: int = 2,
) -> dict:
    spec_by_id = {s.task_id: s for s in specs}
    counts = {"outliers": 0, "low_confidence": 0, "image_checks": 0, "regrades": 0}

    # 1. cohort outliers
    cohort_notes: dict[str, str] = {}
    outliers: set[tuple[str, str]] = set()
    for spec in specs:
        marks = [
            results[sid][spec.task_id]["mark"]
            for sid in results
            if spec.task_id in results[sid]
            and not results[sid][spec.task_id].get("failed")
            and "not_solved" not in results[sid][spec.task_id].get("flags", [])
        ]
        if len(marks) < 3:
            continue
        med = statistics.median(marks)
        note = _cohort_note(marks)
        for sid in results:
            g = results[sid].get(spec.task_id)
            if not g or g.get("failed") or "not_solved" in g.get("flags", []):
                continue
            if abs(g["mark"] - med) >= 1.0:
                outliers.add((sid, spec.task_id))
                cohort_notes[f"{sid}|{spec.task_id}"] = note

    async def regrade(sid: str, tid: str, *, cohort: str | None) -> None:
        spec = spec_by_id[tid]
        prior = dict(results[sid][tid])
        async with sem:
            new = await grade_task(
                spec,
                rubrics.get(tid, {}),
                context_cells=context_cells,
                gold_cells=gold_by_task.get(tid, []),
                blank_cells=blank_by_task.get(tid, []),
                student_cells=student_task_cells.get(sid, {}).get(tid, []),
                student_setup_cells=(student_setup or {}).get(sid),
                provider=provider,
                model=model,
                api_key=api_key,
                yc_folder=yc_folder,
                effort="strict",
                retry=retry,
                temperature=temperature,
                seed=seed,
                top_p=top_p,
                openrouter_provider=openrouter_provider,
                img_kwargs=img_kwargs,
                regrade=True,
                prior=prior,
                cohort_note=cohort,
            )
        counts["regrades"] += 1
        if new.get("failed"):
            _finalize(
                results[sid][tid],
                reference_distance=prior.get("confidence", 0.0),
                agreement=0.5,
            )
            return
        agreement = _agreement(prior["mark"], new["mark"])
        new["prior_mark"] = prior["mark"]
        new["regraded"] = True
        new["flags"] = list(
            dict.fromkeys(prior.get("flags", []) + new.get("flags", []))
        )
        results[sid][tid] = new
        _finalize(new, reference_distance=new["confidence"], agreement=agreement)

    async def image_check(sid: str, tid: str) -> None:
        spec = spec_by_id[tid]
        base = results[sid][tid]
        samples = []
        for k in range(max(0, image_consistency_samples - 1)):
            alt_seed = None if seed is None else seed + 101 + k
            async with sem:
                s = await grade_task(
                    spec,
                    rubrics.get(tid, {}),
                    context_cells=context_cells,
                    gold_cells=gold_by_task.get(tid, []),
                    blank_cells=blank_by_task.get(tid, []),
                    student_cells=student_task_cells.get(sid, {}).get(tid, []),
                    student_setup_cells=(student_setup or {}).get(sid),
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    yc_folder=yc_folder,
                    effort=effort,
                    retry=retry,
                    temperature=temperature,
                    seed=alt_seed,
                    top_p=top_p,
                    openrouter_provider=openrouter_provider,
                    img_kwargs=img_kwargs,
                )
            counts["regrades"] += 1
            if not s.get("failed"):
                samples.append(s["mark"])
        if samples and any(m != base["mark"] for m in samples):
            base["mark"] = min(base["mark"], 0.5)
            base["confidence"] = 0.0
            base["manual_review"] = True
            base["flags"] = list(
                dict.fromkeys(base.get("flags", []) + ["image_inconsistent"])
            )
            _finalize(base, reference_distance=0.0, agreement=0.0)
        else:
            _finalize(base, reference_distance=base["confidence"], agreement=1.0)

    jobs = []
    for sid, tasks in results.items():
        for tid, g in tasks.items():
            if g.get("failed") or "not_solved" in g.get("flags", []):
                _finalize(g, reference_distance=g.get("confidence", 0.0), agreement=1.0)
                continue
            if g.get("is_image"):
                counts["image_checks"] += 1
                jobs.append(image_check(sid, tid))
                continue
            if (sid, tid) in outliers:
                counts["outliers"] += 1
                jobs.append(regrade(sid, tid, cohort=cohort_notes.get(f"{sid}|{tid}")))
            elif g["confidence"] <= 0.5:
                counts["low_confidence"] += 1
                jobs.append(regrade(sid, tid, cohort=None))
            else:
                _finalize(g, reference_distance=g["confidence"], agreement=1.0)

    if jobs:
        await asyncio.gather(*jobs)
    return counts
