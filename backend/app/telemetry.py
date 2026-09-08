"""Request instrumentation: correlation id + Prometheus, both via standard libs.

- `asgi-correlation-id` — reads/generates `X-Correlation-ID` per request and puts
  it on a ContextVar that `app.logging` reads into every structured log line.
- `prometheus-fastapi-instrumentator` — per-route latency / count / size / in-
  progress metrics and the `/metrics` endpoint.

Agent-call spans go to Langfuse from the worker (that's where the LLM calls are).
"""
from __future__ import annotations

import uuid

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def setup(app: FastAPI) -> None:
    app.add_middleware(
        CorrelationIdMiddleware,
        header_name="X-Correlation-ID",
        generator=lambda: uuid.uuid4().hex,
    )
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(app, include_in_schema=False)
