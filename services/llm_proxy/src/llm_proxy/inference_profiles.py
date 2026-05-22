from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

_log = logging.getLogger(__name__)

DUMMY_PROFILE_NAME = "dummy"


class InferenceProfileCreate(BaseModel):
    name: str
    provider: str
    model: str
    api_key: str
    yc_folder: str | None = None
    description: str | None = None
    is_dummy: bool = False
    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int | None = None
    openrouter_provider: dict[str, Any] | None = None
    effort: str | None = None


class InferenceProfileRead(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    api_key_preview: str
    yc_folder: str | None
    description: str | None
    is_dummy: bool
    created_at: datetime | None
    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int | None = None
    openrouter_provider: dict[str, Any] | None = None
    effort: str | None = None


def _mask_key(key: str) -> str:
    return "****" + key[-4:] if len(key) > 4 else "****"


def _to_read(prof: dict) -> dict:
    return {
        "id": prof["_id"],
        "name": prof["name"],
        "provider": prof["provider"],
        "model": prof["model"],
        "api_key_preview": _mask_key(prof["api_key"]),
        "yc_folder": prof.get("yc_folder"),
        "description": prof.get("description"),
        "is_dummy": prof.get("is_dummy", False),
        "created_at": prof.get("created_at"),
        "temperature": prof.get("temperature"),
        "top_p": prof.get("top_p"),
        "seed": prof.get("seed"),
        "max_tokens": prof.get("max_tokens"),
        "openrouter_provider": prof.get("openrouter_provider"),
        "effort": prof.get("effort"),
    }


def list_profiles(db: Any) -> list[dict]:
    return [_to_read(p) for p in db.inference_profiles.find().sort("name", 1)]


def create_profile(db: Any, data: InferenceProfileCreate) -> dict:
    pid = str(uuid.uuid4())
    doc = {
        "_id": pid,
        "name": data.name,
        "provider": data.provider,
        "model": data.model,
        "api_key": data.api_key,
        "yc_folder": data.yc_folder,
        "description": data.description,
        "is_dummy": data.is_dummy,
        "created_at": datetime.utcnow(),
        "temperature": data.temperature,
        "top_p": data.top_p,
        "seed": data.seed,
        "max_tokens": data.max_tokens,
        "openrouter_provider": data.openrouter_provider,
        "effort": data.effort,
    }
    try:
        db.inference_profiles.insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=409,
            detail="An inference profile with this name already exists",
        ) from exc
    except Exception as exc:
        _log.exception("create inference profile failed")
        raise HTTPException(
            status_code=500,
            detail="Could not create inference profile",
        ) from exc
    return _to_read(doc)


def delete_profile(db: Any, profile_id: str) -> None:
    r = db.inference_profiles.delete_one({"_id": profile_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Inference profile not found")


def get_profile(db: Any, profile_id: str) -> dict:
    doc = db.inference_profiles.find_one({"_id": profile_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Inference profile not found")
    return doc


def ensure_dummy_profile(db: Any) -> None:
    if db.inference_profiles.find_one({"name": DUMMY_PROFILE_NAME}):
        return
    db.inference_profiles.insert_one(
        {
            "_id": str(uuid.uuid4()),
            "name": DUMMY_PROFILE_NAME,
            "provider": "or",
            "model": "dummy-model",
            "api_key": "dummy-key-not-for-production",
            "yc_folder": None,
            "description": "No real API calls; pipelines return stub results.",
            "is_dummy": True,
            "created_at": datetime.utcnow(),
        }
    )


def ensure_indexes(db: Any) -> None:
    db.inference_profiles.create_index("name", unique=True)


def resolve_profile(db: Any, profile_id: str) -> dict:
    """Return full credentials for pipeline execution (service-to-service only)."""
    doc = get_profile(db, profile_id)
    return {
        "id": doc["_id"],
        "name": doc["name"],
        "provider": doc["provider"],
        "model": doc["model"],
        "api_key": doc["api_key"],
        "yc_folder": doc.get("yc_folder"),
        "description": doc.get("description"),
        "is_dummy": doc.get("is_dummy", False),
        "temperature": doc.get("temperature"),
        "top_p": doc.get("top_p"),
        "seed": doc.get("seed"),
        "max_tokens": doc.get("max_tokens"),
        "openrouter_provider": doc.get("openrouter_provider"),
        "effort": doc.get("effort"),
    }
