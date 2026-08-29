"""arq worker entrypoint."""
from __future__ import annotations

import structlog
from arq import cron

from pipeline import db, metrics
from pipeline.jobs import dispatch_outbox, process_refunds, reembed_policy, review_return
from pipeline.settings import redis_settings

log = structlog.get_logger()


async def startup(ctx: dict) -> None:
    await db.start()
    try:
        metrics.serve(9100)
    except OSError:
        pass  # already bound (reload)
    log.info("worker.startup")


async def refresh_metrics(ctx: dict) -> str:
    await metrics.refresh_gauges(db)
    return "ok"


async def shutdown(ctx: dict) -> None:
    await db.stop()
    log.info("worker.shutdown")


async def heartbeat(ctx: dict) -> str:
    import time

    await ctx["redis"].set("rg:worker:heartbeat", str(time.time()))
    return "ok"


class WorkerSettings:
    functions = [review_return, dispatch_outbox, reembed_policy, process_refunds,
                 refresh_metrics, heartbeat]
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 6
    job_timeout = 180
    max_tries = 3
    cron_jobs = [
        cron(heartbeat, minute=set(range(60)), run_at_startup=True),
        cron(dispatch_outbox, second={0, 10, 20, 30, 40, 50}, run_at_startup=True),
        cron(refresh_metrics, second={5, 20, 35, 50}, run_at_startup=True),
        cron(process_refunds, second={15, 45}, run_at_startup=True),
    ]
