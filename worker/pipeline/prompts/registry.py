"""Load versioned prompt files + expose a content hash logged with every agent_run."""
from __future__ import annotations

import hashlib
import pathlib
from functools import lru_cache

_DIR = pathlib.Path(__file__).parent


@lru_cache(maxsize=64)
def load(name: str) -> tuple[str, str, str]:
    """Return (body, version, sha256[:16]) for prompts/<name>.md."""
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8")
    version = "0"
    for line in text.splitlines()[:5]:
        if line.lower().startswith("version:"):
            version = line.split(":", 1)[1].strip()
            break
    body = text.split("\n", 1)[1].strip() if text.lower().startswith("version:") else text
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    return body, version, digest


def prompt_version(name: str) -> str:
    _, v, h = load(name)
    return f"{name}.v{v}.{h}"
