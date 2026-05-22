"""Liveness and readiness probes for orchestration and observability."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, Any]:
    """Readiness: Mongo, Redis (ARQ), optional StorageManager."""
    settings = get_settings()
    checks: dict[str, bool] = {}
    ok = True

    try:
        from pymongo import MongoClient  # noqa: PLC0415

        client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2500)
        client.admin.command("ping")
        client.close()
        checks["mongo"] = True
    except Exception:
        checks["mongo"] = False
        ok = False

    try:
        import redis as redis_lib  # noqa: PLC0415

        r = redis_lib.Redis.from_url(settings.REDIS_URL, socket_timeout=2.0)
        r.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False
        ok = False

    if settings.STORAGE_BACKEND == "minio" and settings.STORAGE_MANAGER_URL:
        try:
            import httpx  # noqa: PLC0415

            headers = {}
            if settings.STORAGE_MANAGER_TOKEN:
                headers["Authorization"] = f"Bearer {settings.STORAGE_MANAGER_TOKEN}"
            r = httpx.get(
                f"{settings.STORAGE_MANAGER_URL.rstrip('/')}/health",
                headers=headers,
                timeout=2.0,
            )
            checks["storage_manager"] = r.status_code == 200
            if not checks["storage_manager"]:
                ok = False
        except Exception:
            checks["storage_manager"] = False
            ok = False

    status = "ready" if ok else "not_ready"
    return {"status": status, "checks": checks}
