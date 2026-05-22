import json
import sys
from pathlib import Path
from typing import Optional

from llm_notebook_grader.inference import universal_prompt
from llm_notebook_grader.data_layout import (
    get_latest_action_file,
    get_next_revision,
    add_action_file,
)
from llm_notebook_grader.prompts import extract
from llm_notebook_grader.prompts.extract_reasoning import REASONING_MODES


def extract_tasks_with_model(
    *,
    submission_dir: Path,
    provider: str,
    model: str,
    api_key: str,
    yc_folder: Optional[str] = None,
    reasoning: str = "standard",
    profile: str,
    debug: bool = False,
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

    parsed_notebook_str = "\n".join(parsed_cells)

    reasoning_prompt = REASONING_MODES.get(reasoning, REASONING_MODES["standard"])
    system_prompt = f"{reasoning_prompt}\n\n{extract.restrictive_prompt}"

    if debug:
        print("=" * 80, file=sys.stderr)
        print("DEBUG: Full system prompt for extract", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(system_prompt, file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(f"User message length: {len(parsed_notebook_str)} chars", file=sys.stderr)
        print("=" * 80, file=sys.stderr)

    try:
        print("=== Running model")
        extracted_json, usage, response = universal_prompt(
            provider,
            prompts=[system_prompt, parsed_notebook_str],
            model_name=model,
            api_token=api_key,
            folder=yc_folder,
        )
    except Exception as e:
        print(f"    Error during inference: {e}")
        return False, 0

    reasoning_short = {"restrictive": "res", "standard": "sta", "verbose": "ver"}[reasoning]
    profile_id = f"{profile}_{reasoning_short}"

    revision = get_next_revision(submission_dir, "extract", profile_id)

    raw_response_path = submission_dir / f"extract_{profile_id}_{revision}_raw.json"
    with open(raw_response_path, "w", encoding="utf-8") as f:
        json.dump(response, f, indent=2, ensure_ascii=False)

    output_filename = f"extract_{profile_id}_{revision}.json"
    output_path = submission_dir / output_filename

    try:
        tasks = json.loads(extracted_json)
    except json.JSONDecodeError as e:
        print(f"    Error: JSON parsing failed: {e}")
        print(f"    Raw response saved to {raw_response_path.name}")
        return False, 0

    envelope = {
        "source_parsed_file": parsed_file.name,
        "tasks": tasks
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)

    add_action_file(submission_dir, "extract", output_filename)

    return True, revision
