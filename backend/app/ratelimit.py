"""Shared slowapi limiter.

- A global default (`SlowAPIMiddleware` in `app.main`) caps every request by
  client IP *before* route handling — so an unauthenticated flood is throttled
  at the edge.
- Stricter per-route caps: decorate the endpoint `@limiter.limit("12/minute")`
  and give it a `request: Request` parameter.

Keyed by client IP; in-memory store (single node).
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1200/minute"],
)
