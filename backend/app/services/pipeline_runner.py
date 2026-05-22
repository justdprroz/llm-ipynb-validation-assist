"""Pipeline subprocess helpers (shared by Mongo run path and legacy SQLite path if kept)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

from pydantic import ValidationError

from app.schemas import PipelineOutput

_PIPELINE_OUTPUT_HEAD = re.compile(r"\{\s*\"results\"\s*:")


def parse_pipeline_stdout(stdout: str) -> PipelineOutput:
    if not stdout or not stdout.strip():
        raise ValueError("pipeline stdout is empty")

    decoder = json.JSONDecoder()

    def try_at(start: int) -> PipelineOutput | None:
        chunk = stdout[start:].lstrip()
        if not chunk.startswith("{"):
            return None
        try:
            obj, _end = decoder.raw_decode(chunk)
        except json.JSONDecodeError:
            return None
        try:
            return PipelineOutput.model_validate(obj)
        except ValidationError:
            return None

    for m in reversed(list(_PIPELINE_OUTPUT_HEAD.finditer(stdout))):
        parsed = try_at(m.start())
        if parsed is not None:
            return parsed

    lead = len(stdout) - len(stdout.lstrip())
    parsed = try_at(lead)
    if parsed is not None:
        return parsed

    pos = len(stdout)
    while True:
        pos = stdout.rfind("{", 0, pos)
        if pos == -1:
            break
        parsed = try_at(pos)
        if parsed is not None:
            return parsed

    raise ValueError(
        "pipeline stdout did not contain a valid PipelineOutput JSON object "
        f"(tail preview: {stdout[-400:]!r})"
    )


def run_pipeline_subprocess(
    cmd: list[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Spawn pipeline with stderr inherited; stdout buffered for JSON parsing."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
        env=env,
    )

    stdout_parts: list[str] = []
    if proc.stdout:
        for line in proc.stdout:
            stdout_parts.append(line)
            sys.stderr.write(line)
            sys.stderr.flush()

    rc = proc.wait()
    return subprocess.CompletedProcess(cmd, rc, "".join(stdout_parts), None)
