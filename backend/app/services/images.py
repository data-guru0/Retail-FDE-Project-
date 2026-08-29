"""Upload hardening: magic-byte sniff, size cap, Pillow re-encode to strip
EXIF / any embedded payload. Returns clean JPEG bytes.
"""
from __future__ import annotations

import io

from fastapi import HTTPException
from PIL import Image

MAX_BYTES = 8 * 1024 * 1024
_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # RIFF....WEBP
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}


def sniff(data: bytes) -> str:
    for magic, mime in _MAGIC.items():
        if data.startswith(magic):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    raise HTTPException(415, "unsupported or unrecognised image format")


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
