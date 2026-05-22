"""Single-file JSON cache in the run scratch dir for resumable stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CACHE_NAME = "_ng_cache.json"


def load_cache(scratch_dir: Path) -> dict[str, Any]:
    path = scratch_dir / _CACHE_NAME
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(scratch_dir: Path, cache: dict[str, Any]) -> None:
    path = scratch_dir / _CACHE_NAME
    path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
