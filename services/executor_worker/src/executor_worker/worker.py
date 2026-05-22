"""ARQ worker entrypoint — wire Docker + StorageManager + LLMProxy per queue-execution.md."""

from __future__ import annotations

import os
from typing import Any

from arq.connections import RedisSettings


def _redis_settings() -> RedisSettings:
    host = os.environ.get("REDIS_HOST", "redis")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    return RedisSettings(host=host, port=port)


async def execute_run(_ctx: dict[str, Any], job: dict[str, Any]) -> str:
    """Process one run job (payload shape: gradelab.run_job.v1).

    TODO: pull artifacts from StorageManager, ``docker run`` pipeline image,
    POST results to Backend internal API.
    """
    return str(job.get("run_id", ""))


class WorkerSettings:
    redis_settings = _redis_settings()
    functions = [execute_run]
