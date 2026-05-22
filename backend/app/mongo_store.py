"""MongoDB access and index bootstrap."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from pymongo import MongoClient
from pymongo.database import Database

from app.config import get_settings

if TYPE_CHECKING:
    pass

_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    global _client
    settings = get_settings()
    if not settings.MONGO_URI:
        raise RuntimeError("MONGO_URI is required")
    if _client is None:
        _client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_mongo_db() -> Database:
    settings = get_settings()
    return get_mongo_client()[settings.MONGO_DB]


def ensure_mongo_indexes() -> None:
    db = get_mongo_db()
    db.realms.create_index("name", unique=True)
    db.homeworks.create_index([("realm_id", 1), ("name", 1)], unique=True)
    db.homeworks.create_index("realm_id")
    db.pipelines.create_index([("name", 1), ("version", 1)], unique=True)
    db.pipelines.create_index("status")
    db.runs.create_index("pipeline_id")
    db.runs.create_index("homework_id")
    db.runs.create_index([("status", 1), ("created_at", -1)])
    db.run_results.create_index([("run_id", 1), ("student_id", 1)], unique=True)
    db.run_results.create_index("run_id")
    db.inference_profiles.create_index("name", unique=True)
    db.git_credentials.create_index("host")


def close_mongo_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
