import asyncio
import csv
import json
import re
import sys
import time
import base64
import io
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from llm_notebook_grader.parse_cells import parse_ipynb_rich
from llm_notebook_grader.inference import (
    DEFAULT_SEED,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    async_anthropic_prompt,
    async_openai_prompt,
    async_universal_prompt,
    DO_ENDPOINT,
    normalize_inference_provider,
    OR_ENDPOINT,
    _normalize_openrouter_model_slug,
)
from llm_notebook_grader.prompts.instant import extract_tasks_prompt, grade_task_prompt, EFFORT_MODES

MAX_IMAGE_DIM = 1568
MAX_OUTPUT_CHARS = 2000  # truncate huge outputs (HTML tables, long prints)


def _sampling_triple(cfg: dict | None) -> tuple[float, int | None, float]:
    """
    Reads ``temperature``, ``seed``, ``top_p`` from GradeLab ``RunContext.config`` (or CLI dict).
    If ``seed`` is JSON ``null``, omit seed on OpenAI-compatible APIs (providers differ).
    """
    c = cfg or {}
    temperature = float(c.get("temperature", DEFAULT_TEMPERATURE))
    top_p = float(c.get("top_p", DEFAULT_TOP_P))
    if "seed" in c:
        s = c["seed"]
        infer_seed = None if s is None else int(s)
    else:
        infer_seed = DEFAULT_SEED
    return temperature, infer_seed, top_p


# ── JSON extraction ──

def _extract_json(text: str) -> str:
    if not text or not text.strip():
        return text

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.DOTALL)

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)

    cleaned = cleaned.strip()

    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1]

    return cleaned


# ── Image resizing ──

def _resize_b64_image(b64_data: str, media_type: str) -> tuple[str, str]:
    raw = base64.b64decode(b64_data)
    img = Image.open(io.BytesIO(raw))
    orig_size = img.size

    if max(img.size) <= MAX_IMAGE_DIM:
        return b64_data, media_type

    img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), Image.LANCZOS)
    buf = io.BytesIO()
    fmt = "PNG" if "png" in media_type else "JPEG"
    img.save(buf, format=fmt)
    new_data = base64.b64encode(buf.getvalue()).decode("ascii")
    print(f"      resized {orig_size} -> {img.size} ({len(b64_data)//1024}KB -> {len(new_data)//1024}KB)")
    return new_data, media_type


# ── Output truncation ──

def _truncate_output(content: str) -> str:
    if len(content) <= MAX_OUTPUT_CHARS:
        return content
    half = MAX_OUTPUT_CHARS // 2
    return content[:half] + f"\n... [truncated {len(content) - MAX_OUTPUT_CHARS} chars] ...\n" + content[-half:]


# ── Cell utilities ──

def _cell_stats(cells: list[dict]) -> dict:
    types = {}
    total_text_chars = 0
    total_image_bytes = 0
    for c in cells:
        t = c.get("type", "?")
        types[t] = types.get(t, 0) + 1
        if t == "image":
            total_image_bytes += len(c.get("data", "")) * 3 // 4
        else:
            total_text_chars += len(c.get("content", ""))
    return {"count": len(cells), "types": types, "text_chars": total_text_chars, "image_bytes": total_image_bytes}


def _cells_by_id(cells: list[dict]) -> dict[int, list[dict]]:
    index = {}
    for c in cells:
        cid = c.get("cell_id")
        if cid is not None:
            index.setdefault(cid, []).append(c)
    return index


def _slice_cells(cell_index: dict[int, list[dict]], cell_ids: list[int]) -> list[dict]:
    result = []
    for cid in cell_ids:
        result.extend(cell_index.get(cid, []))
    return result


def _cells_to_text(cells: list[dict]) -> str:
    lines = []
    for c in cells:
        if c["type"] == "image":
            lines.append(f"{c['cell_id']}: image: [graphical output]")
        elif c["type"] == "output":
            lines.append(f"{c['cell_id']}: output: {_truncate_output(c.get('content', ''))}")
        else:
            lines.append(f"{c['cell_id']}: {c['type']}: {c.get('content', '')}")
    return "\n".join(lines)


def _cells_to_anthropic_blocks(cells: list[dict]) -> list[dict]:
    blocks = []
    text_buffer = []

    for c in cells:
        if c["type"] == "image":
            if text_buffer:
                blocks.append({"type": "text", "text": "\n".join(text_buffer) + "\n"})
                text_buffer = []
            resized_data, resized_type = _resize_b64_image(c["data"], c["media_type"])
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": resized_type, "data": resized_data}
            })
        elif c["type"] == "output":
            text_buffer.append(f"{c['cell_id']}: output: {_truncate_output(c.get('content', ''))}")
        else:
            text_buffer.append(f"{c['cell_id']}: {c['type']}: {c.get('content', '')}")

    if text_buffer:
        blocks.append({"type": "text", "text": "\n".join(text_buffer) + "\n"})

    return blocks


def _blocks_to_text(blocks: list[dict]) -> str:
    parts = []
    for b in blocks:
        if b.get("type") == "text":
            parts.append(b["text"])
        elif b.get("type") == "image":
            parts.append("[image]")
    return "\n".join(parts)


def _anthropic_to_openai_blocks(blocks: list[dict]) -> list[dict]:
    result = []
    for b in blocks:
        if b.get("type") == "text":
            result.append({"type": "text", "text": b["text"]})
        elif b.get("type") == "image":
            src = b["source"]
            data_uri = f"data:{src['media_type']};base64,{src['data']}"
            result.append({"type": "image_url", "image_url": {"url": data_uri}})
    return result


# ── Cache ──

def _load_cache(output_dir: Path) -> dict:
    cache_path = output_dir / "_cache.json"
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"task_map": None, "students": {}}


def _save_cache(output_dir: Path, cache: dict):
    cache_path = output_dir / "_cache.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


# ── LLM dispatch ──

_VISION_PROVIDERS = {"or", "do"}


async def _call_llm(
    provider: str, model: str, api_key: str,
    system: str, user_content,
    *, yc_folder: str | None = None, debug: bool = False, retry: int = 3,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
    label: str = "",
) -> tuple[str | None, dict]:
    last_error = None

    for attempt in range(retry + 1):
        if attempt > 0:
            wait = min(2 ** attempt, 60)
            print(f"    Retry {attempt}/{retry} (waiting {wait}s...)")
            await asyncio.sleep(wait)

        try:
            t0 = time.time()
            is_multimodal = isinstance(user_content, list)
            p = normalize_inference_provider(provider)

            if p == "anthropic":
                messages = [{"role": "user", "content": user_content}]
                result_text, usage, response = await async_anthropic_prompt(
                    model_name=model,
                    api_key=api_key,
                    system=system,
                    messages=messages,
                    temperature=temperature,
                )
            elif is_multimodal and p in _VISION_PROVIDERS:
                openai_blocks = _anthropic_to_openai_blocks(user_content)
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": openai_blocks},
                ]
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                }
                url = OR_ENDPOINT if p == "or" else DO_ENDPOINT
                or_model = _normalize_openrouter_model_slug(model) if p == "or" else model
                result_text, usage, response = await async_openai_prompt(
                    url=url,
                    model_name=or_model,
                    headers=headers,
                    messages=messages,
                    temperature=temperature,
                    seed=seed,
                    top_p=top_p,
                    openrouter_provider=openrouter_provider if p == "or" else None,
                )
            else:
                text = user_content if isinstance(user_content, str) else _blocks_to_text(user_content)
                result_text, usage, response = await async_universal_prompt(
                    provider,
                    prompts=[system, text],
                    model_name=model,
                    api_token=api_key,
                    folder=yc_folder,
                    temperature=temperature,
                    seed=seed,
                    top_p=top_p,
                    openrouter_provider=openrouter_provider,
                )

            elapsed = time.time() - t0
            in_tok = usage.get("input_tokens") or usage.get("prompt_tokens", "?")
            out_tok = usage.get("output_tokens") or usage.get("completion_tokens", "?")
            print(f"    {label} -> {in_tok} in / {out_tok} out, {elapsed:.1f}s")
            return result_text, usage

        except Exception as e:
            last_error = str(e)
            if "rate_limit" in last_error.lower() or "429" in last_error:
                print(f"    Rate limited, backing off...")
            else:
                print(f"    Error: {last_error[:200]}")

    print(f"    Failed after {retry} retries: {last_error[:300]}")
    return None, {}


# ── Phase 1: extract task structure from reference ──

async def _extract_task_map(
    ref_cells: list[dict],
    *, provider: str, model: str, api_key: str,
    yc_folder: str | None = None, debug: bool = False, retry: int = 3,
    temperature: float = DEFAULT_TEMPERATURE,
    seed: int | None = DEFAULT_SEED,
    top_p: float = DEFAULT_TOP_P,
    openrouter_provider: dict[str, Any] | None = None,
) -> dict | None:
    ref_text = _cells_to_text(ref_cells)
    user_prompt = f"Analyze this reference notebook and identify all tasks.\n\n{ref_text}"

    print(f"  Phase 1: extracting task structure (~{len(user_prompt)//1000}K chars, text-only)...")

    result_text, usage = await _call_llm(
        provider, model, api_key,
        extract_tasks_prompt, user_prompt,
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
            print(f"  Bad structure: expected dict with 'tasks' key, got: {type(task_map)}")
            print(f"  Raw (first 300): {result_text[:300]}")
            return None
        return task_map
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        print(f"  Raw (first 500): {result_text[:500]}")
        return None


# ── Phase 2: grade each task individually ──

def _find_student_cells_for_task(
    task: dict,
    ref_index: dict[int, list[dict]],
    student_cells: list[dict],
) -> list[dict]:
    ref_task_cells = _slice_cells(ref_index, task.get("task_cells", []))
    ref_task_text = ""
    for c in ref_task_cells:
        if c["type"] == "md":
            ref_task_text += c.get("content", "")

    if not ref_task_text:
        return student_cells

    best_idx = -1
    best_score = 0
    ref_words = set(ref_task_text.lower().split())

    for i, c in enumerate(student_cells):
        if c["type"] != "md":
            continue
        student_words = set(c.get("content", "").lower().split())
        overlap = len(ref_words & student_words)
        if overlap > best_score:
            best_score = overlap
            best_idx = i

    if best_idx < 0 or best_score < 3:
        return []

    result = [student_cells[best_idx]]
    for c in student_cells[best_idx + 1:]:
        if c["type"] == "md":
            break
        result.append(c)

    return result


async def _grade_single_task(
    task: dict,
    context_cells: list[dict],
    ref_task_cells: list[dict],
    student_task_cells: list[dict],
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

    if not student_task_cells:
        print(f"    Task {task_id}: no matching student cells found")
        return {
            "task_id": task_id,
            "mark": 0.0,
            "interpretation": "Решение задачи не найдено в тетрадке студента.",
            "issues": ["Задача не решена или не найдена"],
            "confidence": "high",
        }

    user_content = []
    if context_cells:
        user_content.append({"type": "text", "text": f"=== SHARED CONTEXT (imports/setup) ===\n{_cells_to_text(context_cells)}\n\n"})

    user_content.append({"type": "text", "text": f"=== REFERENCE SOLUTION for task {task_id}: {desc} ===\n"})
    user_content.extend(_cells_to_anthropic_blocks(ref_task_cells))

    user_content.append({"type": "text", "text": f"\n\n=== STUDENT SOLUTION for task {task_id} ===\n"})
    user_content.extend(_cells_to_anthropic_blocks(student_task_cells))

    img_count = sum(1 for b in user_content if b.get("type") == "image")
    text_chars = sum(len(b.get("text", "")) for b in user_content if b.get("type") == "text")
    print(f"    Task {task_id} ({desc[:40]}): {img_count} images, ~{text_chars//1000}K text")

    effort_prefix = EFFORT_MODES.get(effort, EFFORT_MODES["normal"])
    system_prompt = f"{effort_prefix}\n{grade_task_prompt}"

    result_text, usage = await _call_llm(
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
        print(f"    Raw (first 300): {result_text[:300]}")
        return None
    except json.JSONDecodeError as e:
        print(f"    Task {task_id}: JSON parse error: {e}")
        print(f"    Raw (first 300): {result_text[:300]}")
        return None


# ── Student discovery ──

def discover_students(input_dir: Path) -> list[tuple[str, Path]]:
    students = []
    for entry in sorted(input_dir.iterdir()):
        if not entry.is_dir():
            continue

        notebooks = list(entry.glob("*.ipynb"))
        if not notebooks:
            print(f"  [{entry.name}] no notebook found, skipping")
            continue

        colab = [n for n in notebooks if n.name.startswith("colab_")]
        chosen = colab[0] if colab else notebooks[0]

        if len(notebooks) > 1:
            others = [n.name for n in notebooks if n != chosen]
            print(f"  [{entry.name}] picked {chosen.name} (skipped: {', '.join(others)})")

        students.append((entry.name, chosen))

    return students


# ── Report generation ──

def _generate_report(student_name: str, task_results: list[dict]) -> str:
    total_mark = sum(t.get("mark", 0.0) for t in task_results)
    task_count = len(task_results)
    final_grade = (total_mark / task_count * 10) if task_count > 0 else 0.0

    feedback_lines = []
    for t in task_results:
        mark = t.get("mark", 0.0)
        if mark >= 1.0:
            continue
        issues = t.get("issues", [])
        interpretation = t.get("interpretation", "")
        comment = "; ".join(issues) if issues else interpretation
        feedback_lines.append(f"Задача {t['task_id']} - {mark}: {comment}")

    if final_grade >= 9.0:
        quality = "отличную "
    elif final_grade >= 7.0:
        quality = "хорошую "
    else:
        quality = ""

    lines = [f"Привет {student_name}!", ""]

    if feedback_lines:
        lines.append("Обратная связь:")
        lines.append("")
        lines.extend(feedback_lines)
        lines.append("")

    lines.append(f"Спасибо за проделанную {quality}работу!")
    lines.append("")
    lines.append(f"Итого: {final_grade:.1f} / 10")

    return "\n".join(lines)


# ── CSV grades table ──

def _write_grades_csv(output_dir: Path, tasks: list[dict], all_results: dict):
    csv_path = output_dir / "_grades.csv"
    task_ids = [t["task_id"] for t in tasks]

    header = ["student"] + [f"task_{tid}" for tid in task_ids] + ["total"]

    rows = []
    for student_name, task_results in sorted(all_results.items()):
        marks_by_id = {r["task_id"]: r.get("mark", 0.0) for r in task_results}
        row = [student_name]
        for tid in task_ids:
            row.append(marks_by_id.get(tid, ""))
        total = sum(marks_by_id.get(tid, 0.0) for tid in task_ids)
        count = sum(1 for tid in task_ids if tid in marks_by_id)
        grade = (total / count * 10) if count > 0 else 0.0
        row.append(f"{grade:.1f}")
        rows.append(row)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"Grades CSV: {csv_path}")


# ── Main action ──

def action_instant(args, config):
    asyncio.run(_action_instant_async(args, config))


async def _action_instant_async(args, config):
    reference_path = Path(args.reference)
    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not reference_path.exists():
        print(f"Error: reference notebook not found: {reference_path}")
        return

    if not input_dir.exists():
        print(f"Error: input directory not found: {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    if not config.profile:
        print("Error: profile required for instant action")
        return

    effort = getattr(args, "effort", "normal") or "normal"
    concurrency = max(1, int(getattr(args, "concurrency", 8) or 8))

    temperature, infer_seed, top_p = _sampling_triple({})

    print(f"Provider: {config.provider}, Model: {config.model}")
    print(f"Effort: {effort}")
    print(f"Concurrency: {concurrency}")
    print(f"Sampling: temperature={temperature}, seed={infer_seed}, top_p={top_p}")
    print(f"Reference: {reference_path}")
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print()

    sem = asyncio.Semaphore(concurrency)
    cache_lock = asyncio.Lock()

    # load cache — invalidate if effort changed
    cache = _load_cache(output_dir)
    if cache.get("effort") != effort:
        if cache.get("effort"):
            print(f"  Effort changed ({cache.get('effort')} -> {effort}), clearing cache")
        cache = {"task_map": None, "students": {}, "effort": effort}

    # store paths for adjust
    cache["reference_path"] = str(reference_path)
    cache["input_dir"] = str(input_dir)
    _save_cache(output_dir, cache)

    # parse reference
    print("Parsing reference notebook...")
    ref_cells = parse_ipynb_rich(filepath=str(reference_path))
    stats = _cell_stats(ref_cells)
    print(f"  {stats['count']} cells: {stats['types']}")
    print(f"  ~{stats['text_chars']//1000}K text, ~{stats['image_bytes']//1024}KB images")

    # phase 1: extract task structure from reference (cached)
    print()
    if cache.get("task_map"):
        task_map = cache["task_map"]
        print(f"  Phase 1: using cached task structure")
    else:
        async with sem:
            task_map = await _extract_task_map(
                ref_cells,
                provider=config.provider, model=config.model, api_key=config.api_key,
                yc_folder=config.yc_folder, debug=config.debug, retry=config.retry,
                temperature=temperature, seed=infer_seed, top_p=top_p,
            )

        if task_map is None:
            print("Error: failed to extract task structure from reference")
            return

        async with cache_lock:
            cache["task_map"] = task_map
            _save_cache(output_dir, cache)

    tasks = task_map["tasks"]
    context_ids = task_map.get("context_cells", [])
    print(f"  Found {len(tasks)} tasks, {len(context_ids)} context cells")
    for t in tasks:
        print(f"    Task {t['task_id']}: {t.get('description', '?')[:60]}")

    ref_index = _cells_by_id(ref_cells)
    context_cells = _slice_cells(ref_index, context_ids)

    # discover students
    print()
    print("Discovering students...")
    students = discover_students(input_dir)
    print(f"Found {len(students)} student(s)")

    if not students:
        return

    all_results: dict = {}
    low_confidence: list = []
    failed_students: list = []

    async def grade_one_student(idx: int, student_name: str, notebook_path: Path) -> None:
        print(f"\n[{idx}/{len(students)}] == {student_name} ({notebook_path.name})")

        cached_student = cache.get("students", {}).get(student_name)
        if cached_student and cached_student.get("complete"):
            task_results = cached_student["results"]
            total = sum(t.get("mark", 0.0) for t in task_results)
            grade = (total / len(task_results) * 10) if task_results else 0
            print(f"  CACHED: {len(task_results)} tasks, grade: {grade:.1f}/10")

            all_results[student_name] = task_results
            for t in task_results:
                conf = t.get("confidence", "manual-review")
                if conf in ("low", "manual-review"):
                    low_confidence.append({
                        "student": student_name,
                        "task_id": t["task_id"],
                        "mark": t.get("mark", 0),
                        "confidence": conf,
                        "interpretation": t.get("interpretation", ""),
                    })
            return

        student_cells = parse_ipynb_rich(filepath=str(notebook_path))
        stats = _cell_stats(student_cells)
        print(f"  Parsed: {stats['count']} cells: {stats['types']}")

        cached_tasks: dict = {}
        if cached_student and "results" in cached_student:
            for r in cached_student["results"]:
                cached_tasks[r["task_id"]] = r
            print(f"  Resuming: {len(cached_tasks)} tasks cached")

        async def grade_one_task(task: dict) -> dict | None:
            task_id = task["task_id"]
            all_task_ids = (
                task.get("task_cells", [])
                + task.get("solution_cells", [])
                + task.get("output_cells", [])
            )
            ref_task_cells = _slice_cells(ref_index, all_task_ids)
            student_task_cells = _find_student_cells_for_task(task, ref_index, student_cells)
            async with sem:
                return await _grade_single_task(
                    task, context_cells, ref_task_cells, student_task_cells,
                    provider=config.provider, model=config.model, api_key=config.api_key,
                    yc_folder=config.yc_folder, debug=config.debug, retry=config.retry,
                    effort=effort,
                    temperature=temperature, seed=infer_seed, top_p=top_p,
                )

        fresh_tasks = [t for t in tasks if t["task_id"] not in cached_tasks]
        fresh_results = await asyncio.gather(*[grade_one_task(t) for t in fresh_tasks]) if fresh_tasks else []

        task_results: list = []
        for task in tasks:
            task_id = task["task_id"]
            if task_id in cached_tasks:
                result = cached_tasks[task_id]
                print(f"    Task {task_id}: CACHED mark={result.get('mark', '?')}")
                task_results.append(result)

        for task, result in zip(fresh_tasks, fresh_results):
            task_id = task["task_id"]
            if result is None:
                print(f"    Task {task_id}: FAILED")
                continue
            task_results.append(result)
            conf = result.get("confidence", "?")
            mark = result.get("mark", 0)
            print(f"    Task {task_id} -> mark={mark}, confidence={conf}")
            if conf in ("low", "manual-review"):
                low_confidence.append({
                    "student": student_name,
                    "task_id": result["task_id"],
                    "mark": mark,
                    "confidence": conf,
                    "interpretation": result.get("interpretation", ""),
                })

        if not task_results:
            print(f"  ALL TASKS FAILED")
            failed_students.append(student_name)
            async with cache_lock:
                cache.setdefault("students", {})[student_name] = {
                    "results": task_results,
                    "complete": False,
                }
                _save_cache(output_dir, cache)
            return

        complete = len(task_results) == len(tasks)
        async with cache_lock:
            cache.setdefault("students", {})[student_name] = {
                "results": task_results,
                "complete": complete,
            }
            _save_cache(output_dir, cache)

        all_results[student_name] = task_results

        total = sum(t.get("mark", 0.0) for t in task_results)
        grade = (total / len(task_results) * 10) if task_results else 0
        print(f"  Grade: {grade:.1f}/10 ({len(task_results)}/{len(tasks)} tasks graded)")

        report = _generate_report(student_name, task_results)
        report_path = output_dir / f"{student_name}.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  Report -> {report_path.name}")

    await asyncio.gather(
        *[grade_one_student(i, name, path) for i, (name, path) in enumerate(students, 1)]
    )

    # summary
    print(f"\n{'='*60}")
    print(f"Results: {len(all_results)} graded, {len(failed_students)} failed out of {len(students)}")

    if failed_students:
        print(f"\nFailed:")
        for name in failed_students:
            print(f"  - {name}")

    if low_confidence:
        print(f"\nLow confidence ({len(low_confidence)}):")
        for item in low_confidence:
            print(f"  {item['student']} / Задача {item['task_id']}: "
                  f"mark={item['mark']}, confidence={item['confidence']}")
            print(f"    {item['interpretation']}")

    if all_results:
        _write_grades_csv(output_dir, tasks, all_results)

    summary_path = output_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "task_map": task_map,
            "results": all_results,
            "low_confidence": low_confidence,
            "failed": failed_students,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nSummary: {summary_path}")


def execute_instant_gradelab(
    *,
    reference_path: Path,
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
    """
    GradeLab variant: flat student notebooks. Returns (task_map, all_results, low_confidence, failed_students).

    Sync wrapper that drives the async core via asyncio.run.
    """
    return asyncio.run(
        _execute_instant_gradelab_async(
            reference_path=reference_path,
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


async def _execute_instant_gradelab_async(
    *,
    reference_path: Path,
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

    # Use SimpleNamespace: in a class body, `provider = provider` makes `provider`
    # local for the whole block, so the RHS does not see the function parameter.
    config = SimpleNamespace(
        provider=provider,
        model=model,
        api_key=api_key,
        yc_folder=yc_folder,
        debug=debug,
        retry=retry,
        profile="gradelab",
    )

    sem = asyncio.Semaphore(max(1, concurrency))
    cache_lock = asyncio.Lock()

    cache = _load_cache(output_dir)
    if cache.get("effort") != effort:
        cache = {"task_map": None, "students": {}, "effort": effort}
    cache["reference_path"] = str(reference_path)
    cache["input_dir"] = str(output_dir)
    _save_cache(output_dir, cache)

    ref_cells = parse_ipynb_rich(filepath=str(reference_path))

    if cache.get("task_map"):
        task_map = cache["task_map"]
    else:
        async with sem:
            task_map = await _extract_task_map(
                ref_cells,
                provider=config.provider,
                model=config.model,
                api_key=config.api_key,
                yc_folder=config.yc_folder,
                debug=config.debug,
                retry=config.retry,
                temperature=temperature,
                seed=infer_seed,
                top_p=top_p,
                openrouter_provider=openrouter_provider,
            )
        if task_map is None:
            return None, {}, [], []
        async with cache_lock:
            cache["task_map"] = task_map
            _save_cache(output_dir, cache)

    tasks = task_map["tasks"]
    context_ids = task_map.get("context_cells", [])
    ref_index = _cells_by_id(ref_cells)
    context_cells = _slice_cells(ref_index, context_ids)

    students = student_tuples
    all_results: dict[str, list] = {}
    low_confidence: list[dict] = []
    failed_students: list[str] = []

    async def grade_one_task(
        student_name: str,
        task: dict,
        ref_task_cells: list[dict],
        student_task_cells: list[dict],
    ) -> dict | None:
        async with sem:
            return await _grade_single_task(
                task,
                context_cells,
                ref_task_cells,
                student_task_cells,
                provider=config.provider,
                model=config.model,
                api_key=config.api_key,
                yc_folder=config.yc_folder,
                debug=config.debug,
                retry=config.retry,
                effort=effort,
                temperature=temperature,
                seed=infer_seed,
                top_p=top_p,
                openrouter_provider=openrouter_provider,
            )

    async def grade_one_student(student_name: str, notebook_path: Path) -> None:
        cached_student = cache.get("students", {}).get(student_name)
        if cached_student and cached_student.get("complete"):
            task_results = cached_student["results"]
            all_results[student_name] = task_results
            for t in task_results:
                conf = t.get("confidence", "manual-review")
                if conf in ("low", "manual-review"):
                    low_confidence.append({
                        "student": student_name,
                        "task_id": t["task_id"],
                        "mark": t.get("mark", 0),
                        "confidence": conf,
                        "interpretation": t.get("interpretation", ""),
                    })
            return

        student_cells = parse_ipynb_rich(filepath=str(notebook_path))
        cached_tasks: dict = {}
        if cached_student and "results" in cached_student:
            for r in cached_student["results"]:
                cached_tasks[r["task_id"]] = r

        fresh_tasks: list[dict] = []
        fresh_coros: list = []
        for task in tasks:
            task_id = task["task_id"]
            if task_id in cached_tasks:
                continue
            all_task_ids = (
                task.get("task_cells", [])
                + task.get("solution_cells", [])
                + task.get("output_cells", [])
            )
            ref_task_cells = _slice_cells(ref_index, all_task_ids)
            student_task_cells = _find_student_cells_for_task(task, ref_index, student_cells)
            fresh_tasks.append(task)
            fresh_coros.append(
                grade_one_task(student_name, task, ref_task_cells, student_task_cells)
            )

        fresh_results = await asyncio.gather(*fresh_coros) if fresh_coros else []

        task_results: list[dict] = []
        for task in tasks:
            task_id = task["task_id"]
            if task_id in cached_tasks:
                task_results.append(cached_tasks[task_id])

        for task, result in zip(fresh_tasks, fresh_results):
            if result is None:
                continue
            task_results.append(result)
            conf = result.get("confidence", "?")
            if conf in ("low", "manual-review"):
                low_confidence.append({
                    "student": student_name,
                    "task_id": result["task_id"],
                    "mark": result.get("mark", 0),
                    "confidence": conf,
                    "interpretation": result.get("interpretation", ""),
                })

        if not task_results:
            failed_students.append(student_name)
            async with cache_lock:
                cache.setdefault("students", {})[student_name] = {
                    "results": task_results,
                    "complete": False,
                }
                _save_cache(output_dir, cache)
            return

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
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

    await asyncio.gather(
        *[grade_one_student(name, path) for name, path in students]
    )

    if all_results:
        _write_grades_csv(output_dir, tasks, all_results)
    summary_path = output_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "task_map": task_map,
            "results": all_results,
            "low_confidence": low_confidence,
            "failed": failed_students,
        }, f, indent=2, ensure_ascii=False)

    return task_map, all_results, low_confidence, failed_students


# ── Adjust action ──

def _regenerate_outputs(output_dir: Path, cache: dict):
    """Regenerate reports, CSV, and summary from cache."""
    task_map = cache["task_map"]
    tasks = task_map["tasks"]
    all_results = {}

    for student_name, student_data in cache.get("students", {}).items():
        if not student_data.get("results"):
            continue
        task_results = student_data["results"]
        all_results[student_name] = task_results

        report = _generate_report(student_name, task_results)
        report_path = output_dir / f"{student_name}.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

    if all_results:
        _write_grades_csv(output_dir, tasks, all_results)

    low_confidence = []
    for student_name, task_results in all_results.items():
        for t in task_results:
            conf = t.get("confidence", "manual-review")
            if conf in ("low", "manual-review"):
                low_confidence.append({
                    "student": student_name,
                    "task_id": t["task_id"],
                    "mark": t.get("mark", 0),
                    "confidence": conf,
                    "interpretation": t.get("interpretation", ""),
                })

    summary_path = output_dir / "_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "task_map": task_map,
            "results": all_results,
            "low_confidence": low_confidence,
            "failed": [],
        }, f, indent=2, ensure_ascii=False)

    return all_results


adjust_system_prompt = """
You are re-grading a previously graded task based on an adjustment instruction.

You receive the previous grading result (mark, interpretation, issues) and an
adjustment instruction from the teacher. Re-evaluate the mark accordingly.

=== OUTPUT FORMAT ===

Your output will be machine-parsed by json.loads().
CRITICAL: First character = {, last character = }

{
  "task_id": <int>,
  "mark": <float 0-1>,
  "interpretation": "<1-2 sentence assessment in Russian>",
  "issues": ["<issue in Russian>"],
  "confidence": "<high|medium|low|manual-review>"
}

Rules:
1. NO markdown fences. Raw JSON only.
2. NO text before or after the JSON.
3. "interpretation" and "issues" in Russian.
4. "issues" is an array. Empty [] if no issues.
5. First character = {, last character = }
"""


def action_adjust(args, config):
    asyncio.run(_action_adjust_async(args, config))


async def _action_adjust_async(args, config):
    output_dir = Path(args.output)
    adjustment = args.prompt
    task_filter = getattr(args, "task", None)
    student_filter = getattr(args, "student", None)
    concurrency = max(1, int(getattr(args, "concurrency", 8) or 8))

    temperature, infer_seed, top_p = _sampling_triple({})

    if not output_dir.exists():
        print(f"Error: output directory not found: {output_dir}")
        return

    cache = _load_cache(output_dir)

    if not cache.get("task_map"):
        print("Error: no cached task_map found — run instant first")
        return

    if not cache.get("students"):
        print("Error: no cached results found — run instant first")
        return

    if not config.profile:
        print("Error: profile required for adjust action")
        return

    task_map = cache["task_map"]
    tasks = task_map["tasks"]

    sem = asyncio.Semaphore(concurrency)
    cache_lock = asyncio.Lock()

    print(f"Provider: {config.provider}, Model: {config.model}")
    print(f"Adjustment: {adjustment}")
    print(f"Concurrency: {concurrency}")
    if task_filter:
        print(f"Task filter: {task_filter}")
    if student_filter:
        print(f"Student filter: {student_filter}")
    print()

    # figure out which tasks to target
    target_task_ids: set = set()
    if task_filter:
        try:
            target_task_ids = {int(x) for x in task_filter.split(",")}
        except ValueError:
            print(f"Error: --task must be comma-separated integers, got: {task_filter}")
            return
    else:
        target_task_ids = {t["task_id"] for t in tasks}

    tasks_by_id = {t["task_id"]: t for t in tasks}
    adjusted_count = 0

    students_to_adjust = []
    for student_name, student_data in sorted(cache.get("students", {}).items()):
        if student_filter and student_filter not in student_name:
            continue
        if not student_data.get("results"):
            continue
        students_to_adjust.append(student_name)

    print(f"Adjusting {len(students_to_adjust)} student(s), tasks: {sorted(target_task_ids)}")

    async def adjust_one_task(student_name: str, idx: int, result: dict) -> tuple[int, dict | None]:
        task_id = result["task_id"]
        old_mark = result.get("mark", "?")
        task = tasks_by_id.get(task_id)
        desc = task.get("description", "?") if task else "?"

        user_prompt = f"""Task {task_id}: {desc}

=== PREVIOUS GRADING RESULT ===
Mark: {old_mark}
Interpretation: {result.get('interpretation', '')}
Issues: {json.dumps(result.get('issues', []), ensure_ascii=False)}
Confidence: {result.get('confidence', '?')}

=== ADJUSTMENT INSTRUCTION ===
{adjustment}

Re-grade this task considering the adjustment instruction above."""

        print(f"  [{student_name}] Task {task_id} (was {old_mark}): adjusting...")

        async with sem:
            result_text, usage = await _call_llm(
                config.provider, config.model, config.api_key,
                adjust_system_prompt, user_prompt,
                yc_folder=config.yc_folder, debug=config.debug, retry=config.retry,
                temperature=temperature, seed=infer_seed, top_p=top_p,
                label=f"adjust task {task_id}",
            )

        if result_text is None:
            print(f"  [{student_name}] Task {task_id}: FAILED, keeping old mark")
            return idx, None

        extracted = _extract_json(result_text)
        try:
            new_result = json.loads(extracted)
            if isinstance(new_result, list) and len(new_result) == 1:
                new_result = new_result[0]
            if not isinstance(new_result, dict):
                print(f"  [{student_name}] Task {task_id}: bad response type, keeping old mark")
                return idx, None

            new_result["task_id"] = task_id
            new_mark = new_result.get("mark", "?")
            new_conf = new_result.get("confidence", "?")
            print(f"    [{student_name}] Task {task_id}: {old_mark} -> {new_mark} (confidence: {new_conf})")
            return idx, new_result

        except json.JSONDecodeError as e:
            print(f"  [{student_name}] Task {task_id}: JSON parse error: {e}, keeping old mark")
            return idx, None

    async def adjust_one_student(student_name: str) -> int:
        student_data = cache["students"][student_name]
        task_results = student_data["results"]
        print(f"\n== {student_name}")

        coros = []
        for idx, result in enumerate(task_results):
            task_id = result["task_id"]
            if task_id not in target_task_ids:
                continue
            coros.append(adjust_one_task(student_name, idx, result))

        if not coros:
            return 0

        outcomes = await asyncio.gather(*coros)

        local_count = 0
        updated = False
        for idx, new_result in outcomes:
            if new_result is None:
                continue
            task_results[idx] = new_result
            updated = True
            local_count += 1

        if updated:
            async with cache_lock:
                cache["students"][student_name] = {
                    "results": task_results,
                    "complete": True,
                }
                _save_cache(output_dir, cache)

        return local_count

    counts = await asyncio.gather(
        *[adjust_one_student(name) for name in students_to_adjust]
    )
    adjusted_count = sum(counts)

    print(f"\n{'='*60}")
    print(f"Adjusted {adjusted_count} task(s)")

    # regenerate all outputs
    print("\nRegenerating reports and CSV...")
    all_results = _regenerate_outputs(output_dir, cache)
    print(f"Done. {len(all_results)} student(s) updated.")
