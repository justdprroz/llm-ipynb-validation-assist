import json
import sys
from pathlib import Path
from typing import Optional

from llm_notebook_grader.inference import universal_prompt
from llm_notebook_grader.data_layout import (
    get_latest_action_file,
    get_next_revision,
    add_action_file,
    get_homework_dir,
)
from llm_notebook_grader.prompts import report
from llm_notebook_grader.prompts.check_reasoning import REASONING_MODES


def _format_task_prompt(task_result: dict, validation_task: Optional[dict]) -> str:
    mark = task_result.get("mark", 0.0)
    interpretation = task_result.get("interpretation", "")
    issues = task_result.get("issues", [])

    task_info = f"""Оценка задачи: {mark}
Интерпретация: {interpretation}
Проблемы: {issues}"""

    if validation_task:
        guidance = validation_task.get("guidance", "")
        patterns = validation_task.get("patterns", [])

        task_info += f"""

Рекомендации по калибровке: {guidance}
Типичные паттерны: {patterns}"""

    return task_info


def generate_report(
    *,
    submission_dir: Path,
    course: str,
    homework: str,
    data_dir: Path,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: Optional[str] = None,
    reasoning: str = "standard",
    profile: str,
    debug: bool = False,
) -> tuple[bool, int]:
    grading_file = get_latest_action_file(submission_dir, "full-check")
    if not grading_file or not grading_file.exists():
        grading_file = get_latest_action_file(submission_dir, "check")
    if not grading_file or not grading_file.exists():
        print(f"    Error: no full-check or check file found")
        return False, 0

    with open(grading_file, "r", encoding="utf-8") as f:
        grading_data = json.load(f)

    if isinstance(grading_data, dict) and "results" in grading_data:
        results = grading_data["results"]
    else:
        results = grading_data

    homework_dir = get_homework_dir(data_dir, course, homework)
    validation_files = list(homework_dir.glob(f"validate_{profile}_*.json"))

    validation_tasks = {}
    if validation_files:
        latest_validation = max(validation_files, key=lambda p: p.name)
        with open(latest_validation, "r", encoding="utf-8") as f:
            validation_data = json.load(f)
            for task_review in validation_data.get("task_reviews", []):
                task_id = task_review.get("task_id")
                if task_id:
                    validation_tasks[task_id] = task_review

    if provider == "yc" and not yc_folder:
        print(f"    Error: yc_folder required for yc provider")
        return False, 0

    reasoning_prompt = REASONING_MODES.get(reasoning, REASONING_MODES["standard"])
    system_prompt = f"{reasoning_prompt}\n\n{report.reporting_prompt}"

    total_mark = 0.0
    task_count = 0
    report_lines = []

    for task_result in results:
        task_id = task_result.get("task_id")
        mark = task_result.get("mark", 0.0)

        total_mark += mark
        task_count += 1

        if mark >= 1.0:
            continue

        validation_task = validation_tasks.get(task_id)
        task_prompt = _format_task_prompt(task_result, validation_task)

        user_prompt = f"Задача {task_id} (оценка {mark}):\n\n{task_prompt}\n\nСоставь краткое объяснение на русском."

        if debug:
            print("=" * 80, file=sys.stderr)
            print(f"DEBUG: Grading prompt for task {task_id}", file=sys.stderr)
            print("=" * 80, file=sys.stderr)
            print(user_prompt, file=sys.stderr)
            print("=" * 80, file=sys.stderr)

        try:
            explanation, usage, response = universal_prompt(
                provider,
                prompts=[system_prompt, user_prompt],
                model_name=model,
                api_token=api_key,
                folder=yc_folder,
            )
            explanation = explanation.strip()
            report_lines.append(f"Задача {task_id} ({mark}): {explanation}")
        except Exception as e:
            print(f"  Error generating explanation for task {task_id}: {e}")
            interpretation = task_result.get("interpretation", "Ошибка генерации отчёта")
            report_lines.append(f"Задача {task_id} ({mark}): {interpretation}")

    final_grade = (total_mark / task_count * 10) if task_count > 0 else 0.0

    if not report_lines:
        report_lines.append("Все задачи выполнены без замечаний.")

    report_lines.append("")
    report_lines.append(f"Итоговая оценка: {final_grade:.1f} / 10")

    report_text = "\n".join(report_lines)

    reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
    profile_id = f"{profile}_{reasoning_short}"

    revision = get_next_revision(submission_dir, "report", profile_id)
    output_filename = f"report_{profile_id}_{revision}.txt"
    output_path = submission_dir / output_filename

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    add_action_file(submission_dir, "report", output_filename)

    return True, revision
