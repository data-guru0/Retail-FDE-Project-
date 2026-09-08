"""Keycloak JWT verification (JWKS) + a `users` row upsert per authenticated caller.

Every API request carries a Keycloak access token. We verify signature + issuer +
expiry against the realm JWKS, then map the token to a local `users` row (created
on first sight) so the rest of the app has a stable internal user id.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.logging import log
from app.models import Reviewer, User
from app.settings import get_settings

_jwks_client: jwt.PyJWKClient | None = None
_jwks_at = 0.0


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client, _jwks_at
    if _jwks_client is None or time.time() - _jwks_at > 3600:
        _jwks_client = jwt.PyJWKClient(get_settings().keycloak_jwks_url)
        _jwks_at = time.time()
    return _jwks_client


@dataclass
class Principal:
    sub: str
    email: str
    name: str
    roles: list[str] = field(default_factory=list)
    user_id: str = ""
    reviewer_id: str | None = None

    def has(self, role: str) -> bool:
        return role in self.roles


def _decode(token: str) -> dict:
    s = get_settings()
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=s.keycloak_issuer,
            options={"verify_aud": False},  # KC access-token aud is 'account'; we gate on roles
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e


async def get_principal(
    authorization: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    claims = _decode(authorization.split(" ", 1)[1])

    sub = claims["sub"]
    email = claims.get("email") or claims.get("preferred_username") or f"{sub}@no-email"
    name = claims.get("name") or claims.get("preferred_username") or email
    roles = list(claims.get("realm_access", {}).get("roles", []))
    app_roles = [r for r in roles if r in ("customer", "reviewer", "admin")]
    role = "admin" if "admin" in app_roles else "reviewer" if "reviewer" in app_roles else "customer"

    user = (await session.execute(select(User).where(User.keycloak_sub == sub))).scalar_one_or_none()
    if user is None:
        user = User(keycloak_sub=sub, email=email, name=name, role=role)
        session.add(user)
        await session.flush()
        if role in ("reviewer", "admin"):
            session.add(Reviewer(user_id=user.id, display_name=name))
        await session.commit()
        log.info("user.created", sub=sub, role=role)
    elif user.role != role or user.email != email:
        user.role, user.email, user.name = role, email, name
        await session.commit()

    reviewer = (
        await session.execute(select(Reviewer).where(Reviewer.user_id == user.id))
    ).scalar_one_or_none()

    return Principal(
        sub=sub, email=email, name=name, roles=app_roles,
        user_id=str(user.id), reviewer_id=str(reviewer.id) if reviewer else None,
    )


async def current_user(p: Principal = Depends(get_principal)) -> Principal:
    return p


def require_role(*allowed: str):
    async def _dep(p: Principal = Depends(get_principal)) -> Principal:
        if not any(p.has(r) for r in allowed):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires one of {allowed}")
        return p

    return _dep
