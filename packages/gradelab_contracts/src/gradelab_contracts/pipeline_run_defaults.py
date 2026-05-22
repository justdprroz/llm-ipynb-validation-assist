"""Default RunContext.config keys merged with per-run pipeline_config."""

from __future__ import annotations

from typing import Any

# Shallow merge: user pipeline_config overrides these keys.
# Inference params (temperature, seed, top_p, effort, openrouter_provider) are set on the
# inference profile and injected by the backend; they must not be specified here.
PIPELINE_RUN_CONFIG_DEFAULTS: dict[str, Any] = {
    "debug": False,
    "retry": 3,
    "concurrency": 8,
}

PIPELINE_RUN_CONFIG_DESCRIPTION = (
    "Operational knobs merged into RunContext.config for pipeline subprocesses. "
    "debug: emit extra logs; retry: per-student LLM retry count; concurrency: parallel students. "
    "Inference params (temperature, seed, top_p, effort, openrouter_provider, max_tokens) "
    "are configured on the inference profile and injected automatically — do not set them here."
)
