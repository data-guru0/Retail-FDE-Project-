"""Liveness + a real deep health check that actually talks to every dependency."""
from __future__ import annotations

import asyncio

import boto3
import httpx
import redis.asyncio as aioredis
from botocore.client import Config as BotoConfig
from fastapi import APIRouter
from sqlalchemy import text

from app.db import Session
from app.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


async def _check_postgres() -> dict:
    async with Session() as s:
        one = (await s.execute(text("SELECT 1"))).scalar_one()
        tables = (
            await s.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
            )
        ).scalar_one()
    return {"ok": one == 1, "public_tables": tables}


async def _check_redis() -> dict:
    r = aioredis.from_url(get_settings().redis_url)
    try:
        await r.set("rg:health", "1", ex=10)
        v = await r.get("rg:health")
        pong = await r.ping()
        return {"ok": bool(pong) and v == b"1"}
    finally:
        await r.aclose()


async def _check_qdrant() -> dict:
    async with httpx.AsyncClient(timeout=5) as c:
        resp = await c.get(f"{get_settings().qdrant_url}/collections")
        return {"ok": resp.status_code == 200, "collections": len(resp.json()["result"]["collections"])}


def _check_minio_sync() -> dict:
    s = get_settings()
    cli = boto3.client(
        "s3",
        endpoint_url=s.minio_endpoint,
        aws_access_key_id=s.minio_access_key,
        aws_secret_access_key=s.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )
    cli.head_bucket(Bucket=s.minio_bucket)
    return {"ok": True, "bucket": s.minio_bucket}


async def _check_minio() -> dict:
    return await asyncio.to_thread(_check_minio_sync)


async def _check_vault() -> dict:
    from app import vault

    tok = vault._client().lookup_token()
    return {"ok": bool(tok["data"]["id"])}


async def _check_http(name: str, url: str) -> dict:
    async with httpx.AsyncClient(timeout=5) as c:
        resp = await c.get(url)
        return {"ok": resp.status_code < 500, "status": resp.status_code}


@router.get("/health/deep")
async def deep() -> dict:
    s = get_settings()
    checks = {
        "postgres": _check_postgres(),
        "redis": _check_redis(),
        "qdrant": _check_qdrant(),
        "minio": _check_minio(),
        "vault": _check_vault(),
        "bifrost": _check_http("bifrost", f"{s.bifrost_url}/metrics"),
        "contextforge": _check_http("contextforge", f"{s.mcp_gateway_url}/health"),
        "opa": _check_http("opa", f"{s.opa_url}/health"),
    }
    results: dict = {}
    for name, coro in checks.items():
        try:
            results[name] = await coro
        except Exception as e:  # noqa: BLE001 — health must report, not raise
            results[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    ok = all(v.get("ok") for v in results.values())
    return {"status": "ok" if ok else "degraded", "checks": results}
