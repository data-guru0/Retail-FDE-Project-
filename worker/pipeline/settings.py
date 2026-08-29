"""Worker config — same Vault-backed pattern as the backend."""
from __future__ import annotations

import os
from functools import lru_cache

import hvac
from pydantic import BaseModel

_KV_MOUNT = "secret"
_BASE = "returnguard"


def _vault() -> hvac.Client:
    c = hvac.Client(url=os.environ["VAULT_ADDR"])
    rid, sid = os.getenv("VAULT_ROLE_ID"), os.getenv("VAULT_SECRET_ID")
    if rid and sid:
        c.auth.approle.login(role_id=rid, secret_id=sid)
    else:
        c.token = os.environ["VAULT_TOKEN"]
    if not c.is_authenticated():
        raise RuntimeError("Vault auth failed")
    return c


@lru_cache(maxsize=16)
def _read(path: str) -> dict:
    return _vault().secrets.kv.v2.read_secret_version(
        mount_point=_KV_MOUNT, path=f"{_BASE}/{path}", raise_on_deleted_version=True
    )["data"]["data"]


class Settings(BaseModel):
    database_url: str
    redis_url: str
    qdrant_url: str
    bifrost_url: str
    openai_api_key: str
    groq_api_key: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    langfuse_host: str
    langfuse_public_key: str
    langfuse_secret_key: str
    mcp_gateway_url: str


@lru_cache
def get_settings() -> Settings:
    db, r, q = _read("db"), _read("redis"), _read("qdrant")
    llm, mn, lf, mcp = _read("llm"), _read("minio"), _read("langfuse"), _read("mcp")
    return Settings(
        database_url=db["url_async"],
        redis_url=r["url"],
        qdrant_url=q["url"],
        bifrost_url=llm["bifrost_url"],
        openai_api_key=llm.get("openai_api_key", ""),
        groq_api_key=llm.get("groq_api_key", ""),
        minio_endpoint=mn["endpoint"],
        minio_access_key=mn["access_key"],
        minio_secret_key=mn["secret_key"],
        minio_bucket=mn["bucket"],
        langfuse_host=lf["host"],
        langfuse_public_key=lf["public_key"],
        langfuse_secret_key=lf["secret_key"],
        mcp_gateway_url=mcp["gateway_url"],
    )


def redis_settings():
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(get_settings().redis_url)
