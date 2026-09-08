"""Thin client for the OPA policy engine (sidecar container).

OPA is the policy decision point for:
  * the GovernanceGate route  — data.returnguard.governance.decision
  * per-agent tool grants      — data.returnguard.authz.allow_tool
  * per-agent model grants     — data.returnguard.authz.allow_model

Policies live in `infra/opa/*.rego`. Callers **fail closed**: if OPA can't be
reached, `query()` returns None and the caller escalates / denies (mcp_client
and models_config keep an offline copy of the grant maps for that path).
"""
from __future__ import annotations

import os

import httpx
import structlog

log = structlog.get_logger()

_URL = os.getenv("RG_OPA_URL", "http://opa:8181").rstrip("/")


def query(path: str, input_doc: dict):
    """POST to /v1/data/<path> with {"input": ...}; return the `result` value.

    Returns None on any transport / HTTP error — callers must fail closed.
    """
    try:
        r = httpx.post(f"{_URL}/v1/data/{path}",
                       json={"input": input_doc}, timeout=5)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:  # noqa: BLE001 — policy must degrade, not crash
        log.warning("opa.unreachable", path=path, error=f"{type(e).__name__}: {e}")
        return None


def allowed(path: str, input_doc: dict, *, offline: bool) -> bool:
    """Boolean OPA query. On OPA failure, return the `offline` fallback verdict."""
    res = query(path, input_doc)
    return offline if res is None else bool(res)
