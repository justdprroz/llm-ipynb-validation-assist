"""Stage D/E: grade one task against the shared rubric.

The same coroutine drives the provisional bootstrap pass, the main grading pass,
and the validation re-grade (via ``regrade``/``prior``/``cohort_note``).
"""

from __future__ import annotations

from typing import Any

from llm_notebook_ng import prompts
from llm_notebook_ng.inference import EFFORT_MODES, call_llm
from llm_notebook_ng.jsonio import loads
from llm_notebook_ng.schema import TaskSpec, quantize


def _empty(spec: TaskSpec, reason: str) -> dict:
    return {
        "task_id": spec.task_id,
        "mark": 0.0,
        "confidence": 1.0,  # absence is unambiguous; not a manual-review case
        "interpretation": "Решение задачи не найдено в тетрадке.",
        "issues": ["Задача не решена или ячейки отсутствуют"],
        "approach": "missing",
        "matched_criteria": [],
        "evidence_cell_ids": [],
        "output_type_seen": "none",
        "is_image": spec.expects_image,
        "manual_review": False,
        "flags": [reason],
        "failed": False,
        "error": None,
    }


def _failed(spec: TaskSpec, error: str) -> dict:
    return {
        "task_id": spec.task_id,
        "mark": 0.0,
        "confidence": 0.0,
        "interpretation": "Не удалось оценить задачу (ошибка модели).",
        "issues": [error[:200]],
        "approach": "error",
        "matched_criteria": [],
        "evidence_cell_ids": [],
        "output_type_seen": "error",
        "is_image": spec.expects_image,
        "manual_review": True,
        "flags": ["grade_failed"],
        "failed": True,
        "error": error,
    }


def _normalize(spec: TaskSpec, raw: dict, *, has_img: bool) -> dict:
    mark = quantize(raw.get("mark"))
    if has_img:
        confidence = quantize(raw.get("confidence"), allowed=(0.0, 1.0))
    else:
        confidence = quantize(raw.get("confidence"))

    flags: list[str] = list(raw.get("flags") or [])
    manual_review = False
    if has_img and confidence == 0.0:
        # Aggressive image rule: unverifiable visual caps the mark, forces review.
        if mark > 0.5:
            mark = 0.5
            flags.append("image_mark_capped")
        manual_review = True
        flags.append("image_unverified")

    return {
        "task_id": spec.task_id,
        "mark": mark,
        "confidence": confidence,
        "interpretation": str(raw.get("interpretation") or "").strip(),
        "issues": [str(i) for i in (raw.get("issues") or [])],
        "approach": str(raw.get("approach") or "?"),
        "matched_criteria": [str(c) for c in (raw.get("matched_criteria") or [])],
        "evidence_cell_ids": [
            c for c in (raw.get("evidence_cell_ids") or []) if isinstance(c, int)
        ],
        "output_type_seen": str(raw.get("output_type_seen") or "none"),
        "is_image": has_img,
        "manual_review": manual_review,
        "flags": flags,
        "failed": False,
        "error": None,
    }


async def grade_task(
    spec: TaskSpec,
    rubric: dict,
    *,
    context_cells: list[dict],
    gold_cells: list[dict],
    blank_cells: list[dict],
    student_cells: list[dict],
    student_setup_cells: list[dict] | None = None,
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
    img_kwargs: dict[str, Any],
    regrade: bool = False,
    prior: dict | None = None,
    cohort_note: str | None = None,
) -> dict:
    real_cells = [
        c
        for c in student_cells
        if c.get("type") != "md" or c.get("content", "").strip()
    ]
    if not real_cells:
        return _empty(spec, "not_solved")

    has_img = spec.expects_image or any(c.get("type") == "image" for c in student_cells)
    effort_text = EFFORT_MODES.get(effort, EFFORT_MODES["normal"])
    system = prompts.grade_system(effort_text, is_image=has_img, regrade=regrade)
    user_content = prompts.grade_user(
        rubric=rubric,
        context_cells=context_cells,
        gold_cells=gold_cells,
        blank_cells=blank_cells,
        student_cells=student_cells,
        student_setup_cells=student_setup_cells,
        img_kwargs=img_kwargs,
        prior=prior,
        cohort_note=cohort_note,
    )

    text = await call_llm(
        provider,
        model,
        api_key,
        system,
        user_content,
        yc_folder=yc_folder,
        retry=retry,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider,
        label=f"{'regrade' if regrade else 'grade'} task {spec.task_id}",
    )
    if text is None:
        return _failed(spec, "LLM call failed")

    parsed = loads(text)
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        return _failed(spec, "unparseable grade response")

    return _normalize(spec, parsed, has_img=has_img)
