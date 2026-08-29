"""M3 single-agent return review.

One real Groq call (via Bifrost, with the OpenAI fallback chain active) reads a
return and produces a structured, guardrail-validated decision. The decision is
written to `returns` + a real `agent_runs` row; every step streams an
`agent_run_events` row (and a Redis pub/sub event for the live dashboard trace);
a real Langfuse generation is recorded. `automation_level` defaults to `shadow`:
the agent decides, a human still acts.

M4 replaces this single node with the full LangGraph pipeline.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid

import structlog

from pipeline import db
from pipeline.bus import publish_event
from pipeline.guardrails import parse_validated
from pipeline.llm import chat
from pipeline.observability import flush, record_generation
from pipeline.prompts.registry import load, prompt_version

log = structlog.get_logger()

DECISION_SCHEMA = {
    "type": "object",
    "required": ["decision", "confidence", "risk", "reason"],
    "additionalProperties": True,
    "properties": {
        "decision": {"enum": ["approve", "deny", "escalate"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "risk": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "minLength": 3},
        "signals": {"type": "array", "items": {"type": "string"}},
    },
}

MAX_TRIES = 3


def _facts(ctx: dict) -> str:
    age_days = None
    if ctx.get("age_since_order") is not None:
        age_days = round(ctx["age_since_order"].total_seconds() / 86400, 1)
    return json.dumps(
        {
            "item_name": ctx["item_name"],
            "category": ctx["category"],
            "product_description": (ctx.get("product_description") or "")[:400],
            "reason_code": ctx["reason_code"],
            "customer_reason_text": ctx["reason_text"],
            "refund_amount_usd": float(ctx["amount"]),
            "order_total_usd": float(ctx["order_total"]),
            "days_since_order": age_days,
            "photo_provided": ctx["photo_count"] > 0,
            "customer_lifetime_orders": ctx["user_order_count"],
            "customer_lifetime_returns": ctx["user_return_count"],
        },
        indent=2,
    )


async def review_return(rctx: dict, return_id: str) -> dict:
    graph_run_id = uuid.uuid4().hex

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

        system, version, _ = load("decision")
        facts = _facts(context)
        input_hash = hashlib.sha256(facts.encode()).hexdigest()

        await event("node_start", "decision", {"model_role": "reason"})
        result = chat("reason", system, facts, max_tokens=900)
        parsed, result = parse_validated(
            result, DECISION_SCHEMA, role="reason", system=system, user=facts
        )

        trace_id = record_generation(
            agent="decision", model=result.model, prompt=facts, output=result.text,
            return_id=return_id, graph_run_id=graph_run_id,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out, cost=result.cost_usd,
        )

        run_id = await db.insert_agent_run(
            return_id=return_id, graph_run_id=graph_run_id, agent="decision",
            sa_subject=None, model=result.model, prompt_version=prompt_version("decision"),
            policy_version=None, automation_level=level, input_hash=input_hash,
            raw_response=result.text, parsed_output=parsed,
            confidence=round(float(parsed["confidence"]), 3),
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            cost_usd=result.cost_usd, latency_ms=result.latency_ms,
            langfuse_trace_id=trace_id, error=None,
        )
        await event("node_end", "decision", {
            "agent_run_id": run_id, "decision": parsed["decision"],
            "confidence": parsed["confidence"], "risk": parsed["risk"],
            "reason": parsed["reason"], "signals": parsed.get("signals", []),
            "model": result.model, "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out, "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
        })

        # shadow: record the agent's proposal on the return; a human still acts.
        await db.execute(
            "UPDATE returns SET decision=%(d)s, decision_reason=%(r)s, status='in_review' "
            "WHERE id=%(id)s",
            {"d": parsed["decision"], "r": parsed["reason"], "id": return_id},
        )
        await event("pipeline_end", "system",
                    {"proposed_decision": parsed["decision"], "automation_level": level})
        flush()
        log.info("review_return.done", return_id=return_id, decision=parsed["decision"],
                 model=result.model, cost=result.cost_usd)
        return {"return_id": return_id, "decision": parsed["decision"], "agent_run_id": run_id}

    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
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
            log.error("review_return.dead_letter", return_id=return_id, attempts=job_try)
            return {"dead_letter": True, "return_id": return_id}
        # release the claim and re-enqueue a counted retry (5s back-off)
        await db.execute(
            "UPDATE returns SET status='pending' WHERE id=%(r)s AND status='in_review'",
            {"r": return_id},
        )
        await rctx["redis"].enqueue_job("review_return", return_id, _defer_by=5)
        return {"retry_scheduled": True, "attempt": job_try, "error": err}


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
