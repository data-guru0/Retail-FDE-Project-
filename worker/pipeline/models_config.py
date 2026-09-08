"""Config-driven model ids + per-agent model grants.

Every model call names a *role*, never a literal model string. Each agent is
granted a set of roles; `assert_grant()` refuses a call for a role an agent
doesn't hold. The grant decision is made by **OPA**
(`data.returnguard.authz.allow_model`, `infra/opa/authz.rego`); `AGENT_MODEL_GRANTS`
below is the offline mirror used as a fail-closed fallback when OPA is
unreachable. It is also mirrored by the per-agent Bifrost virtual keys created by
`scripts/bifrost_setup.py` (which additionally carry spend + rate limits).

Groq's mid-2026 catalog dropped the llama-3.x ids; the served replacements are
the gpt-oss models. See worker/pipeline/llm.py + infra/opa/.
"""
from __future__ import annotations

import os

from pipeline import opa

_DEFAULTS = {
    "fast": "groq/openai/gpt-oss-20b",      # intake, data-quality, planner
    "reason": "groq/openai/gpt-oss-120b",   # policy, behaviour, decision
    "deep": "openai/gpt-4o-mini",           # critic, explanation
    "vision": "openai/gpt-4o",              # borderline image checks (image only)
    "embed": "openai/text-embedding-3-small",
}

_FALLBACKS = {
    "fast": ["openai/gpt-4o-mini"],
    "reason": ["openai/gpt-4o-mini"],
    "deep": ["openai/gpt-4o"],
    "vision": ["openai/gpt-4o-mini"],
    "embed": [],
}

# Offline mirror of infra/opa/authz.rego `model_grants` (fail-closed fallback).
AGENT_MODEL_GRANTS: dict[str, set[str]] = {
    "planner": {"fast"},
    "intake": {"fast"},
    "policy": {"reason", "embed"},
    "image": {"vision"},
    "behavior": {"reason"},
    "decision": {"reason", "deep"},
    "critic": {"deep"},
    "explanation": {"deep"},
}


def model(role: str) -> str:
    return os.getenv(f"RG_MODEL_{role.upper()}", _DEFAULTS[role])


def fallbacks(role: str) -> list[str]:
    return _FALLBACKS.get(role, [])


def is_granted(agent: str | None, role: str) -> bool:
    """OPA decides; if OPA is unreachable, fall back to the offline mirror.
    `agent=None` (utility callers like the policy re-embed job) is unrestricted."""
    if agent is None:
        return True
    return opa.allowed(
        "returnguard/authz/allow_model", {"agent": agent, "role": role},
        offline=role in AGENT_MODEL_GRANTS.get(agent, set()),
    )


def assert_grant(agent: str | None, role: str) -> None:
    """Raise if `agent` is not permitted to use `role`."""
    if agent is None:
        return
    if not is_granted(agent, role):
        raise PermissionError(
            f"agent '{agent}' is not granted the '{role}' model role "
            f"(granted: {sorted(AGENT_MODEL_GRANTS.get(agent, set())) or 'none'})"
        )
