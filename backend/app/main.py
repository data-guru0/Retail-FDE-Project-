from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.logging import configure, log
from app.routers import health
from app.telemetry import CorrelationMiddleware, metrics_response

configure()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("backend.start")
    yield
    log.info("backend.stop")


app = FastAPI(title="ReturnGuard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(CorrelationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


app.include_router(health.router)


@app.get("/metrics")
def metrics():
    return metrics_response()


# Routers added in later milestones (shop, orders, returns, dashboard, ...).
try:
    from app.routers import orders, returns, shop  # noqa: F401

    app.include_router(shop.router)
    app.include_router(orders.router)
    app.include_router(returns.router)
except ImportError:
    log.info("backend.routers.partial", note="shop/orders/returns not yet present")
