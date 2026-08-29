"""arq worker entrypoint. M3 registers the return-review job here."""
from __future__ import annotations

import structlog
from arq import cron

from pipeline.settings import redis_settings

log = structlog.get_logger()


async def startup(ctx: dict) -> None:
    log.info("worker.startup")


async def shutdown(ctx: dict) -> None:
    log.info("worker.shutdown")


async def heartbeat(ctx: dict) -> str:
    """Liveness beacon — arq cron writes the worker's last-seen time to Redis."""
    import time

    await ctx["redis"].set("rg:worker:heartbeat", str(time.time()))
    return "ok"


# Jobs are appended in later milestones (M3: review_return).
try:
    from pipeline.jobs import review_return  # noqa: F401

    FUNCTIONS: list = [heartbeat, review_return]
except ImportError:
    FUNCTIONS = [heartbeat]


class WorkerSettings:
    functions = FUNCTIONS
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 300
    cron_jobs = [cron(heartbeat, minute=set(range(60)), run_at_startup=True)]
