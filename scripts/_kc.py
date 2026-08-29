"""Keycloak helpers for the host-side verify_* / scenario scripts."""
from __future__ import annotations

import httpx

import os

from _rg import _E

KC = os.getenv("RG_KEYCLOAK", "http://localhost:8081")
REALM = "returnguard"
ADMIN_USER = _E.get("KEYCLOAK_ADMIN") or os.getenv("KEYCLOAK_ADMIN", "admin")
ADMIN_PASS = _E.get("KEYCLOAK_ADMIN_PASSWORD") or os.getenv("KEYCLOAK_ADMIN_PASSWORD", "")


def admin_token() -> str:
    r = httpx.post(
        f"{KC}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": ADMIN_USER,
            "password": ADMIN_PASS,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def register_user(email: str, password: str, roles: list[str] | None = None) -> str:
    """Create a realm user (idempotent-ish) and return its Keycloak id."""
    tok = admin_token()
    h = {"Authorization": f"Bearer {tok}"}
    body = {
        "username": email,
        "email": email,
        "enabled": True,
        "emailVerified": True,
        "firstName": email.split("@")[0],
        "lastName": "Test",
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    r = httpx.post(f"{KC}/admin/realms/{REALM}/users", headers=h, json=body, timeout=15)
    if r.status_code not in (201, 409):
        r.raise_for_status()
    got = httpx.get(
        f"{KC}/admin/realms/{REALM}/users", headers=h, params={"email": email, "exact": "true"},
        timeout=15,
    )
    got.raise_for_status()
    uid = got.json()[0]["id"]
    for role in roles or []:
        rr = httpx.get(f"{KC}/admin/realms/{REALM}/roles/{role}", headers=h, timeout=15)
        rr.raise_for_status()
        httpx.post(
            f"{KC}/admin/realms/{REALM}/users/{uid}/role-mappings/realm",
            headers=h, json=[rr.json()], timeout=15,
        )
    return uid


def token(email: str, password: str, client_id: str = "returnguard-cli") -> str:
    r = httpx.post(
        f"{KC}/realms/{REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": email,
            "password": password,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]
