"""Prometheus metrics for the worker. Served on :9100 (scraped by Prometheus).
Updated from pipeline/jobs.py and pipeline/governance.py.
"""
from __future__ import annotations

import structlog
from prometheus_client import Counter, Gauge, Histogram, start_http_server

log = structlog.get_logger()

PIPELINE_RUNS = Counter("rg_pipeline_runs_total", "Return-review pipeline runs", ["route"])
PIPELINE_ERRORS = Counter("rg_pipeline_errors_total", "Pipeline errors (per attempt)")
DEAD_LETTERS = Counter("rg_dead_letters_total", "Cases sent to the dead-letter queue")
LLM_COST = Counter("rg_llm_cost_usd_total", "USD spent on LLM calls (from agent_runs)")
DECISION_LATENCY = Histogram(
    "rg_pipeline_seconds", "Wall time of one review_return job",
    buckets=(1, 2, 5, 10, 20, 40, 80, 160),
)
QUEUE_OLDEST = Gauge("rg_queue_oldest_seconds", "Age of the oldest undecided escalation")
AGREEMENT = Gauge("rg_agent_human_agreement_ratio", "Rolling agent-vs-human agreement")


def serve(port: int = 9100) -> None:
    start_http_server(port)
    log.info("worker.metrics.serving", port=port)


async def refresh_gauges(db) -> None:
    """Called by a cron — pulls a couple of gauges straight from Postgres."""
    row = await db.fetchrow(
        "SELECT COALESCE(EXTRACT(epoch FROM (now() - min(created_at))), 0) AS oldest "
        "FROM returns WHERE status = 'escalated' AND final_decision IS NULL"
    )
    QUEUE_OLDEST.set(float(row["oldest"]) if row else 0.0)
    ag = await db.fetchrow(
        "SELECT COALESCE(avg(CASE WHEN agreed THEN 1 ELSE 0 END), 1) AS r "
        "FROM agreement_samples WHERE kind = 'override' "
        "AND created_at > now() - interval '30 days'"
    )
    AGREEMENT.set(float(ag["r"]) if ag else 1.0)
