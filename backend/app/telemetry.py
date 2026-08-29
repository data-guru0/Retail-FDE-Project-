"""Prometheus metrics + a correlation-id middleware.

ponytail: OTel span export to Langfuse is done in the worker (where the agent
calls live) via the Langfuse SDK + Bifrost's OTel feed. The backend only needs
request metrics + correlation-id propagation, so that's all this does.
"""
from __future__ import annotations

import time
import uuid

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging import correlation_id

REQS = Counter("rg_http_requests_total", "HTTP requests", ["method", "path", "status"])
LAT = Histogram("rg_http_request_seconds", "HTTP latency", ["method", "path"])


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or uuid.uuid4().hex
        correlation_id.set(cid)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = request.scope.get("route").path if request.scope.get("route") else request.url.path
        REQS.labels(request.method, path, response.status_code).inc()
        LAT.labels(request.method, path).observe(elapsed)
        response.headers["x-correlation-id"] = cid
        return response


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
