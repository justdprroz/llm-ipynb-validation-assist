import json
import os
from pathlib import Path
from typing import Optional


def get_submission_dir(data_dir: Path, course: str, submission_hash: str) -> Path:
    return data_dir / course / "submissions" / submission_hash


def get_submission_db_path(submission_dir: Path) -> Path:
    return submission_dir / "db.json"


def load_submission_db(submission_dir: Path) -> dict:
    db_path = get_submission_db_path(submission_dir)
    if db_path.exists():
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_submission_db(submission_dir: Path, db: dict) -> None:
    db_path = get_submission_db_path(submission_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def get_next_revision(submission_dir: Path, action: str, model_id: Optional[str] = None) -> str:
    db = load_submission_db(submission_dir)
    actions = db.get("actions", {})
    existing = actions.get(action, [])

    if not existing:
        return "000"

    max_rev = -1
    for filename in existing:
        if model_id:
            prefix = f"{action}_{model_id}_"
        else:
            prefix = f"{action}_"

        if filename.startswith(prefix):
            rev_part = filename[len(prefix):].split(".")[0]
            try:
                rev_num = int(rev_part)
                max_rev = max(max_rev, rev_num)
            except ValueError:
                continue

    return f"{max_rev + 1:03d}"


def add_action_file(submission_dir: Path, action: str, filename: str) -> None:
    db = load_submission_db(submission_dir)

    if "actions" not in db:
        db["actions"] = {}

    if action not in db["actions"]:
        db["actions"][action] = []

    if filename not in db["actions"][action]:
        db["actions"][action].append(filename)

    save_submission_db(submission_dir, db)


def get_latest_action_file(submission_dir: Path, action: str, model_id: Optional[str] = None) -> Optional[Path]:
    db = load_submission_db(submission_dir)
    actions = db.get("actions", {})
    files = actions.get(action, [])

    if not files:
        return None

    return submission_dir / files[-1]


def create_symlink_safe(target: Path, link: Path) -> None:
    if link.exists() or link.is_symlink():
        if link.is_symlink() and link.resolve() == target.resolve():
            return
        link.unlink()

    link.parent.mkdir(parents=True, exist_ok=True)

    relative_target = os.path.relpath(target, link.parent)
    link.symlink_to(relative_target, target_is_directory=True)


def get_homework_dir(data_dir: Path, course: str, homework: str) -> Path:
    return data_dir / course / homework


def get_homework_db_path(homework_dir: Path) -> Path:
    return homework_dir / "db.json"


def load_homework_db(homework_dir: Path) -> dict:
    db_path = get_homework_db_path(homework_dir)
    if db_path.exists():
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_homework_db(homework_dir: Path, db: dict) -> None:
    db_path = get_homework_db_path(homework_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def get_next_homework_revision(homework_dir: Path, action: str, profile_id: Optional[str] = None) -> str:
    db = load_homework_db(homework_dir)
    actions = db.get("actions", {})
    existing = actions.get(action, [])

    if not existing:
        return "000"

    max_rev = -1
    for filename in existing:
        if profile_id:
            prefix = f"{action}_{profile_id}_"
        else:
            prefix = f"{action}_"

        if filename.startswith(prefix):
            rev_part = filename[len(prefix):].split(".")[0]
            try:
                rev_num = int(rev_part)
                max_rev = max(max_rev, rev_num)
            except ValueError:
                continue

    return f"{max_rev + 1:03d}"


def add_homework_action(homework_dir: Path, action: str, filename: str) -> None:
    db = load_homework_db(homework_dir)

    if "actions" not in db:
        db["actions"] = {}

    if action not in db["actions"]:
        db["actions"][action] = []

    if filename not in db["actions"][action]:
        db["actions"][action].append(filename)

    save_homework_db(homework_dir, db)
