import json
import sys
import asyncio
from pathlib import Path
from typing import Optional
from collections import defaultdict

from llm_notebook_grader.inference import async_universal_prompt
from llm_notebook_grader.data_layout import get_latest_action_file
from llm_notebook_grader.prompts import validate
from llm_notebook_grader.prompts.check_reasoning import REASONING_MODES


def _extract_task_content(parsed_cells: list, task_cell: int, solution_cells: list, output_cells: list) -> dict:
    cells_by_id: dict[int, list[dict]] = {}

    for cell_str in parsed_cells:
        if not isinstance(cell_str, str):
            continue

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

    def _fmt_cells(cell_id: int) -> list[str]:
        return [f"[{c['type']}] {c['content']}" for c in cells_by_id.get(cell_id, [])]

    task_desc = "\n".join(_fmt_cells(task_cell)) if task_cell in cells_by_id else ""

    solution_lines = []
    for sid in solution_cells:
        solution_lines.extend(_fmt_cells(sid))

    output_lines = []
    for oid in output_cells:
        output_lines.extend(_fmt_cells(oid))

    return {
        "task_description": task_desc,
        "solution": "\n".join(solution_lines),
        "output": "\n".join(output_lines)
    }


async def _validate_single_task(
    task_id: int,
    students_data: list[dict],
    provider: str,
    model: str,
    api_key: str,
    yc_folder: Optional[str],
    reasoning_prompt: str,
    debug: bool,
) -> dict:
    if not students_data:
        return {
            "task_id": task_id,
            "guidance": "No student data available",
            "patterns": []
        }

    first_student = students_data[0]
    task_desc = first_student["content"]["task_description"]

    student_sections = []
    for idx, student in enumerate(students_data, 1):
        student_hash = student["hash"][:8]
        content = student["content"]
        review = student["review"]

        section = f"""
=== Student {idx} ({student_hash}) ===

Solution:
{content["solution"]}

Output:
{content["output"]}

Review:
  Mark: {review.get("mark", "N/A")}
  Interpretation: {review.get("interpretation", "N/A")}
  Issues: {review.get("issues", [])}
"""
        student_sections.append(section)

    user_prompt = f"""Task {task_id}:

{task_desc}

{"".join(student_sections)}

Provide cross-student calibration analysis for this task.
"""

    system_prompt = f"{reasoning_prompt}\n\n{validate.validation_prompt}"

    if debug:
        print("=" * 80, file=sys.stderr)
        print(f"DEBUG: Validation prompt for task {task_id}", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(user_prompt, file=sys.stderr)
        print("=" * 80, file=sys.stderr)

    try:
        result_json, usage, response = await async_universal_prompt(
            provider,
            prompts=[system_prompt, user_prompt],
            model_name=model,
            api_token=api_key,
            folder=yc_folder,
        )
    except Exception as e:
        print(f"  Error validating task {task_id}: {e}")
        return {
            "task_id": task_id,
            "guidance": f"Validation failed: {e}",
            "patterns": []
        }

    try:
        result = json.loads(result_json)
        result["task_id"] = task_id
        return result
    except json.JSONDecodeError as e:
        print(f"  JSON parse error for task {task_id}: {e}")
        return {
            "task_id": task_id,
            "guidance": "Validation response parsing failed",
            "patterns": []
        }


async def validate_cross_student(
    *,
    submissions: list[dict],
    data_dir: Path,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: Optional[str] = None,
    reasoning: str = "standard",
    profile: str,
    debug: bool = False,
    single_task_id: Optional[int] = None,
) -> tuple[bool, dict]:
    from llm_notebook_grader.data_layout import get_submission_dir

    students_data = []

    for entry in submissions:
        course = entry["course"]
        hash_val = entry["hash"]

        submission_dir = get_submission_dir(data_dir, course, hash_val)

        grading_file = get_latest_action_file(submission_dir, "full-check")
        if not grading_file or not grading_file.exists():
            grading_file = get_latest_action_file(submission_dir, "check")
        parse_file = get_latest_action_file(submission_dir, "parse")

        if not grading_file or not grading_file.exists():
            print(f"  Warning: no full-check/check file for {hash_val[:8]}, skipping")
            continue

        if not parse_file or not parse_file.exists():
            print(f"  Warning: no parse file for {hash_val[:8]}, skipping")
            continue

        with open(grading_file, "r", encoding="utf-8") as f:
            grading_data = json.load(f)

        if isinstance(grading_data, dict) and "results" in grading_data:
            results = grading_data["results"]
        else:
            results = grading_data

        with open(parse_file, "r", encoding="utf-8") as f:
            parsed_cells = json.load(f)

        students_data.append({
            "hash": hash_val,
            "entry": entry,
            "results": results,
            "parsed_cells": parsed_cells
        })

    if not students_data:
        print("  Error: no valid student data found")
        return False, {}

    tasks_by_id = defaultdict(list)

    for student in students_data:
        for task_result in student["results"]:
            task_id = task_result.get("task_id")
            if task_id is None:
                continue

            content = _extract_task_content(
                student["parsed_cells"],
                task_result.get("task_cell"),
                task_result.get("solution_cells", []),
                task_result.get("output_cells", [])
            )

            tasks_by_id[task_id].append({
                "hash": student["hash"],
                "content": content,
                "review": task_result
            })

    if not tasks_by_id:
        print("  Error: no tasks found to validate")
        return False, {}

    if single_task_id is not None:
        if single_task_id not in tasks_by_id:
            print(f"  Error: task_id {single_task_id} not found")
            return False, {}

        print(f"  Validating task {single_task_id} across {len(students_data)} students")

        reasoning_prompt = REASONING_MODES.get(reasoning, REASONING_MODES["standard"])

        task_review = await _validate_single_task(
            task_id=single_task_id,
            students_data=tasks_by_id[single_task_id],
            provider=provider,
            model=model,
            api_key=api_key,
            yc_folder=yc_folder,
            reasoning_prompt=reasoning_prompt,
            debug=debug
        )

        task_reviews = [task_review]
    else:
        print(f"  Validating {len(tasks_by_id)} tasks across {len(students_data)} students")

        reasoning_prompt = REASONING_MODES.get(reasoning, REASONING_MODES["standard"])

        validation_tasks = [
            _validate_single_task(
                task_id=task_id,
                students_data=student_list,
                provider=provider,
                model=model,
                api_key=api_key,
                yc_folder=yc_folder,
                reasoning_prompt=reasoning_prompt,
                debug=debug
            )
            for task_id, student_list in sorted(tasks_by_id.items())
        ]

        task_reviews = await asyncio.gather(*validation_tasks)

    validation_result = {
        "validation_metadata": {
            "students_count": len(students_data),
            "student_hashes": [s["hash"] for s in students_data],
            "tasks_validated": len(task_reviews),
            "profile": profile,
            "reasoning": reasoning
        },
        "task_reviews": task_reviews
    }

    return True, validation_result
