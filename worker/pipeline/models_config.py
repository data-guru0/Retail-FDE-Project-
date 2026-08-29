"""Config-driven model ids. Every model call names one of these roles, never a
literal model string. Override any of them with RG_MODEL_<ROLE> env vars.

Groq's mid-2026 catalog dropped the llama-3.x ids in CLAUDE.md's table; the
served replacements are the gpt-oss models (still on Groq, still a real upstream
call). Deep reasoning stays on OpenAI. See ADR-0007 / ADR-0010.
"""
from __future__ import annotations

import os

_DEFAULTS = {
    # fast, high-volume (intake, data-quality)
    "fast": "groq/openai/gpt-oss-20b",
    # policy / behaviour reasoning
    "reason": "groq/openai/gpt-oss-120b",
    # deep reasoning (decision, critic, explanation) + borderline vision
    "deep": "openai/gpt-4o-mini",
    "vision": "openai/gpt-4o",
    "embed": "openai/text-embedding-3-small",
}

# Bifrost fallback chains per role: a Groq error yields a real OpenAI response.
_FALLBACKS = {
    "fast": ["openai/gpt-4o-mini"],
    "reason": ["openai/gpt-4o-mini"],
    "deep": ["openai/gpt-4o"],
    "vision": ["openai/gpt-4o-mini"],
    "embed": [],
}


def model(role: str) -> str:
    return os.getenv(f"RG_MODEL_{role.upper()}", _DEFAULTS[role])


def fallbacks(role: str) -> list[str]:
    return _FALLBACKS.get(role, [])
