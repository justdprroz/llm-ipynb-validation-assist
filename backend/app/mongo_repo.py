"""CRUD helpers for MongoDB persistence (mirrors SQL semantics)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId

from app.mongo_store import get_mongo_db


def oid() -> str:
    return str(ObjectId())


def pipeline_insert(doc: dict[str, Any]) -> None:
    get_mongo_db().pipelines.insert_one(doc)


def pipeline_list() -> list[dict[str, Any]]:
    return list(get_mongo_db().pipelines.find())


def pipeline_get(pipeline_id: str) -> dict[str, Any] | None:
    return get_mongo_db().pipelines.find_one({"_id": pipeline_id})


def pipeline_delete(pipeline_id: str) -> None:
    get_mongo_db().pipelines.delete_one({"_id": pipeline_id})


def run_insert(doc: dict[str, Any]) -> None:
    get_mongo_db().runs.insert_one(doc)


def run_get(run_id: str) -> dict[str, Any] | None:
    return get_mongo_db().runs.find_one({"_id": run_id})


def run_update(run_id: str, patch: dict[str, Any]) -> None:
    get_mongo_db().runs.update_one({"_id": run_id}, {"$set": patch})


def run_list(
    pipeline_id: str | None = None,
    homework_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    q: dict[str, Any] = {}
    if pipeline_id:
        q["pipeline_id"] = pipeline_id
    if homework_id:
        q["homework_id"] = homework_id
    if status:
        q["status"] = status
    return list(get_mongo_db().runs.find(q))


def run_results_insert_many(docs: list[dict[str, Any]]) -> None:
    if docs:
        get_mongo_db().run_results.insert_many(docs)


def run_results_for_run(run_id: str) -> list[dict[str, Any]]:
    return list(get_mongo_db().run_results.find({"run_id": run_id}))


def viewer_get(run_id: str) -> dict[str, Any] | None:
    return get_mongo_db().run_viewer_adjustments.find_one({"_id": run_id})


def viewer_upsert(run_id: str, payload: str, updated_at: datetime) -> None:
    get_mongo_db().run_viewer_adjustments.update_one(
        {"_id": run_id},
        {"$set": {"payload": payload, "updated_at": updated_at}},
        upsert=True,
    )
