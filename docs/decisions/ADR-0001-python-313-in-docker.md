# ADR-0001 — Backend & worker run on Python 3.13 in Docker

**Status:** accepted (M1)

## Context
The target host has Python 3.14.2 as default, plus 3.12 and 3.11 — no 3.13.
Several pinned deps (LangGraph checkpointer, open-clip-torch, torch) had the
widest wheel coverage on 3.13 at build time (Aug 2026), and CLAUDE.md fixes the
runtime at `python:3.13-slim`.

## Decision
`backend/` and `worker/` build from `python:3.13-slim` and run only in Docker.
Host Python is used solely for the thin `scripts/verify_*.py` / `run_scenarios.py`
harness, which needs only `httpx` + `psycopg` and is version-tolerant (runs on
host 3.14 or via `docker compose run`).

## Consequences
- No host virtualenv to maintain; `make` targets shell into containers.
- Dependency resolution is reproducible against one interpreter.
- Contributors never hit "works on my Python" drift.
