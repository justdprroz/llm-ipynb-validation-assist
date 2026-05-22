"""HTTP client for Storage Manager realm and object APIs."""

from __future__ import annotations

import httpx
from fastapi import HTTPException, UploadFile

from app.config import get_settings


def _base_url() -> str:
    s = get_settings()
    if not s.STORAGE_MANAGER_URL:
        raise HTTPException(status_code=503, detail="STORAGE_MANAGER_URL is not configured")
    return s.STORAGE_MANAGER_URL.rstrip("/")


def _headers() -> dict[str, str]:
    s = get_settings()
    h: dict[str, str] = {}
    if s.STORAGE_MANAGER_TOKEN:
        h["Authorization"] = f"Bearer {s.STORAGE_MANAGER_TOKEN}"
    return h


def _raise_from_response(r: httpx.Response) -> None:
    if r.is_success:
        return
    try:
        detail = r.json().get("detail", r.text)
    except Exception:
        detail = r.text
    raise HTTPException(status_code=r.status_code, detail=detail)


async def upload_realm(file: UploadFile, name: str) -> dict:
    content = await file.read()
    files = {"file": (file.filename or "upload.zip", content, file.content_type or "application/octet-stream")}
    data = {"name": name}
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(
            f"{_base_url()}/v1/realms/upload",
            files=files,
            data=data,
            headers=_headers(),
        )
    _raise_from_response(r)
    return r.json()


def list_realms() -> list[dict]:
    r = httpx.get(f"{_base_url()}/v1/realms", headers=_headers(), timeout=60.0)
    _raise_from_response(r)
    return r.json()


def get_realm(realm_id: str) -> dict:
    r = httpx.get(f"{_base_url()}/v1/realms/{realm_id}", headers=_headers(), timeout=60.0)
    _raise_from_response(r)
    return r.json()


def get_homework_detail(realm_id: str, homework_id: str) -> dict:
    r = httpx.get(
        f"{_base_url()}/v1/realms/{realm_id}/homeworks/{homework_id}",
        headers=_headers(),
        timeout=60.0,
    )
    _raise_from_response(r)
    return r.json()


def get_file_content(realm_id: str, homework_id: str, file_path: str) -> dict:
    r = httpx.get(
        f"{_base_url()}/v1/realms/{realm_id}/homeworks/{homework_id}/files/{file_path}",
        headers=_headers(),
        timeout=60.0,
    )
    _raise_from_response(r)
    return r.json()


async def upload_gold_file(realm_id: str, hw_id: str, file: UploadFile) -> dict:
    content = await file.read()
    files = {"file": (file.filename or "gold.ipynb", content, "application/json")}
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{_base_url()}/v1/realms/{realm_id}/homeworks/{hw_id}/gold",
            files=files,
            headers=_headers(),
        )
    _raise_from_response(r)
    return r.json()


def delete_realm(realm_id: str) -> None:
    r = httpx.delete(f"{_base_url()}/v1/realms/{realm_id}", headers=_headers(), timeout=120.0)
    _raise_from_response(r)
