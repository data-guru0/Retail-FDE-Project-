"""Shared helpers for the host-side verify_* / scenario scripts.
These run on the host (Python 3.14) and talk to the live stack over localhost.
Only stdlib + httpx + psycopg.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import psycopg


def _dotenv() -> dict[str, str]:
    f = Path(__file__).resolve().parents[1] / ".env"
    out: dict[str, str] = {}
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


_E = _dotenv()
_PW = _E.get("POSTGRES_PASSWORD", "")
_USER = _E.get("POSTGRES_USER", "returnguard")
_DB = _E.get("POSTGRES_DB", "returnguard")

API = os.getenv("RG_API", "http://localhost:8000")
PG = os.getenv("RG_PG_DSN", f"postgresql://{_USER}:{_PW}@localhost:5432/{_DB}")
KEYCLOAK = os.getenv("RG_KEYCLOAK", "http://localhost:8081")
MINIO = os.getenv("RG_MINIO", "http://localhost:9000")
LANGFUSE = os.getenv("RG_LANGFUSE", "http://localhost:3001")
BIFROST = os.getenv("RG_BIFROST", "http://localhost:8090")


def run(cmd: list[str]):
    """subprocess.run with UTF-8 decoding (Windows console is cp1252)."""
    import subprocess

    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def db() -> psycopg.Connection:
    return psycopg.connect(PG, autocommit=True)


def q1(sql: str, **params):
    with db() as c:
        row = c.execute(sql, params).fetchone()
        return row[0] if row and len(row) == 1 else row


def qall(sql: str, **params):
    with db() as c:
        return c.execute(sql, params).fetchall()


class Check:
    def __init__(self, name: str):
        self.name = name
        self.failed = 0

    def ok(self, cond: bool, msg: str) -> None:
        mark = "PASS" if cond else "FAIL"
        if not cond:
            self.failed += 1
        print(f"  [{mark}] {msg}")

    def done(self) -> None:
        if self.failed:
            print(f"\n{self.name}: {self.failed} check(s) FAILED\n")
            sys.exit(1)
        print(f"\n{self.name}: all checks passed\n")


__all__ = [
    "API", "KEYCLOAK", "MINIO", "LANGFUSE", "BIFROST",
    "db", "q1", "qall", "run", "Check", "httpx",
]
