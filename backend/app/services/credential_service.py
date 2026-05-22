from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException

from app.mongo_store import get_mongo_db
from app.schemas import GitCredentialCreate


def _mdb():
    return get_mongo_db()


def _mask_token(token: str) -> str:
    return "****" + token[-4:] if len(token) > 4 else "****"


def _to_read(cred: SimpleNamespace | dict) -> dict:
    if isinstance(cred, dict):
        return {
            "id": cred["_id"],
            "host": cred["host"],
            "token_preview": _mask_token(cred["token"]),
            "description": cred.get("description"),
            "created_at": cred.get("created_at"),
        }
    return {
        "id": cred.id,
        "host": cred.host,
        "token_preview": _mask_token(cred.token),
        "description": cred.description,
        "created_at": cred.created_at,
    }


def list_credentials() -> list[dict]:
    return [_to_read(c) for c in _mdb().git_credentials.find().sort("host", 1)]


def create_credential(data: GitCredentialCreate) -> dict:
    doc = {
        "_id": str(uuid.uuid4()),
        "host": data.host,
        "token": data.token,
        "description": data.description,
        "created_at": datetime.utcnow(),
    }
    _mdb().git_credentials.insert_one(doc)
    return _to_read(doc)


def delete_credential(credential_id: str) -> None:
    r = _mdb().git_credentials.delete_one({"_id": credential_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Credential not found")


def get_credential_for_host(host: str) -> SimpleNamespace | None:
    doc = _mdb().git_credentials.find_one({"host": host})
    if doc is None:
        return None
    return SimpleNamespace(id=doc["_id"], host=doc["host"], token=doc["token"])
