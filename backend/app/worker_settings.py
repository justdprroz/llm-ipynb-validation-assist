"""ARQ worker (same codebase as API — run in executor container)."""

from __future__ import annotations

import asyncio
import os
import urllib.parse

from arq.connections import RedisSettings

from app.services import run_service


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


async def execute_run_job(_ctx: dict, run_id: str) -> None:
    await asyncio.to_thread(run_service.execute_run, run_id)


class WorkerSettings:
    redis_settings = _redis_settings_from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
    functions = [execute_run_job]
    # arq defaults to a 300s job_timeout, which kills any non-trivial LLM
    # grading pipeline mid-run and leaves the run stuck at status "running".
    # Give jobs a generous, env-overridable ceiling instead.
    job_timeout = int(os.environ.get("RUN_JOB_TIMEOUT", "5400"))
    # Do not silently re-run a timed-out grading job 5x (arq default) — that
    # burns inference tokens and worsens provider throttling.
    max_tries = 1
    keep_result = int(os.environ.get("ARQ_KEEP_RESULT", "3600"))
