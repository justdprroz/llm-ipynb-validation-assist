"""CRUD helpers for realm/homework metadata in MongoDB."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from storage_manager.mongo_store import get_mongo_db


def realm_insert(realm_id: str, name: str, path: str, homeworks: list[dict[str, Any]]) -> None:
    db = get_mongo_db()
    now = datetime.utcnow()
    db.realms.insert_one({"_id": realm_id, "name": name, "path": path, "created_at": now})
    for hw in homeworks:
        db.homeworks.insert_one(
            {
                "_id": hw["id"],
                "realm_id": realm_id,
                "name": hw["name"],
                "student_count": hw.get("student_count"),
                "gold_count": hw.get("gold_count"),
            }
        )


def realm_list() -> list[dict[str, Any]]:
    return list(get_mongo_db().realms.find())


def realm_get(realm_id: str) -> dict[str, Any] | None:
    return get_mongo_db().realms.find_one({"_id": realm_id})


def realm_delete(realm_id: str) -> None:
    db = get_mongo_db()
    db.homeworks.delete_many({"realm_id": realm_id})
    db.realms.delete_one({"_id": realm_id})


def homework_get(realm_id: str, homework_id: str) -> dict[str, Any] | None:
    return get_mongo_db().homeworks.find_one({"_id": homework_id, "realm_id": realm_id})


def homework_list_for_realm(realm_id: str) -> list[dict[str, Any]]:
    return list(get_mongo_db().homeworks.find({"realm_id": realm_id}))


def homework_increment_gold_count(homework_id: str, delta: int = 1) -> None:
    get_mongo_db().homeworks.update_one({"_id": homework_id}, {"$inc": {"gold_count": delta}})
