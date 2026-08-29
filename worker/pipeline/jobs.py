"""Return review job.

`review_return` claims a pending return, runs the full LangGraph pipeline
(pipeline/graph.py), and lets GovernanceGate finalize it. Every step writes a
real `agent_runs` row + streams `agent_run_events` (Redis pub/sub → dashboard WS)
+ records a Langfuse generation. Retry is counted on `returns.review_attempts`;
3 crashes → `dead_letter` + auto-escalate. Never an infinite retry.
"""
from __future__ import annotations

import os
import time
import uuid

import structlog

from pipeline import db
from pipeline.bus import publish_event
from pipeline.metrics import DEAD_LETTERS, DECISION_LATENCY, PIPELINE_ERRORS, PIPELINE_RUNS
from pipeline.observability import flush

log = structlog.get_logger()

MAX_TRIES = 3


async def review_return(rctx: dict, return_id: str) -> dict:
    graph_run_id = uuid.uuid4().hex
    _t0 = time.perf_counter()

    context = await db.get_review_context(return_id)
    if context is None:
        log.warning("review_return.no_such_return", return_id=return_id)
        return {"skipped": "return not found"}
    if context["status"] not in ("pending", "info_requested"):
        log.info("review_return.already_processed", return_id=return_id, status=context["status"])
        return {"skipped": f"status={context['status']}"}

    # atomically claim + count the attempt so a duplicate enqueue can't double-process
    # and the dead-letter cap holds regardless of arq job identity
    attempt = await db.fetchval(
        "UPDATE returns SET status='in_review', graph_run_id=%(g)s, "
        "review_attempts = review_attempts + 1 "
        "WHERE id=%(r)s AND status IN ('pending','info_requested') RETURNING review_attempts",
        {"g": graph_run_id, "r": return_id},
    )
    if attempt is None:
        log.info("review_return.claimed_elsewhere", return_id=return_id)
        return {"skipped": "claimed by another run"}
    job_try = attempt
    log.info("review_return.start", return_id=return_id, try_=job_try)

    # claim implies the outbox row is handled — stop the dispatcher re-enqueuing it
    await db.execute(
        "UPDATE outbox SET dispatched_at=now() "
        "WHERE topic='return.submitted' AND payload->>'return_id'=%(id)s AND dispatched_at IS NULL",
        {"id": return_id},
    )

    level, kill = await db.current_automation_level(context["category"])
    seq = 0

    async def event(kind: str, agent: str, payload: dict) -> None:
        nonlocal seq
        seq += 1
        await db.add_event(return_id, graph_run_id, seq, agent, kind, payload)

    await event("pipeline_start", "system",
                {"automation_level": level, "kill_switch": kill, "try": job_try})

    try:
        # ponytail: fault-injection hook for the dead-letter drill (verify_m3_dlq).
        # Off unless RG_PIPELINE_FORCE_ERROR is set. Never fabricates a decision —
        # it only raises, exercising the real retry -> dead_letter -> escalate path.
        if os.getenv("RG_PIPELINE_FORCE_ERROR"):
            raise RuntimeError("forced pipeline error (RG_PIPELINE_FORCE_ERROR)")

        from pipeline.graph import run_pipeline

        initial = {
            "return_id": return_id,
            "graph_run_id": graph_run_id,
            "automation_level": level,
            "kill_switch": kill,
            "category": context["category"],
            "context": context,
            "seq": seq,
            "errors": [],
        }
        final_state = await run_pipeline(initial)
        final = final_state.get("final", {})
        dec = final_state.get("decision", {})
        proposed = final.get("proposed") or dec.get("decision", "escalate")
        route = final.get("route", "escalate")
        seq = final_state.get("seq", seq)  # continue the event sequence past the graph's

        await event("pipeline_end", "system", {
            "route": route, "proposed": proposed, "automation_level": level,
            "auto": final.get("auto", False),
            "agents_fired": sorted({
                r["agent"] for r in await db.fetchall(
                    "SELECT DISTINCT agent FROM agent_runs WHERE graph_run_id=%(g)s",
                    {"g": graph_run_id})
            }),
        })
        flush()
        PIPELINE_RUNS.labels(route=route).inc()
        DECISION_LATENCY.observe(time.perf_counter() - _t0)
        log.info("review_return.done", return_id=return_id, route=route, proposed=proposed)
        return {"return_id": return_id, "route": route, "proposed": proposed}

    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        PIPELINE_ERRORS.inc()
        log.error("review_return.error", return_id=return_id, try_=job_try, error=err)
        await event("error", "system", {"try": job_try, "error": err})
        if job_try >= MAX_TRIES:
            await db.execute(
                "INSERT INTO dead_letter (return_id, attempts, last_error) "
                "VALUES (%(r)s, %(a)s, %(e)s)",
                {"r": return_id, "a": job_try, "e": err},
            )
            await db.execute(
                "UPDATE returns SET status='escalated' WHERE id=%(r)s", {"r": return_id}
            )
            await event("dead_letter", "system", {"attempts": job_try})
            await publish_event(return_id, {"kind": "dead_letter", "attempts": job_try})
            DEAD_LETTERS.inc()
            log.error("review_return.dead_letter", return_id=return_id, attempts=job_try)
            return {"dead_letter": True, "return_id": return_id}
        # release the claim and re-enqueue a counted retry (5s back-off)
        await db.execute(
            "UPDATE returns SET status='pending' WHERE id=%(r)s AND status='in_review'",
            {"r": return_id},
        )
        await rctx["redis"].enqueue_job("review_return", return_id, _defer_by=5)
        return {"retry_scheduled": True, "attempt": job_try, "error": err}


async def reembed_policy(rctx: dict) -> dict:
    """Re-embed the active policy docs into Qdrant (triggered by the admin Policy editor)."""
    from pipeline.policy_index import reembed

    out = await reembed()
    log.info("reembed_policy.done", **out)
    return out


def _send_mail(to: str, subject: str, body: str) -> None:
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "no-reply@returnguard.local", to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP("mailhog", 1025, timeout=10) as s:
            s.send_message(msg)
    except OSError as e:
        log.warning("process_refunds.mail_failed", to=to, error=str(e))


async def process_refunds(rctx: dict) -> int:
    """Settle approved returns: refund_state pending -> refunded, + audit row +
    customer email. No money moves — this is the state transition a payment
    processor's settlement webhook would otherwise drive."""
    from pipeline import audit

    rows = await db.fetchall(
        "SELECT r.id::text AS rid, r.amount, u.email "
        "FROM returns r JOIN users u ON u.id = r.user_id "
        "WHERE r.refund_state = 'pending' AND r.status = 'approved' "
        "ORDER BY r.decided_at LIMIT 25"
    )
    n = 0
    for row in rows:
        updated = await db.fetchval(
            "UPDATE returns SET refund_state = 'refunded', status = 'refunded' "
            "WHERE id = %(r)s AND refund_state = 'pending' RETURNING id::text",
            {"r": row["rid"]},
        )
        if not updated:
            continue
        await audit.append(
            actor_type="system", actor_id="refund_processor", action="refund_issued",
            entity_type="return", entity_id=row["rid"],
            data={"amount_usd": float(row["amount"]), "note": "state transition only; no money moved"},
        )
        _send_mail(row["email"], "Your refund has been issued",
                   f"Return {row['rid']}: ${row['amount']} refunded to your original payment method.")
        n += 1
    if n:
        log.info("process_refunds.settled", n=n)
    return n


async def dispatch_outbox(rctx: dict) -> int:
    """Durability backstop: enqueue any return.submitted outbox row the backend's
    best-effort enqueue missed (older than 8s and still undispatched)."""
    ids = await db.fetchall(
        "SELECT payload->>'return_id' AS rid FROM outbox "
        "WHERE topic='return.submitted' AND dispatched_at IS NULL "
        "AND created_at < now() - interval '8 seconds'"
    )
    n = 0
    for row in ids:
        await rctx["redis"].enqueue_job("review_return", row["rid"])
        n += 1
    if n:
        log.info("dispatch_outbox.enqueued", n=n)
    return n
