import json
import os
from pathlib import Path


def _score_status(score: float, threshold: float = 1.0) -> str:
    if score >= threshold:
        return "pass"
    if score > 0:
        return "partial"
    return "fail"


def _process_student(filepath: str) -> dict:
    student_id = Path(filepath).stem
    file_size = os.path.getsize(filepath)

    try:
        with open(filepath, encoding="utf-8") as f:
            nb = json.load(f)
        cells = nb.get("cells", [])
        total_cells = len(cells)
        code_cells = sum(1 for c in cells if c.get("cell_type") == "code")
        markdown_cells = sum(1 for c in cells if c.get("cell_type") == "markdown")
        parse_error = None
    except Exception as exc:
        total_cells = 0
        code_cells = 0
        markdown_cells = 0
        parse_error = str(exc)

    if parse_error:
        tasks = [
            {
                "task_id": "cell_count",
                "score": 0.0,
                "max_score": 5.0,
                "status": "error",
                "comment": f"Parse error: {parse_error}",
            },
            {
                "task_id": "has_markdown",
                "score": 0.0,
                "max_score": 1.0,
                "status": "error",
                "comment": f"Parse error: {parse_error}",
            },
            {
                "task_id": "file_size",
                "score": 0.0,
                "max_score": 10.0,
                "status": "error",
                "comment": f"Parse error: {parse_error}",
            },
        ]
        total_score = 0.0
        report = f"Failed to parse notebook: {parse_error}"
        metadata = {"file_size": file_size}
    else:
        cell_count_score = 1.0 if total_cells >= 5 else total_cells / 5.0
        cell_count_status = _score_status(cell_count_score)

        has_markdown_score = 1.0 if markdown_cells >= 1 else 0.0
        has_markdown_status = "pass" if has_markdown_score == 1.0 else "fail"

        file_size_score = min(1.0, file_size / 10240)
        file_size_status = "pass" if file_size_score >= 1.0 else "partial"

        tasks = [
            {
                "task_id": "cell_count",
                "score": cell_count_score,
                "max_score": 5.0,
                "status": cell_count_status,
                "comment": f"{total_cells} out of 5 cells",
            },
            {
                "task_id": "has_markdown",
                "score": has_markdown_score,
                "max_score": 1.0,
                "status": has_markdown_status,
                "comment": f"{markdown_cells} markdown cell(s)",
            },
            {
                "task_id": "file_size",
                "score": file_size_score,
                "max_score": 10.0,
                "status": file_size_status,
                "comment": f"{file_size} bytes",
            },
        ]

        total_score = (cell_count_score + has_markdown_score + file_size_score) / 3.0
        report = (
            f"Processed {code_cells} code cells, "
            f"{markdown_cells} markdown cells, "
            f"{file_size} bytes"
        )
        metadata = {
            "code_cells": code_cells,
            "markdown_cells": markdown_cells,
            "total_cells": total_cells,
            "file_size": file_size,
        }

    return {
        "student_id": student_id,
        "tasks": tasks,
        "total_score": total_score,
        "report": report,
        "metadata": metadata,
    }


def run(context: dict) -> dict:
    student_files = context["student_files"]
    results = [_process_student(f) for f in student_files]
    return {
        "results": results,
        "metadata": {
            "pipeline": "mock_pipeline",
            "version": "0.1.0",
            "total_students": len(results),
        },
    }
