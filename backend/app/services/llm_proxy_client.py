"""HTTP client for LLM Proxy inference profile APIs."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.schemas import InferenceCredentials, InferenceProfileCreate


def _base_url() -> str:
    s = get_settings()
    if not s.LLMPROXY_URL:
        raise HTTPException(status_code=503, detail="LLMPROXY_URL is not configured")
    return s.LLMPROXY_URL.rstrip("/")


def _headers() -> dict[str, str]:
    s = get_settings()
    h: dict[str, str] = {}
    if s.LLMPROXY_SERVICE_TOKEN:
        h["Authorization"] = f"Bearer {s.LLMPROXY_SERVICE_TOKEN}"
    return h


def _raise_from_response(r: httpx.Response) -> None:
    if r.is_success:
        return
    try:
        detail = r.json().get("detail", r.text)
    except Exception:
        detail = r.text
    raise HTTPException(status_code=r.status_code, detail=detail)


def list_profiles() -> list[dict]:
    r = httpx.get(f"{_base_url()}/v1/inference-profiles", headers=_headers(), timeout=30.0)
    _raise_from_response(r)
    return r.json()


def create_profile(data: InferenceProfileCreate) -> dict:
    r = httpx.post(
        f"{_base_url()}/v1/inference-profiles",
        json=data.model_dump(),
        headers=_headers(),
        timeout=30.0,
    )
    _raise_from_response(r)
    return r.json()


def delete_profile(profile_id: str) -> None:
    r = httpx.delete(
        f"{_base_url()}/v1/inference-profiles/{profile_id}",
        headers=_headers(),
        timeout=30.0,
    )
    _raise_from_response(r)


def get_profile(profile_id: str) -> SimpleNamespace:
    r = httpx.get(
        f"{_base_url()}/v1/inference-profiles/{profile_id}/resolve",
        headers=_headers(),
        timeout=30.0,
    )
    _raise_from_response(r)
    data = r.json()
    return SimpleNamespace(
        id=data["id"],
        name=data["name"],
        provider=data["provider"],
        model=data["model"],
        api_key=data["api_key"],
        yc_folder=data.get("yc_folder"),
        description=data.get("description"),
        is_dummy=data.get("is_dummy", False),
        created_at=None,
        temperature=data.get("temperature"),
        top_p=data.get("top_p"),
        seed=data.get("seed"),
        max_tokens=data.get("max_tokens"),
        openrouter_provider=data.get("openrouter_provider"),
        effort=data.get("effort"),
    )


def profile_to_credentials(prof: SimpleNamespace) -> InferenceCredentials:
    return InferenceCredentials(
        provider=prof.provider,
        model=prof.model,
        api_key=prof.api_key,
        yc_folder=prof.yc_folder,
        profile_id=prof.id,
        profile_name=prof.name,
        is_dummy=prof.is_dummy,
    )
