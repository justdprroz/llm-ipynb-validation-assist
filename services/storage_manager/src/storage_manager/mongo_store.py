from __future__ import annotations

from functools import lru_cache
from typing import Any

from pymongo import MongoClient

from storage_manager.config import Settings, get_settings


@lru_cache
def get_mongo_client() -> MongoClient:
    settings = get_settings()
    return MongoClient(settings.MONGO_URI)


def get_mongo_db() -> Any:
    settings = get_settings()
    return get_mongo_client()[settings.MONGO_DB]


def ensure_mongo_indexes() -> None:
    db = get_mongo_db()
    db.homeworks.create_index([("realm_id", 1), ("name", 1)], unique=True)
    db.homeworks.create_index("realm_id")
