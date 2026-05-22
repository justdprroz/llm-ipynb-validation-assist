"""Stage C: HQ-bootstrap rubric synthesis.

A provisional pass grades the sample against a gold-anchored auto-rubric; the
clearest results become exemplars; one LLM call per task then synthesizes the
final rubric from gold + blank + exemplars. The rubric is reused verbatim for
every student — this is the cross-notebook consistency anchor.
"""

from __future__ import annotations

import asyncio

from llm_notebook_ng import prompts
from llm_notebook_ng.grading import grade_task
from llm_notebook_ng.inference import call_llm
from llm_notebook_ng.jsonio import loads
from llm_notebook_ng.notebook import cells_to_text
from llm_notebook_ng.schema import TaskSpec
from llm_notebook_ng.structure import (
    locate_student_task_cells,
    student_setup_cells,
)


def auto_rubric(spec: TaskSpec) -> dict:
    return {
        "task_id": spec.task_id,
        "summary": spec.description,
        "criteria_full": [
            "Solution follows the gold approach and produces the expected result"
        ],
        "criteria_partial": [
            "Mostly correct but with minor issues or an unusual but defensible approach"
        ],
        "criteria_zero": [
            "Not solved, wrong approach, runtime errors, or no meaningful output"
        ],
        "confidence_full": "Work is clearly above the blank skeleton and "
        "comparable to the gold solution",
        "confidence_low": "Work is indistinguishable from the blank, unrelated, "
        "or otherwise ungradeable",
        "common_mistakes": [],
    }


async def build_rubrics(
    specs: list[TaskSpec],
    *,
    gold_by_task: dict[str, list[dict]],
    blank_by_task: dict[str, list[dict]],
    context_cells: list[dict],
    shared_setup: list[dict] | None = None,
    sample: list[tuple[str, list[dict]]],
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
) -> tuple[dict[str, dict], dict]:
    provisional = {s.task_id: auto_rubric(s) for s in specs}

    async def grade_sample(
        sid: str, cells: list[dict], spec: TaskSpec
    ) -> tuple[str, dict]:
        task_cells = locate_student_task_cells(spec, cells)
        async with sem:
            g = await grade_task(
                spec,
                provisional[spec.task_id],
                context_cells=context_cells,
                gold_cells=gold_by_task.get(spec.task_id, []),
                blank_cells=blank_by_task.get(spec.task_id, []),
                student_cells=task_cells,
                student_setup_cells=student_setup_cells(cells, specs),
                provider=provider,
                model=model,
                api_key=api_key,
                yc_folder=yc_folder,
                effort=effort,
                retry=retry,
                temperature=temperature,
                seed=seed,
                top_p=top_p,
                openrouter_provider=openrouter_provider,
                img_kwargs=img_kwargs,
            )
        return sid, g

    jobs = [grade_sample(sid, cells, s) for sid, cells in sample for s in specs]
    graded = await asyncio.gather(*jobs) if jobs else []

    pos: dict[str, list[str]] = {s.task_id: [] for s in specs}
    neg: dict[str, list[str]] = {s.task_id: [] for s in specs}
    sample_cells = dict(sample)
    for sid, g in graded:
        tid = str(g["task_id"])
        spec = next((s for s in specs if s.task_id == tid), None)
        if spec is None:
            continue
        snippet = cells_to_text(locate_student_task_cells(spec, sample_cells[sid]))[
            :1500
        ]
        if not snippet:
            continue
        if g["mark"] == 1.0 and g["confidence"] == 1.0 and len(pos[tid]) < 3:
            pos[tid].append(snippet)
        elif g["mark"] == 0.0 and g["confidence"] >= 0.5 and len(neg[tid]) < 3:
            neg[tid].append(snippet)

    async def synth(spec: TaskSpec) -> tuple[str, dict]:
        user = prompts.rubric_user(
            spec.description,
            gold_by_task.get(spec.task_id, []),
            blank_by_task.get(spec.task_id, []),
            pos[spec.task_id],
            neg[spec.task_id],
            shared_setup=shared_setup,
        )
        async with sem:
            text = await call_llm(
                provider,
                model,
                api_key,
                prompts.RUBRIC_SYSTEM,
                user,
                yc_folder=yc_folder,
                retry=retry,
                temperature=temperature,
                seed=seed,
                top_p=top_p,
                openrouter_provider=openrouter_provider,
                label=f"rubric task {spec.task_id}",
            )
        parsed = loads(text)
        if isinstance(parsed, dict) and parsed.get("summary"):
            parsed["task_id"] = spec.task_id
            return spec.task_id, parsed
        return spec.task_id, auto_rubric(spec)

    rubrics = dict(await asyncio.gather(*[synth(s) for s in specs]))
    meta = {
        "exemplars": {
            tid: {"positive": len(pos[tid]), "negative": len(neg[tid])} for tid in pos
        },
        "sample_grade_calls": len(graded),
    }
    return rubrics, meta
