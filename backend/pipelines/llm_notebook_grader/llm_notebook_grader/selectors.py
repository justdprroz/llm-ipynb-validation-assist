import json
from pathlib import Path
from typing import List, Optional


def load_main_db(data_dir: Path) -> dict:
    db_path = data_dir / "db.json"
    if db_path.exists():
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_main_db(data_dir: Path, db: dict) -> None:
    db_path = data_dir / "db.json"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def select_submissions(
    data_dir: Path,
    submission_hash: Optional[str] = None,
    course: Optional[str] = None,
    student: Optional[str] = None,
    homework: Optional[str] = None,
) -> List[dict]:
    db = load_main_db(data_dir)

    if submission_hash:
        if submission_hash in db:
            entry = db[submission_hash].copy()
            entry["hash"] = submission_hash
            return [entry]
        else:
            return []

    results = []
    for hash_key, entry in db.items():
        if course and entry.get("course") != course:
            continue
        if student and entry.get("student") != student:
            continue
        if homework and entry.get("homework") != homework:
            continue

        result = entry.copy()
        result["hash"] = hash_key
        results.append(result)

    return results
