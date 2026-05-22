"""Stage A/B: one canonical task map for the whole cohort + sample reconcile.

The skeleton-derived task map is authoritative (the consistency anchor). The
sample is used only to detect structural drift and to locate each student's
cells per task at grade time.
"""

from __future__ import annotations

from llm_notebook_ng import prompts
from llm_notebook_ng.inference import call_llm
from llm_notebook_ng.jsonio import loads
from llm_notebook_ng.notebook import cells_by_id, slice_cells
from llm_notebook_ng.schema import TaskSpec


async def _extract(
    system: str,
    user: str,
    *,
    provider,
    model,
    api_key,
    yc_folder,
    retry,
    temperature,
    seed,
    top_p,
    openrouter_provider,
    label,
) -> dict | None:
    text = await call_llm(
        provider,
        model,
        api_key,
        system,
        user,
        yc_folder=yc_folder,
        retry=retry,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider,
        label=label,
    )
    parsed = loads(text)
    if isinstance(parsed, dict) and isinstance(parsed.get("tasks"), list):
        return parsed
    return None


def _match_text(skeleton_cells: list[dict], task_cell_ids: list[int]) -> str:
    index = cells_by_id(skeleton_cells)
    return " ".join(
        c.get("content", "")
        for c in slice_cells(index, task_cell_ids)
        if c.get("type") == "md"
    ).strip()


async def extract_structure(
    skeleton_cells: list[dict],
    *,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: str | None,
    retry: int,
    temperature: float,
    seed: int | None,
    top_p: float,
    openrouter_provider: dict | None,
) -> tuple[list[TaskSpec], list[int], dict] | None:
    raw = await _extract(
        prompts.STRUCTURE_SYSTEM,
        prompts.structure_user(skeleton_cells),
        provider=provider,
        model=model,
        api_key=api_key,
        yc_folder=yc_folder,
        retry=retry,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider,
        label="structure",
    )
    if raw is None:
        return None

    specs: list[TaskSpec] = []
    for t in raw["tasks"]:
        tid = str(t.get("task_id", len(specs) + 1))
        task_cells = [c for c in t.get("task_cells", []) if isinstance(c, int)]
        specs.append(
            TaskSpec(
                task_id=tid,
                description=str(t.get("description", "")).strip() or f"Task {tid}",
                output_type=str(t.get("output_type", "none")),
                skeleton_cell_ids=(
                    task_cells
                    + [c for c in t.get("solution_cells", []) if isinstance(c, int)]
                    + [c for c in t.get("output_cells", []) if isinstance(c, int)]
                ),
                match_text=_match_text(skeleton_cells, task_cells)
                or str(t.get("description", "")),
            )
        )
    context_ids = [c for c in raw.get("context_cells", []) if isinstance(c, int)]
    return specs, context_ids, raw


async def extract_student_tasks(
    student_cells: list[dict],
    *,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: str | None,
    retry: int,
    temperature: float,
    seed: int | None,
    top_p: float,
    openrouter_provider: dict | None,
) -> dict | None:
    return await _extract(
        prompts.STRUCTURE_STUDENT_SYSTEM,
        prompts.student_structure_user(student_cells),
        provider=provider,
        model=model,
        api_key=api_key,
        yc_folder=yc_folder,
        retry=retry,
        temperature=temperature,
        seed=seed,
        top_p=top_p,
        openrouter_provider=openrouter_provider,
        label="structure(student)",
    )


def reconcile(specs: list[TaskSpec], sample_maps: list[dict]) -> dict:
    """Report drift between the canonical map and what students actually wrote."""
    counts = [len(m.get("tasks", [])) for m in sample_maps if m]
    canonical = len(specs)
    drift = [n for n in counts if n != canonical]
    return {
        "canonical_task_count": canonical,
        "sample_task_counts": counts,
        "structural_drift": bool(drift),
        "samples_used": len(counts),
    }


def locate_student_task_cells(spec: TaskSpec, student_cells: list[dict]) -> list[dict]:
    """Word-overlap heuristic: find the student's markdown header for this task
    and take everything up to the next markdown cell."""
    ref_words = set(spec.match_text.lower().split())
    if not ref_words:
        return student_cells

    best_idx, best_overlap = -1, 0
    for i, c in enumerate(student_cells):
        if c.get("type") != "md":
            continue
        overlap = len(ref_words & set(c.get("content", "").lower().split()))
        if overlap > best_overlap:
            best_idx, best_overlap = i, overlap

    if best_idx < 0 or best_overlap < 3:
        return []

    result = [student_cells[best_idx]]
    for c in student_cells[best_idx + 1 :]:
        if c.get("type") == "md":
            break
        result.append(c)
    return result


def student_setup_cells(student_cells: list[dict], specs: list[TaskSpec]) -> list[dict]:
    """Shared preamble: everything before the first located task cell (imports,
    data loading). Falls back to leading code cells if no task is located."""
    first: int | None = None
    for spec in specs:
        for c in locate_student_task_cells(spec, student_cells):
            cid = c.get("cell_id")
            if cid is not None and (first is None or cid < first):
                first = cid
    if first is None:
        return [c for c in student_cells if c.get("type") == "code"][:3]
    return [c for c in student_cells if c.get("cell_id", 1 << 30) < first]
