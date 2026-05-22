"""Notebook parsing into rich cells, with safeguards against hostile output.

Cell shape (dict):
  {"cell_id": int, "type": "md"|"code"|"output"|"image",
   "content": str}                       # md/code/output
  {"cell_id": int, "type": "image", "data": b64, "media_type": str}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from llm_notebook_ng.images import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_DIM,
    b64_byte_len,
    downscale_b64_image,
)

DEFAULT_MAX_OUTPUT_CHARS = 2000
DEFAULT_HTML_HARD_CAP = 50_000

_DANGEROUS = re.compile(
    r"<\s*script|</\s*script|javascript:|\son\w+\s*=|<\s*iframe|data:text/html",
    re.IGNORECASE,
)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]*\n[ \t\n]*")


def _new_stats() -> dict[str, int]:
    return {
        "html_stripped": 0,
        "outputs_truncated": 0,
        "images_found": 0,
        "images_downscaled": 0,
        "images_skipped": 0,
    }


def truncate_text(content: str, max_chars: int) -> tuple[str, bool]:
    if len(content) <= max_chars:
        return content, False
    half = max_chars // 2
    body = (
        content[:half]
        + f"\n... [truncated {len(content) - max_chars} chars] ...\n"
        + content[-half:]
    )
    return body, True


def _sanitize_html(
    html: str, *, max_chars: int, hard_cap: int, stats: dict[str, int]
) -> str:
    if _DANGEROUS.search(html) or len(html) > hard_cap:
        stats["html_stripped"] += 1
        return f"[HTML/JS output stripped: {len(html)} chars]"
    text = _TAG.sub(" ", html)
    text = _WS.sub("\n", text).strip()
    text, truncated = truncate_text(text, max_chars)
    if truncated:
        stats["outputs_truncated"] += 1
    return text


def _text_output(
    raw_output: dict,
    data: dict,
    *,
    max_chars: int,
    hard_cap: int,
    stats: dict[str, int],
) -> str | None:
    otype = raw_output.get("output_type", "")
    if otype == "stream":
        text = raw_output.get("text")
        if text is None:
            return None
        body, truncated = truncate_text("".join(text), max_chars)
        if truncated:
            stats["outputs_truncated"] += 1
        return body
    if otype == "error":
        tb = raw_output.get("traceback") or []
        body, truncated = truncate_text(_TAG.sub("", "\n".join(tb)), max_chars)
        if truncated:
            stats["outputs_truncated"] += 1
        return (
            body
            or f"{raw_output.get('ename', 'Error')}: {raw_output.get('evalue', '')}"
        )
    if otype in ("display_data", "execute_result"):
        # Prefer text/plain — never forward raw text/html unsanitized.
        if "text/plain" in data:
            body, truncated = truncate_text("".join(data["text/plain"]), max_chars)
            if truncated:
                stats["outputs_truncated"] += 1
            return body
        if "text/html" in data:
            return _sanitize_html(
                "".join(data["text/html"]),
                max_chars=max_chars,
                hard_cap=hard_cap,
                stats=stats,
            )
    return None


def parse_notebook(
    path: str | Path,
    *,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    html_hard_cap: int = DEFAULT_HTML_HARD_CAP,
) -> tuple[list[dict], dict[str, int]]:
    stats = _new_stats()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cells_in: list[dict] = raw.get("cells", [])
    out: list[dict] = []

    for cid, cell in enumerate(cells_in):
        ctype = cell.get("cell_type")
        src = cell.get("source")
        if isinstance(src, list):
            src = "".join(src)
        src = src or ""

        if ctype == "markdown":
            out.append({"cell_id": cid, "type": "md", "content": src})
            continue
        if ctype != "code":
            continue

        out.append({"cell_id": cid, "type": "code", "content": src})

        for raw_output in cell.get("outputs", []):
            data = raw_output.get("data", {})
            for key in ("image/png", "image/jpeg"):
                if key in data:
                    stats["images_found"] += 1
                    out.append(
                        {
                            "cell_id": cid,
                            "type": "image",
                            "data": data[key].strip()
                            if isinstance(data[key], str)
                            else "".join(data[key]).strip(),
                            "media_type": key,
                        }
                    )
                    break

            text = _text_output(
                raw_output,
                data,
                max_chars=max_output_chars,
                hard_cap=html_hard_cap,
                stats=stats,
            )
            if text is not None:
                out.append({"cell_id": cid, "type": "output", "content": text})

    return out, stats


# ── cell utilities ──


def cells_by_id(cells: list[dict]) -> dict[int, list[dict]]:
    index: dict[int, list[dict]] = {}
    for c in cells:
        index.setdefault(c["cell_id"], []).append(c)
    return index


def slice_cells(index: dict[int, list[dict]], cell_ids: list[int]) -> list[dict]:
    result: list[dict] = []
    for cid in cell_ids or []:
        try:
            result.extend(index.get(int(cid), []))
        except (TypeError, ValueError):
            continue
    return result


def cell_stats(cells: list[dict]) -> dict[str, Any]:
    types: dict[str, int] = {}
    text_chars = 0
    image_bytes = 0
    for c in cells:
        t = c.get("type", "?")
        types[t] = types.get(t, 0) + 1
        if t == "image":
            image_bytes += b64_byte_len(c.get("data", ""))
        else:
            text_chars += len(c.get("content", ""))
    return {
        "count": len(cells),
        "types": types,
        "text_chars": text_chars,
        "image_bytes": image_bytes,
    }


def cells_to_text(cells: list[dict]) -> str:
    lines = []
    for c in cells:
        if c["type"] == "image":
            lines.append(f"{c['cell_id']}: image: [graphical output]")
        else:
            lines.append(f"{c['cell_id']}: {c['type']}: {c.get('content', '')}")
    return "\n".join(lines)


def cells_to_blocks(
    cells: list[dict],
    *,
    max_image_dim: int = DEFAULT_MAX_DIM,
    max_image_bytes: int = DEFAULT_MAX_BYTES,
    max_images: int = 8,
    stats: dict[str, int] | None = None,
) -> list[dict]:
    """Anthropic-style content blocks: text runs interleaved with images."""
    blocks: list[dict] = []
    buf: list[str] = []
    images_used = 0

    def flush() -> None:
        if buf:
            blocks.append({"type": "text", "text": "\n".join(buf) + "\n"})
            buf.clear()

    for c in cells:
        if c["type"] == "image":
            if images_used >= max_images:
                buf.append(f"{c['cell_id']}: image: [omitted: image budget exceeded]")
                continue
            data, media_type, status = downscale_b64_image(
                c["data"],
                c["media_type"],
                max_dim=max_image_dim,
                max_bytes=max_image_bytes,
            )
            if stats is not None and status == "downscaled":
                stats["images_downscaled"] = stats.get("images_downscaled", 0) + 1
            if status == "skipped" or data is None:
                if stats is not None:
                    stats["images_skipped"] = stats.get("images_skipped", 0) + 1
                buf.append(f"{c['cell_id']}: image: [skipped: oversized/undecodable]")
                continue
            flush()
            images_used += 1
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": data,
                    },
                }
            )
        else:
            buf.append(f"{c['cell_id']}: {c['type']}: {c.get('content', '')}")

    flush()
    return blocks


def has_image(cells: list[dict]) -> bool:
    return any(c.get("type") == "image" for c in cells)


# ── gold / blank resolution ──


def find_gold_and_blank(gold_dir: Path) -> tuple[list[Path], Path | None]:
    """Split gold_dir notebooks into (gold solutions, optional blank template)."""
    if not gold_dir.exists():
        return [], None
    notebooks = sorted(gold_dir.glob("*.ipynb"))
    blank: Path | None = None
    gold: list[Path] = []
    for nb in notebooks:
        stem = nb.stem.lower()
        if blank is None and (stem.startswith("blank") or stem.startswith("template")):
            blank = nb
        else:
            gold.append(nb)
    return gold, blank


def derive_skeleton(cells: list[dict]) -> list[dict]:
    """Task skeleton: keep markdown, blank out code, drop outputs/images."""
    skeleton: list[dict] = []
    for c in cells:
        if c["type"] == "md":
            skeleton.append(
                {"cell_id": c["cell_id"], "type": "md", "content": c.get("content", "")}
            )
        elif c["type"] == "code":
            skeleton.append(
                {
                    "cell_id": c["cell_id"],
                    "type": "code",
                    "content": "# (solution omitted)",
                }
            )
    return skeleton
