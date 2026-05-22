"""Merge server defaults with per-run pipeline_config for RunContext.config."""

from __future__ import annotations

from typing import Any

from gradelab_contracts.pipeline_run_defaults import PIPELINE_RUN_CONFIG_DEFAULTS


def merge_pipeline_run_config(user: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(PIPELINE_RUN_CONFIG_DEFAULTS)
    if user:
        merged.update(user)
    return merged
