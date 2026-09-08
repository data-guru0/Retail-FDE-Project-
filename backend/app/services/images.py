"""Upload hardening: content-type sniff (magic bytes via `filetype`), size cap,
Pillow re-encode to strip EXIF / any embedded payload. Returns clean JPEG bytes.
"""
from __future__ import annotations

import io

import filetype
from fastapi import HTTPException
from PIL import Image

MAX_BYTES = 8 * 1024 * 1024
_ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def sniff(data: bytes) -> str:
    kind = filetype.guess(data)
    if kind is None or kind.mime not in _ALLOWED:
        raise HTTPException(415, "unsupported or unrecognised image format")
    return kind.mime


def clean_image(data: bytes) -> tuple[bytes, str]:
    if not data:
        raise HTTPException(400, "empty upload")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"image over {MAX_BYTES // (1024 * 1024)} MB")
    sniff(data)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"unreadable image: {e}") from e
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)  # re-encode: no EXIF, no trailing data
    return out.getvalue(), "image/jpeg"
