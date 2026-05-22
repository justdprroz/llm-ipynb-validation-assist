from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace

from botocore.client import BaseClient
from fastapi import HTTPException, UploadFile

from storage_manager.config import Settings, get_settings
from storage_manager.mongo_repo import (
    homework_get,
    homework_increment_gold_count,
    homework_list_for_realm,
    realm_delete,
    realm_get,
    realm_insert,
    realm_list,
)
from storage_manager.s3client import delete_prefix, get_bytes, list_keys, make_client, put_bytes


def _realm_from_mongo_doc(doc: dict) -> SimpleNamespace:
    hws = homework_list_for_realm(doc["_id"])
    hw_ns = [
        SimpleNamespace(
            id=h["_id"],
            realm_id=h["realm_id"],
            name=h["name"],
            student_count=h.get("student_count"),
            gold_count=h.get("gold_count"),
        )
        for h in hws
    ]
    return SimpleNamespace(
        id=doc["_id"],
        name=doc["name"],
        path=doc["path"],
        created_at=doc.get("created_at"),
        homeworks=hw_ns,
    )


def _extract_archive(file_path: Path, dest_dir: Path, original_name: str = "") -> None:
    name = original_name or file_path.name
    if name.endswith(".zip"):
        with zipfile.ZipFile(file_path, "r") as zf:
            zf.extractall(dest_dir)
    elif name.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(file_path, "r:*") as tf:
            tf.extractall(dest_dir)
    else:
        raise ValueError(f"Unsupported archive format: {name}")


def _is_homework_dir(d: Path) -> bool:
    has_students_dir = (d / "students").is_dir()
    has_gold_dir = (d / "gold").is_dir()
    has_direct_notebooks = any(d.glob("*.ipynb"))
    return (has_students_dir and has_gold_dir) or (has_direct_notebooks and has_gold_dir) or has_students_dir


def _resolve_realm_root(extracted: Path) -> Path:
    children = [p for p in extracted.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        candidate = children[0]
        sub_dirs = [p for p in candidate.iterdir() if p.is_dir()]
        if any(_is_homework_dir(d) for d in sub_dirs):
            return candidate
        if _is_homework_dir(candidate):
            return extracted
    return extracted


def _scan_homework_dirs(realm_root: Path) -> list[Path]:
    hw_dirs = []
    for child in sorted(realm_root.iterdir()):
        if child.is_dir() and _is_homework_dir(child):
            hw_dirs.append(child)
    return hw_dirs


def _storage_prefix(realm_id: str) -> str:
    return f"{realm_id}/"


def _upload_tree(client: BaseClient, settings: Settings, realm_id: str, realm_root: Path) -> None:
    bucket = settings.REALMS_BUCKET
    prefix = _storage_prefix(realm_id)
    for path in realm_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(realm_root).as_posix()
        key = f"{prefix}{rel}"
        content_type = "application/json" if path.suffix == ".ipynb" else None
        put_bytes(client, bucket, key, path.read_bytes(), content_type=content_type)


async def upload_realm(file: UploadFile, name: str) -> SimpleNamespace:
    settings = get_settings()
    realm_id = str(uuid.uuid4())
    client = make_client(settings)
    tmp_extract = Path(tempfile.mkdtemp(prefix="realm-upload-"))

    try:
        content = await file.read()
        tmp_path = Path(tempfile.mktemp(suffix=".upload"))
        tmp_path.write_bytes(content)

        try:
            _extract_archive(tmp_path, tmp_extract, original_name=file.filename or "")
        finally:
            tmp_path.unlink(missing_ok=True)

        realm_root = _resolve_realm_root(tmp_extract)
        hw_dirs = _scan_homework_dirs(realm_root)

        if not hw_dirs:
            raise HTTPException(
                status_code=422,
                detail="Archive contains no valid homework directories (each must have students/ and gold/ subdirs)",
            )

        hw_rows: list[dict] = []
        for hw_dir in hw_dirs:
            if (hw_dir / "students").is_dir():
                student_count = len(list((hw_dir / "students").glob("*.ipynb")))
            else:
                student_count = len([f for f in hw_dir.glob("*.ipynb")])
            gold_count = len(list((hw_dir / "gold").glob("*.ipynb"))) if (hw_dir / "gold").is_dir() else 0
            hw_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": hw_dir.name,
                    "student_count": student_count,
                    "gold_count": gold_count,
                }
            )

        _upload_tree(client, settings, realm_id, realm_root)
        storage_path = _storage_prefix(realm_id)
        realm_insert(realm_id, name, storage_path, hw_rows)
        doc = realm_get(realm_id)
        assert doc is not None
        return _realm_from_mongo_doc(doc)

    except HTTPException:
        delete_prefix(client, settings.REALMS_BUCKET, _storage_prefix(realm_id))
        raise
    except Exception as exc:
        delete_prefix(client, settings.REALMS_BUCKET, _storage_prefix(realm_id))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp_extract, ignore_errors=True)


def list_realms() -> list[SimpleNamespace]:
    return [_realm_from_mongo_doc(d) for d in realm_list()]


def get_realm(realm_id: str) -> SimpleNamespace:
    doc = realm_get(realm_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Realm not found")
    return _realm_from_mongo_doc(doc)


def _list_notebook_files(client: BaseClient, settings: Settings, realm_id: str, hw_name: str, subdir: str) -> list[dict]:
    prefix = f"{realm_id}/{hw_name}/{subdir}/"
    keys = [k for k in list_keys(client, settings.REALMS_BUCKET, prefix) if k.endswith(".ipynb")]
    files = []
    for key in sorted(keys):
        name = Path(key).stem
        rel = f"{subdir}/{Path(key).name}"
        files.append({"name": name, "path": rel})
    return files


def get_homework_detail(realm_id: str, homework_id: str) -> dict:
    get_realm(realm_id)
    hw_doc = homework_get(realm_id, homework_id)
    if hw_doc is None:
        raise HTTPException(status_code=404, detail="Homework not found")

    settings = get_settings()
    client = make_client(settings)
    hw_name = hw_doc["name"]

    student_files = _list_notebook_files(client, settings, realm_id, hw_name, "students")
    if not student_files:
        prefix = f"{realm_id}/{hw_name}/"
        keys = [k for k in list_keys(client, settings.REALMS_BUCKET, prefix) if k.endswith(".ipynb")]
        student_files = []
        for key in sorted(keys):
            rel = key[len(f"{realm_id}/{hw_name}/") :]
            if "/" in rel:
                continue
            student_files.append({"name": Path(key).stem, "path": Path(key).name})

    gold_files = _list_notebook_files(client, settings, realm_id, hw_name, "gold")

    return {
        "id": hw_doc["_id"],
        "realm_id": hw_doc["realm_id"],
        "name": hw_name,
        "student_count": hw_doc.get("student_count"),
        "gold_count": hw_doc.get("gold_count"),
        "student_files": student_files,
        "gold_files": gold_files,
    }


def get_file_content(realm_id: str, homework_id: str, file_path: str) -> dict:
    realm = get_realm(realm_id)
    hw_doc = homework_get(realm_id, homework_id)
    if hw_doc is None:
        raise HTTPException(status_code=404, detail="Homework not found")

    hw_name = hw_doc["name"]
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file path")

    settings = get_settings()
    key = f"{realm.path}{hw_name}/{file_path}"
    client = make_client(settings)
    try:
        raw = get_bytes(client, settings.REALMS_BUCKET, key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    filename = Path(file_path).name
    if filename.endswith(".ipynb"):
        nb = json.loads(raw.decode("utf-8"))
        cells = []
        for cell in nb.get("cells", []):
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)
            cells.append({
                "cell_type": cell.get("cell_type", "raw"),
                "source": source,
                "outputs": cell.get("outputs", []),
            })
        return {
            "path": file_path,
            "filename": filename,
            "content_type": "notebook",
            "notebook": {"cells": cells, "metadata": nb.get("metadata", {})},
            "text": None,
        }

    return {
        "path": file_path,
        "filename": filename,
        "content_type": "text",
        "notebook": None,
        "text": raw.decode("utf-8", errors="replace"),
    }


async def upload_gold_file(realm_id: str, homework_id: str, file: UploadFile) -> dict:
    get_realm(realm_id)
    hw_doc = homework_get(realm_id, homework_id)
    if hw_doc is None:
        raise HTTPException(status_code=404, detail="Homework not found")

    filename = file.filename or "gold.ipynb"
    if not filename.endswith(".ipynb"):
        raise HTTPException(status_code=422, detail="Only .ipynb files are accepted")

    content = await file.read()
    settings = get_settings()
    client = make_client(settings)
    key = f"{realm_id}/{hw_doc['name']}/gold/{filename}"
    put_bytes(client, settings.REALMS_BUCKET, key, content, content_type="application/json")
    homework_increment_gold_count(homework_id)
    return {"homework_id": homework_id, "path": f"gold/{filename}", "filename": filename}


def delete_realm(realm_id: str) -> None:
    get_realm(realm_id)
    settings = get_settings()
    client = make_client(settings)
    delete_prefix(client, settings.REALMS_BUCKET, _storage_prefix(realm_id))
    realm_delete(realm_id)
