"""Free-standing (no reference notebook) instant grading.

Each student's notebook is analyzed independently:
  Phase 1 — extract task structure from the student's own cells.
  Phase 2 — grade each task standalone (no reference comparison).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from llm_notebook_grader.parse_cells import parse_ipynb_rich
from llm_notebook_grader.instant import (
    _call_llm,
    _cell_stats,
    _cells_by_id,
    _cells_to_anthropic_blocks,
    _cells_to_text,
    _extract_json,
    _generate_report,
    _load_cache,
    _save_cache,
    _slice_cells,
)
from llm_notebook_grader.inference import DEFAULT_SEED, DEFAULT_TEMPERATURE, DEFAULT_TOP_P
from llm_notebook_grader.prompts.free import extract_tasks_free_prompt, grade_task_free_prompt
from llm_notebook_grader.prompts.instant import EFFORT_MODES


async def _extract_task_map_free(
    student_cells: list[dict],
    *,
    provider: str, model: str, api_key: str,
    yc_folder: str | None = None, debug: bool = False, retry: int = 3,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> dict | None:
    text = _cells_to_text(student_cells)
    user_prompt = f"Analyze this student notebook and identify all tasks.\n\n{text}"
    print(f"  Phase 1: extracting task structure (~{len(user_prompt)//1000}K chars)...")
    result_text, _ = await _call_llm(
        provider, model, api_key,
        extract_tasks_free_prompt, user_prompt,
        yc_folder=yc_folder, debug=debug, retry=retry,
        temperature=temperature, seed=seed, top_p=top_p,
        openrouter_provider=openrouter_provider,
        label="extract",
    )
    if result_text is None:
        return None
    extracted = _extract_json(result_text)
    try:
        task_map = json.loads(extracted)
        if not isinstance(task_map, dict) or "tasks" not in task_map:
            print(f"  Bad structure from extract: {type(task_map)}")
            return None
        return task_map
    except json.JSONDecodeError as e:
        print(f"  JSON parse error in extract: {e}")
        return None


async def _grade_task_free(
    task: dict,
    context_cells: list[dict],
    task_cells: list[dict],
    *,
    provider: str, model: str, api_key: str,
    yc_folder: str | None = None, debug: bool = False, retry: int = 3,
    effort: str = "normal",
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> dict | None:
    task_id = task["task_id"]
    desc = task.get("description", "?")

    if not task_cells:
        print(f"    Task {task_id}: no cells found")
        return {
            "task_id": task_id,
            "mark": 0.0,
            "interpretation": "Решение задачи не найдено в тетрадке.",
            "issues": ["Задача не решена или ячейки отсутствуют"],
            "confidence": "high",
        }

    user_content: list = []
    if context_cells:
        user_content.append({"type": "text", "text": f"=== CONTEXT (imports/setup) ===\n{_cells_to_text(context_cells)}\n\n"})
    user_content.append({"type": "text", "text": f"=== TASK {task_id}: {desc} ===\n"})
    user_content.extend(_cells_to_anthropic_blocks(task_cells))

    text_chars = sum(len(b.get("text", "")) for b in user_content if b.get("type") == "text")
    img_count = sum(1 for b in user_content if b.get("type") == "image")
    print(f"    Task {task_id} ({desc[:40]}): {img_count} images, ~{text_chars//1000}K text")

    effort_prefix = EFFORT_MODES.get(effort, EFFORT_MODES["normal"])
    system_prompt = f"{effort_prefix}\n{grade_task_free_prompt}"

    result_text, _ = await _call_llm(
        provider, model, api_key,
        system_prompt, user_content,
        yc_folder=yc_folder, debug=debug, retry=retry,
        temperature=temperature, seed=seed, top_p=top_p,
        openrouter_provider=openrouter_provider,
        label=f"task {task_id}",
    )
    if result_text is None:
        return None
    extracted = _extract_json(result_text)
    try:
        result = json.loads(extracted)
        if isinstance(result, dict):
            result["task_id"] = task_id
            return result
        if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
            result[0]["task_id"] = task_id
            return result[0]
        print(f"    Task {task_id}: unexpected response type {type(result)}")
        return None
    except json.JSONDecodeError as e:
        print(f"    Task {task_id}: JSON parse error: {e}")
        return None


def execute_free_gradelab(
    *,
    student_tuples: list[tuple[str, Path]],
    output_dir: Path,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: str | None,
    effort: str = "normal",
    debug: bool = False,
    retry: int = 3,
    concurrency: int = 8,
    temperature: float = DEFAULT_TEMPERATURE,
    infer_seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> tuple[dict | None, dict[str, list], list[dict], list[str]]:
    return asyncio.run(
        _execute_free_async(
            student_tuples=student_tuples,
            output_dir=output_dir,
            provider=provider,
            model=model,
            api_key=api_key,
            yc_folder=yc_folder,
            effort=effort,
            debug=debug,
            retry=retry,
            concurrency=concurrency,
            temperature=temperature,
            infer_seed=infer_seed,
            top_p=top_p,
            openrouter_provider=openrouter_provider,
        )
    )


async def _execute_free_async(
    *,
    student_tuples: list[tuple[str, Path]],
    output_dir: Path,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: str | None,
    effort: str = "normal",
    debug: bool = False,
    retry: int = 3,
    concurrency: int = 8,
    temperature: float = DEFAULT_TEMPERATURE,
    infer_seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> tuple[dict | None, dict[str, list], list[dict], list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = SimpleNamespace(
        provider=provider, model=model, api_key=api_key,
        yc_folder=yc_folder, debug=debug, retry=retry,
    )
    sem = asyncio.Semaphore(max(1, concurrency))
    cache_lock = asyncio.Lock()

    cache = _load_cache(output_dir)
    if cache.get("effort") != effort:
        cache = {"students": {}, "effort": effort}
    _save_cache(output_dir, cache)

    all_results: dict[str, list] = {}
    low_confidence: list[dict] = []
    failed_students: list[str] = []
    combined_task_map: dict | None = None

    async def grade_one_student(student_name: str, notebook_path: Path) -> None:
        nonlocal combined_task_map

        cached = cache.get("students", {}).get(student_name)
        if cached and cached.get("complete"):
            task_results = cached["results"]
            all_results[student_name] = task_results
            for t in task_results:
                if t.get("confidence") in ("low", "manual-review"):
                    low_confidence.append({
                        "student": student_name,
                        "task_id": t["task_id"],
                        "mark": t.get("mark", 0),
                        "confidence": t.get("confidence"),
                        "interpretation": t.get("interpretation", ""),
                    })
            return

        student_cells = parse_ipynb_rich(filepath=str(notebook_path))
        stats = _cell_stats(student_cells)
        print(f"  [{student_name}] {stats['count']} cells: {stats['types']}")

        cached_tasks: dict = {}
        if cached and "results" in cached:
            for r in cached["results"]:
                cached_tasks[r["task_id"]] = r

        async with sem:
            task_map = await _extract_task_map_free(
                student_cells,
                provider=config.provider, model=config.model, api_key=config.api_key,
                yc_folder=config.yc_folder, debug=config.debug, retry=config.retry,
                temperature=temperature, seed=infer_seed, top_p=top_p,
                openrouter_provider=openrouter_provider,
            )

        if task_map is None:
            print(f"  [{student_name}] task extraction failed")
            failed_students.append(student_name)
            async with cache_lock:
                cache.setdefault("students", {})[student_name] = {"results": [], "complete": False}
                _save_cache(output_dir, cache)
            return

        tasks = task_map["tasks"]
        context_ids = task_map.get("context_cells", [])
        cell_index = _cells_by_id(student_cells)
        context_cells = _slice_cells(cell_index, context_ids)

        async with cache_lock:
            if combined_task_map is None:
                combined_task_map = task_map

        async def grade_one_task(task: dict) -> dict | None:
            task_id = task["task_id"]
            if task_id in cached_tasks:
                return cached_tasks[task_id]
            all_ids = (
                task.get("task_cells", [])
                + task.get("solution_cells", [])
                + task.get("output_cells", [])
            )
            task_cells = _slice_cells(cell_index, all_ids)
            async with sem:
                return await _grade_task_free(
                    task, context_cells, task_cells,
                    provider=config.provider, model=config.model, api_key=config.api_key,
                    yc_folder=config.yc_folder, debug=config.debug, retry=config.retry,
                    effort=effort, temperature=temperature, seed=infer_seed, top_p=top_p,
                    openrouter_provider=openrouter_provider,
                )

        results = await asyncio.gather(*[grade_one_task(t) for t in tasks])
        task_results = [r for r in results if r is not None]

        if not task_results:
            print(f"  [{student_name}] all tasks failed")
            failed_students.append(student_name)
            async with cache_lock:
                cache.setdefault("students", {})[student_name] = {"results": [], "complete": False}
                _save_cache(output_dir, cache)
            return

        for r in task_results:
            if r.get("confidence") in ("low", "manual-review"):
                low_confidence.append({
                    "student": student_name,
                    "task_id": r["task_id"],
                    "mark": r.get("mark", 0),
                    "confidence": r.get("confidence"),
                    "interpretation": r.get("interpretation", ""),
                })

        complete = len(task_results) == len(tasks)
        async with cache_lock:
            cache.setdefault("students", {})[student_name] = {
                "results": task_results,
                "complete": complete,
            }
            _save_cache(output_dir, cache)

        all_results[student_name] = task_results
        report = _generate_report(student_name, task_results)
        report_path = output_dir / f"{student_name}.txt"
        report_path.write_text(report, encoding="utf-8")

    await asyncio.gather(*[grade_one_student(name, path) for name, path in student_tuples])

    summary_path = output_dir / "_summary.json"
    summary_path.write_text(
        json.dumps({
            "task_map": combined_task_map,
            "results": all_results,
            "low_confidence": low_confidence,
            "failed": failed_students,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return combined_task_map, all_results, low_confidence, failed_students
