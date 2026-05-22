"""Enqueue ARQ jobs when RUN_EXECUTOR=arq."""

from __future__ import annotations

import asyncio
import urllib.parse

from arq import create_pool
from arq.connections import RedisSettings

from app.config import get_settings


def _redis_settings_from_url(url: str) -> RedisSettings:
    u = urllib.parse.urlparse(url)
    path = (u.path or "/0").strip("/")
    database = int(path) if path.isdigit() else 0
    return RedisSettings(
        host=u.hostname or "localhost",
        port=u.port or 6379,
        database=database,
        password=u.password,
    )


def enqueue_execute_run(run_id: str) -> None:
    settings = get_settings()
    if not settings.REDIS_URL:
        raise RuntimeError("REDIS_URL required for RUN_EXECUTOR=arq")

    async def _go() -> None:
        pool = await create_pool(_redis_settings_from_url(settings.REDIS_URL))
        try:
            await pool.enqueue_job("execute_run_job", run_id)
        finally:
            await pool.close()

    asyncio.run(_go())
