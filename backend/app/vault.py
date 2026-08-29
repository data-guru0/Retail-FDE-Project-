"""Real Vault client. Reads every runtime secret from Vault at boot.

Auth precedence:
  1. AppRole (VAULT_ROLE_ID / VAULT_SECRET_ID) — the production path, one role per service.
  2. VAULT_TOKEN — dev-mode fallback (Vault dev container root token).
"""
from __future__ import annotations

import os
from functools import lru_cache

import hvac

KV_MOUNT = "secret"
BASE = "returnguard"


def _client() -> hvac.Client:
    addr = os.environ["VAULT_ADDR"]
    c = hvac.Client(url=addr)
    role_id = os.getenv("VAULT_ROLE_ID")
    secret_id = os.getenv("VAULT_SECRET_ID")
    if role_id and secret_id:
        c.auth.approle.login(role_id=role_id, secret_id=secret_id)
    else:
        c.token = os.environ["VAULT_TOKEN"]
    if not c.is_authenticated():
        raise RuntimeError("Vault authentication failed")
    return c


@lru_cache(maxsize=32)
def read(path: str) -> dict:
    """Read secret/<BASE>/<path> (KV v2). Cached for process lifetime."""
    resp = _client().secrets.kv.v2.read_secret_version(
        mount_point=KV_MOUNT, path=f"{BASE}/{path}", raise_on_deleted_version=True
    )
    return resp["data"]["data"]
