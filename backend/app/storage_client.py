"""HTTP client for StorageManager when STORAGE_BACKEND=minio."""

from __future__ import annotations

import httpx

from app.config import get_settings


def _headers() -> dict[str, str]:
    s = get_settings()
    h: dict[str, str] = {}
    if s.STORAGE_MANAGER_TOKEN:
        h["Authorization"] = f"Bearer {s.STORAGE_MANAGER_TOKEN}"
    return h


def storage_put_bytes(bucket: str, key: str, data: bytes, content_type: str | None = None) -> None:
    s = get_settings()
    if not s.STORAGE_MANAGER_URL:
        raise RuntimeError("STORAGE_MANAGER_URL required when STORAGE_BACKEND=minio")
    url = f"{s.STORAGE_MANAGER_URL.rstrip('/')}/v1/objects/{bucket}/{key}"
    headers = _headers()
    if content_type:
        headers["Content-Type"] = content_type
    r = httpx.put(url, content=data, headers=headers, timeout=120.0)
    r.raise_for_status()


def storage_get_bytes(bucket: str, key: str) -> bytes:
    s = get_settings()
    if not s.STORAGE_MANAGER_URL:
        raise RuntimeError("STORAGE_MANAGER_URL required when STORAGE_BACKEND=minio")
    url = f"{s.STORAGE_MANAGER_URL.rstrip('/')}/v1/objects/{bucket}/{key}"
    r = httpx.get(url, headers=_headers(), timeout=120.0)
    r.raise_for_status()
    return r.content


def storage_list_keys(bucket: str, prefix: str) -> list[str]:
    s = get_settings()
    if not s.STORAGE_MANAGER_URL:
        raise RuntimeError("STORAGE_MANAGER_URL required when STORAGE_BACKEND=minio")
    url = f"{s.STORAGE_MANAGER_URL.rstrip('/')}/v1/list"
    r = httpx.get(
        url,
        params={"bucket": bucket, "prefix": prefix},
        headers=_headers(),
        timeout=60.0,
    )
    r.raise_for_status()
    return r.json().get("keys", [])


def storage_delete_prefix(bucket: str, prefix: str) -> None:
    for key in storage_list_keys(bucket, prefix):
        url = f"{get_settings().STORAGE_MANAGER_URL.rstrip('/')}/v1/objects/{bucket}/{key}"
        httpx.delete(url, headers=_headers(), timeout=60.0)
