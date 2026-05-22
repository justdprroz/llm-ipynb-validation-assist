import json
import sys
import time
import asyncio
from pathlib import Path
from typing import Optional

from llm_notebook_grader.inference import universal_prompt, async_universal_prompt
from llm_notebook_grader.data_layout import (
    get_latest_action_file,
    get_next_revision,
    add_action_file,
)
from llm_notebook_grader.prompts import check, fullcheck
from llm_notebook_grader.prompts.check_reasoning import REASONING_MODES
from llm_notebook_grader.prompts.fullcheck_reasoning import REASONING_MODES as FULLCHECK_REASONING_MODES


def _build_task_input(parsed_cells: list, extract_data: list, task: dict) -> str:
    """Build LLM input for a single task: general context + task cell + solution cells."""
    # cell id -> list of entries (code cells and outputs share the same id)
    cells_by_id: dict[int, list[dict]] = {}
    for cell_str in parsed_cells:
        if not isinstance(cell_str, str):
            continue

        # parse format: "id: type: content"
        parts = cell_str.split(": ", 2)
        if len(parts) < 3:
            continue

        try:
            cell_id = int(parts[0])
            cell_type = parts[1]
            cell_content = parts[2]
        except (ValueError, IndexError):
            continue

        cells_by_id.setdefault(cell_id, []).append({
            "id": cell_id,
            "type": cell_type,
            "content": cell_content
        })

    # collect general cell ids
    general_ids = set()
    for block in extract_data:
        if block.get("type") == "general":
            general_ids.update(block.get("cells", []))

    parts = []

    def _fmt_cells(cell_id: int) -> list[str]:
        """Format all entries for a cell id (code + outputs)."""
        return [f"[{c['type']}] {c['content']}" for c in cells_by_id.get(cell_id, [])]

    # general context
    general_lines = []
    for cid in sorted(general_ids):
        general_lines.extend(_fmt_cells(cid))
    if general_lines:
        parts.append("=== CONTEXT (general/setup cells) ===")
        parts.extend(general_lines)

    # task description
    task_cell_id = task["task_cell"]
    if task_cell_id in cells_by_id:
        parts.append(f"\n=== TASK (task_id: {task['task_id']}) ===")
        parts.extend(_fmt_cells(task_cell_id))

    # solution cells
    solution_ids = task.get("solution_cells", [])
    if solution_ids:
        parts.append("\n=== STUDENT SOLUTION ===")
        for sid in solution_ids:
            parts.extend(_fmt_cells(sid))

    return "\n".join(parts)


def check_tasks_with_model(
    *,
    submission_dir: Path,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: Optional[str] = None,
    reasoning: str = "standard",
    profile: str,
    debug: bool = False,
    retry: int = 3,
) -> tuple[bool, int]:
    parsed_file = get_latest_action_file(submission_dir, "parse")
    if not parsed_file or not parsed_file.exists():
        print(f"    Error: no parsed file found")
        return False, 0

    extract_file = get_latest_action_file(submission_dir, "extract")
    if not extract_file or not extract_file.exists():
        print(f"    Error: no extract file found")
        return False, 0

    with open(parsed_file, "r", encoding="utf-8") as f:
        parsed_cells = json.load(f)

    print(extract_file)

    with open(extract_file, "r", encoding="utf-8") as f:
        extract_envelope = json.load(f)

    if isinstance(extract_envelope, dict) and "tasks" in extract_envelope:
        extract_data = extract_envelope["tasks"]
        source_parsed_file = extract_envelope.get("source_parsed_file", "unknown")
    else:
        extract_data = extract_envelope
        source_parsed_file = "unknown"

    if provider == "yc" and not yc_folder:
        print(f"    Error: yc_folder required for yc provider")
        return False, 0

    # filter task blocks
    tasks = [block for block in extract_data if block.get("type") == "task"]

    if not tasks:
        print(f"    Error: no tasks found in extract data")
        return False, 0

    reasoning_prompt = REASONING_MODES.get(reasoning, REASONING_MODES["standard"])
    system_prompt = f"{reasoning_prompt}\n\n{check.hardened_prompt}"

    if debug:
        print("=" * 80, file=sys.stderr)
        print("DEBUG: Full system prompt for check", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(system_prompt, file=sys.stderr)
        print("=" * 80, file=sys.stderr)

    results = []
    raw_responses = []
    succeeded = 0
    failed = 0

    print(tasks)

    for task in tasks:
        print("~"*100, "\n", task)
        task_id = task["task_id"]
        task_input = _build_task_input(parsed_cells, extract_data, task)
        task_input_with_id = f"Grade task_id={task_id}.\n\n{task_input}"

        if debug:
            print("=" * 80, file=sys.stderr)
            print(f"DEBUG: Task input for task_id={task_id}", file=sys.stderr)
            print("=" * 80, file=sys.stderr)
            print(task_input_with_id, file=sys.stderr)
            print("=" * 80, file=sys.stderr)

        print(f"=== Checking task {task_id}")

        last_error = None
        result = None

        for attempt in range(retry + 1):
            if attempt > 0:
                wait = 2 ** (attempt - 1)
                print(f"  Retry {attempt}/{retry} for task {task_id}")
                time.sleep(wait)

            # inference
            try:
                result_json, usage, response = universal_prompt(
                    provider,
                    prompts=[system_prompt, task_input_with_id],
                    model_name=model,
                    api_token=api_key,
                    folder=yc_folder,
                )
            except Exception as e:
                last_error = str(e)
                continue

            raw_responses.append(response)

            # json parse
            try:
                result = json.loads(result_json)
            except json.JSONDecodeError:
                last_error = "JSON parsing failed"
                result = None
                continue

            break

        if result is not None:
            results.append(result)
            succeeded += 1
        else:
            print(f"  Task {task_id} failed after {retry} retries: {last_error}")
            results.append({
                "task_id": task_id,
                "failed": True,
                "error": last_error,
            })
            failed += 1

    print(f"Checked {len(tasks)} tasks ({succeeded} succeeded, {failed} failed)")

    reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
    profile_id = f"{profile}_{reasoning_short}"

    revision = get_next_revision(submission_dir, "check", profile_id)

    # save raw responses
    raw_path = submission_dir / f"check_{profile_id}_{revision}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_responses, f, indent=2, ensure_ascii=False)

    # save results
    output_filename = f"check_{profile_id}_{revision}.json"
    output_path = submission_dir / output_filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    add_action_file(submission_dir, "check", output_filename)

    return True, revision


def check_full_notebook_with_model(
    *,
    submission_dir: Path,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: Optional[str] = None,
    reasoning: str = "standard",
    profile: str,
    debug: bool = False,
    retry: int = 3,
) -> tuple[bool, int]:
    parsed_file = get_latest_action_file(submission_dir, "parse")
    if not parsed_file or not parsed_file.exists():
        print(f"    Error: no parsed file found")
        return False, 0

    with open(parsed_file, "r", encoding="utf-8") as f:
        parsed_cells = json.load(f)

    if provider == "yc" and not yc_folder:
        print(f"    Error: yc_folder required for yc provider")
        return False, 0

    reasoning_prompt = FULLCHECK_REASONING_MODES.get(reasoning, FULLCHECK_REASONING_MODES["standard"])
    system_prompt = f"{reasoning_prompt}\n\n{fullcheck.hardened_prompt}"

    # build single user prompt with entire notebook
    notebook_text = "\n".join(parsed_cells) if parsed_cells else ""
    user_prompt = f"Grade all tasks in the following notebook.\n\n{notebook_text}"

    if debug:
        print("=" * 80, file=sys.stderr)
        print("DEBUG: Full system prompt for fullcheck", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(system_prompt, file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("DEBUG: User prompt for fullcheck", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(user_prompt, file=sys.stderr)
        print("=" * 80, file=sys.stderr)

    last_error = None
    results = None
    raw_response = None

    for attempt in range(retry + 1):
        if attempt > 0:
            wait = 2 ** (attempt - 1)
            print(f"  Retry {attempt}/{retry}")
            time.sleep(wait)

        try:
            result_json, usage, response = universal_prompt(
                provider,
                prompts=[system_prompt, user_prompt],
                model_name=model,
                api_token=api_key,
                folder=yc_folder,
            )
        except Exception as e:
            last_error = str(e)
            continue

        raw_response = response

        try:
            results = json.loads(result_json)
        except json.JSONDecodeError:
            last_error = "JSON parsing failed"
            results = None
            continue

        if not isinstance(results, list):
            last_error = "Response is not a JSON array"
            results = None
            continue

        break

    if results is None:
        print(f"  Full notebook check failed after {retry} retries: {last_error}")
        return False, 0

    print(f"  Graded {len(results)} tasks in full-notebook mode")

    reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
    profile_id = f"{profile}_{reasoning_short}"

    revision = get_next_revision(submission_dir, "full-check", profile_id)

    # save raw response
    raw_path = submission_dir / f"full-check_{profile_id}_{revision}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_response, f, indent=2, ensure_ascii=False)

    envelope = {
        "source_parsed_file": parsed_file.name,
        "results": results
    }

    # save results
    output_filename = f"full-check_{profile_id}_{revision}.json"
    output_path = submission_dir / output_filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)

    add_action_file(submission_dir, "full-check", output_filename)

    return True, revision


async def check_full_notebook_with_model_async(
    *,
    submission_dir: Path,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: Optional[str] = None,
    reasoning: str = "standard",
    profile: str,
    debug: bool = False,
    retry: int = 3,
) -> tuple[bool, int]:
    parsed_file = get_latest_action_file(submission_dir, "parse")
    if not parsed_file or not parsed_file.exists():
        print(f"    Error: no parsed file found")
        return False, 0

    with open(parsed_file, "r", encoding="utf-8") as f:
        parsed_cells = json.load(f)

    if provider == "yc" and not yc_folder:
        print(f"    Error: yc_folder required for yc provider")
        return False, 0

    reasoning_prompt = FULLCHECK_REASONING_MODES.get(reasoning, FULLCHECK_REASONING_MODES["standard"])
    system_prompt = f"{reasoning_prompt}\n\n{fullcheck.hardened_prompt}"

    notebook_text = "\n".join(parsed_cells) if parsed_cells else ""
    user_prompt = f"Grade all tasks in the following notebook.\n\n{notebook_text}"

    if debug:
        print("=" * 80, file=sys.stderr)
        print("DEBUG: Full system prompt for fullcheck", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(system_prompt, file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("DEBUG: User prompt for fullcheck", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(user_prompt, file=sys.stderr)
        print("=" * 80, file=sys.stderr)

    last_error = None
    results = None
    raw_response = None

    for attempt in range(retry + 1):
        if attempt > 0:
            wait = 2 ** (attempt - 1)
            print(f"  Retry {attempt}/{retry}")
            await asyncio.sleep(wait)

        try:
            result_json, usage, response = await async_universal_prompt(
                provider,
                prompts=[system_prompt, user_prompt],
                model_name=model,
                api_token=api_key,
                folder=yc_folder,
            )
        except Exception as e:
            last_error = str(e)
            continue

        raw_response = response

        try:
            results = json.loads(result_json)
        except json.JSONDecodeError:
            last_error = "JSON parsing failed"
            results = None
            continue

        if not isinstance(results, list):
            last_error = "Response is not a JSON array"
            results = None
            continue

        break

    if results is None:
        print(f"  Full notebook check failed after {retry} retries: {last_error}")
        return False, 0

    print(f"  Graded {len(results)} tasks in full-notebook mode")

    reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
    profile_id = f"{profile}_{reasoning_short}"

    revision = get_next_revision(submission_dir, "full-check", profile_id)

    raw_path = submission_dir / f"full-check_{profile_id}_{revision}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_response, f, indent=2, ensure_ascii=False)

    envelope = {
        "source_parsed_file": parsed_file.name,
        "results": results
    }

    output_filename = f"full-check_{profile_id}_{revision}.json"
    output_path = submission_dir / output_filename

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)

    add_action_file(submission_dir, "full-check", output_filename)

    return True, revision
