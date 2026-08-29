"""Redis pub/sub for live agent-trace events (powers the dashboard WebSocket)."""
from __future__ import annotations

import json

import redis.asyncio as aioredis

from pipeline.settings import get_settings

_r: aioredis.Redis | None = None


def r() -> aioredis.Redis:
    global _r
    if _r is None:
        _r = aioredis.from_url(get_settings().redis_url)
    return _r


def channel(return_id: str) -> str:
    return f"rg:events:{return_id}"


async def publish_event(return_id: str, event: dict) -> None:
    await r().publish(channel(return_id), json.dumps(event, default=str))
