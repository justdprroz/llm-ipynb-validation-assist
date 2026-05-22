"""Download realm homework files from Storage Manager into a local directory for pipeline runs."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.config import get_settings
from app.mongo_store import get_mongo_db
from app.storage_client import storage_get_bytes, storage_list_keys


def materialize_homework(homework_id: str, dest_dir: Path) -> tuple[Path, Path, list[str]]:
    """Materialize homework notebooks under dest_dir. Returns (homework_dir, students_dir, student_files)."""
    db = get_mongo_db()
    hw = db.homeworks.find_one({"_id": homework_id})
    if hw is None:
        raise ValueError(f"Homework {homework_id} not found")

    realm = db.realms.find_one({"_id": hw["realm_id"]})
    if realm is None:
        raise ValueError(f"Realm for homework {homework_id} not found")

    settings = get_settings()
    bucket = "realms"
    prefix = f"{realm['_id']}/{hw['name']}/"

    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    keys = storage_list_keys(bucket, prefix)
    if not keys:
        raise ValueError(f"No files found in storage for homework {homework_id}")

    for key in keys:
        rel = key[len(prefix) :]
        if not rel or rel.endswith("/"):
            continue
        local_path = dest_dir / rel
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(storage_get_bytes(bucket, key))

    students_dir = dest_dir / "students"
    gold_dir = dest_dir / "gold"
    if students_dir.is_dir():
        student_files = sorted(str(p) for p in students_dir.glob("*.ipynb"))
        return dest_dir, students_dir, student_files

    student_files = sorted(str(p) for p in dest_dir.glob("*.ipynb"))
    return dest_dir, dest_dir, student_files
