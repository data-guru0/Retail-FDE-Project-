"""Runtime configuration. Secret material comes from Vault (app.vault);
non-secret wiring comes from the environment. Nothing secret is defaulted here.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel

from app import vault


class Settings(BaseModel):
    env: str

    database_url: str            # async (psycopg) DSN
    database_url_sync: str       # sync DSN for Alembic
    redis_url: str

    qdrant_url: str

    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str

    bifrost_url: str
    openai_api_key: str
    groq_api_key: str

    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_internal_url: str
    keycloak_audience: str

    langfuse_host: str
    langfuse_public_key: str
    langfuse_secret_key: str

    mcp_gateway_url: str
    opa_url: str

    # governance thresholds — live defaults; overridable per run via feature_flags
    tau_risk: float = 0.30
    tau_conf: float = 0.80


@lru_cache
def get_settings() -> Settings:
    import os

    db = vault.read("db")
    redis_ = vault.read("redis")
    qdrant = vault.read("qdrant")
    minio = vault.read("minio")
    llm = vault.read("llm")
    kc = vault.read("keycloak")
    lf = vault.read("langfuse")
    mcp = vault.read("mcp")

    return Settings(
        env=os.getenv("RG_ENV", "docker"),
        database_url=db["url_async"],
        database_url_sync=db["url_sync"],
        redis_url=redis_["url"],
        qdrant_url=qdrant["url"],
        minio_endpoint=minio["endpoint"],
        minio_access_key=minio["access_key"],
        minio_secret_key=minio["secret_key"],
        minio_bucket=minio["bucket"],
        bifrost_url=llm["bifrost_url"],
        openai_api_key=llm.get("openai_api_key", ""),
        groq_api_key=llm.get("groq_api_key", ""),
        keycloak_issuer=kc["issuer"],
        keycloak_jwks_url=kc["jwks_url"],
        keycloak_internal_url=kc["internal_url"],
        keycloak_audience=kc.get("audience", "account"),
        langfuse_host=lf["host"],
        langfuse_public_key=lf["public_key"],
        langfuse_secret_key=lf["secret_key"],
        mcp_gateway_url=mcp["gateway_url"],
        opa_url=os.getenv("RG_OPA_URL", "http://opa:8181"),
    )
