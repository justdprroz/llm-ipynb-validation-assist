"""Optional bearer auth for public API when ``ENV=prod`` and ``PROD_PUBLIC_AUTH``."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException

from app.config import get_settings


async def require_user_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """When PROD_PUBLIC_AUTH=1, require ``Authorization: Bearer``."""
    settings = get_settings()
    if settings.ENV != "prod" or not settings.PROD_PUBLIC_AUTH:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    return authorization.removeprefix("Bearer ").strip()


async def public_route_auth(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Dependency for ``/api/v1`` routes: enforce bearer in production when enabled."""
    await require_user_token(authorization)
