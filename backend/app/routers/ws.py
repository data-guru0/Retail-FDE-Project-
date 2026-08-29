"""Live agent-trace: WebSocket + a plain REST fallback.

The worker writes each pipeline step to `agent_run_events` AND publishes it to the
Redis channel `rg:events:<return_id>`. On connect we replay the rows already in
the DB, then stream new ones off Redis.
"""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from app.db import Session, get_session
from app.settings import get_settings

router = APIRouter(tags=["ws"])


async def _existing_events(return_id: str) -> list[dict]:
    async with Session() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT seq, agent, kind, payload, "
                    "extract(epoch from created_at)::float8 AS ts "
                    "FROM agent_run_events WHERE return_id = :rid ORDER BY seq"
                ),
                {"rid": return_id},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/returns/{return_id}/events")
async def events(return_id: str, session=Depends(get_session)) -> list[dict]:
    return await _existing_events(return_id)


@router.websocket("/ws/returns/{return_id}")
async def ws_return_trace(ws: WebSocket, return_id: str) -> None:
    await ws.accept()
    for ev in await _existing_events(return_id):
        await ws.send_json({"replayed": True, **ev})

    r = aioredis.from_url(get_settings().redis_url)
    pubsub = r.pubsub()
    await pubsub.subscribe(f"rg:events:{return_id}")
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20)
            payload = {"heartbeat": True} if msg is None else {
                "replayed": False, **json.loads(msg["data"])
            }
            await ws.send_json(payload)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:  # noqa: BLE001 — client vanished; nothing to do
        pass
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()
        await r.aclose()
        await asyncio.sleep(0)
