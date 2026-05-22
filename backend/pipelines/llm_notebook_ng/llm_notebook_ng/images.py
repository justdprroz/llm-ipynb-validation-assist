"""Image normalization: downscale to a token-sane size, guard huge payloads."""

from __future__ import annotations

import base64
import io

from PIL import Image

DEFAULT_MAX_DIM = 1568
DEFAULT_MAX_BYTES = 8 * 1024 * 1024  # decoded-image hard ceiling


def b64_byte_len(b64_data: str) -> int:
    return len(b64_data) * 3 // 4


def downscale_b64_image(
    b64_data: str,
    media_type: str,
    *,
    max_dim: int = DEFAULT_MAX_DIM,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[str | None, str, str]:
    """Return (data, media_type, status).

    status is one of: "ok" (unchanged), "downscaled", "skipped".
    On "skipped" data is None — the caller should emit a text placeholder.
    """
    if b64_byte_len(b64_data) > max_bytes:
        return None, media_type, "skipped"

    try:
        raw = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        return None, media_type, "skipped"

    if max(img.size) <= max_dim:
        return b64_data, media_type, "ok"

    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    fmt = "PNG" if "png" in media_type else "JPEG"
    if fmt == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii"), media_type, "downscaled"
