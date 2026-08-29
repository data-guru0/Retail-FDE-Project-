"""Analytics + agent health + auditor export — all from real rows.
Baseline rates come from docs/BASELINE.md (parsed, not hardcoded here)."""
from __future__ import annotations

import pathlib
import re

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.security import Principal, require_role

router = APIRouter(prefix="/dashboard", tags=["analytics"])
reviewer = require_role("reviewer", "admin")

_BASELINE_MD = pathlib.Path(__file__).resolve().parents[1] / "docs" / "BASELINE.md"


def _baseline() -> dict:
    txt = _BASELINE_MD.read_text() if _BASELINE_MD.exists() else ""

    def num(label: str, default: float) -> float:
        m = re.search(rf"{re.escape(label)}.*?\*\*\$?([\d.]+)", txt)
        return float(m.group(1)) if m else default

    return {
        "reviewer_cost_per_hour": num("Reviewer fully-loaded cost", 32.0),
        "human_min_all": num("Human handling time per return", 7.5),
        "human_min_escalated": num("time per **escalated** case", 4.0),
        "qa_min": num("confirm time for an auto-approve QA sample", 1.5),
        "fraud_loss": num("Fraud loss per undetected", 140.0),
    }


@router.get("/analytics")
async def analytics(p: Principal = Depends(reviewer),
                    session: AsyncSession = Depends(get_session)) -> dict:
    b = _baseline()
    counts = (await session.execute(text(
        """
        SELECT
          count(*) FILTER (WHERE a.action='auto_approve')            AS auto_approved,
          count(*) FILTER (WHERE a.action='escalate')                AS escalated,
          count(*) FILTER (WHERE a.action IN ('decide_approve','decide_deny')) AS human_decided
        FROM audit_log a WHERE a.entity_type='return'
        """))).mappings().one()
    qa = (await session.execute(text(
        "SELECT count(*) FROM agreement_samples WHERE kind='qa_sample'"))).scalar_one()

    hours_saved = (
        counts["auto_approved"] * b["human_min_all"]
        + counts["escalated"] * (b["human_min_all"] - b["human_min_escalated"])
        + qa * (b["human_min_all"] - b["qa_min"])
    ) / 60.0
    dollars_saved = round(hours_saved * b["reviewer_cost_per_hour"], 2)

    spend = (await session.execute(text(
        "SELECT model, sum(cost_usd) AS cost, count(DISTINCT graph_run_id) AS runs "
        "FROM agent_runs GROUP BY model ORDER BY cost DESC"))).mappings().all()
    total_cost = float(sum(r["cost"] for r in spend))
    total_runs = (await session.execute(text(
        "SELECT count(DISTINCT graph_run_id) FROM agent_runs"))).scalar_one() or 1
    cost_per_decision = round(total_cost / total_runs, 6)

    agree = (await session.execute(text(
        """
        SELECT count(*) AS n, count(*) FILTER (WHERE agreed) AS agreed
        FROM agreement_samples WHERE kind='override'
        """))).mappings().one()
    fp = (await session.execute(text(
        """
        SELECT count(*) FROM agreement_samples
        WHERE kind='override' AND agent_decision='approve' AND human_decision='deny'
        """))).scalar_one()

    p50p95 = (await session.execute(text(
        """
        SELECT
          percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM (decided_at - created_at))) AS p50,
          percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM (decided_at - created_at))) AS p95
        FROM returns WHERE decided_at IS NOT NULL
        """))).mappings().one()

    return {
        "counts": dict(counts) | {"qa_samples": qa},
        "vs_baseline": {
            "reviewer_hours_saved": round(hours_saved, 2),
            "dollars_saved": dollars_saved,
            "time_to_decision_p50_s": round(p50p95["p50"] or 0, 1),
            "time_to_decision_p95_s": round(p50p95["p95"] or 0, 1),
        },
        "unit_economics": {
            "cost_per_decision_usd": cost_per_decision,
            "by_model": [{"model": r["model"], "cost_usd": round(float(r["cost"]), 6),
                          "runs": r["runs"]} for r in spend],
            "monthly_projection_usd": round(cost_per_decision * total_runs, 4),
        },
        "quality": {
            "reviewed": agree["n"],
            "agreement_rate": round((agree["agreed"] / agree["n"]) if agree["n"] else 0, 3),
            "false_positive_overrides": fp,
        },
    }


@router.get("/agent-health")
async def agent_health(p: Principal = Depends(reviewer),
                       session: AsyncSession = Depends(get_session)) -> dict:
    per_agent = (await session.execute(text(
        """
        SELECT agent,
               count(*) AS runs,
               round(avg(latency_ms))::int AS avg_latency_ms,
               round(avg(NULLIF(confidence,0))::numeric, 3) AS avg_confidence,
               round(sum(cost_usd)::numeric, 6) AS cost_usd,
               sum(tokens_in+tokens_out) AS tokens,
               count(*) FILTER (WHERE error IS NOT NULL) AS errors
        FROM agent_runs GROUP BY agent ORDER BY agent
        """))).mappings().all()
    trend = (await session.execute(text(
        """
        SELECT date_trunc('day', created_at) AS day,
               count(*) AS n, count(*) FILTER (WHERE agreed) AS agreed
        FROM agreement_samples WHERE kind='override'
        GROUP BY 1 ORDER BY 1
        """))).mappings().all()
    return {
        "per_agent": [dict(r) for r in per_agent],
        "agreement_trend": [
            {"day": str(r["day"]), "agreement": round((r["agreed"] / r["n"]) if r["n"] else 0, 3),
             "n": r["n"]} for r in trend
        ],
    }


@router.get("/rings")
async def rings(p: Principal = Depends(reviewer),
                session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(text(
        """
        SELECT f1.value_hash, f1.kind, array_agg(DISTINCT u.email) AS accounts
        FROM fingerprints f1
        JOIN fingerprints f2 ON f1.value_hash=f2.value_hash AND f1.kind=f2.kind
             AND f2.user_id <> f1.user_id
        JOIN users u ON u.id = f1.user_id
        GROUP BY f1.value_hash, f1.kind
        HAVING count(DISTINCT f1.user_id) >= 1
        ORDER BY cardinality(array_agg(DISTINCT u.email)) DESC
        """))).mappings().all()
    return [{"kind": r["kind"], "fingerprint": r["value_hash"][:12],
             "accounts": r["accounts"]} for r in rows]


@router.get("/returns/{rid}/export")
async def case_export(rid: str, p: Principal = Depends(reviewer),
                      session: AsyncSession = Depends(get_session)) -> dict:
    r = (await session.execute(text(
        "SELECT r.*, u.email AS customer FROM returns r JOIN users u ON u.id=r.user_id "
        "WHERE r.id=:r"), {"r": rid})).mappings().one()
    runs = (await session.execute(text(
        "SELECT * FROM agent_runs WHERE graph_run_id=:g ORDER BY created_at"),
        {"g": r["graph_run_id"]})).mappings().all()
    audit = (await session.execute(text(
        "SELECT id, ts, actor_type, actor_id, action, data, prev_hash, row_hash "
        "FROM audit_log WHERE entity_id=:r ORDER BY id"), {"r": rid})).mappings().all()
    tool_calls = (await session.execute(text(
        "SELECT seq, agent, kind, payload FROM agent_run_events WHERE return_id=:r "
        "AND kind='rag' ORDER BY seq"), {"r": rid})).mappings().all()

    def clean(d: dict) -> dict:
        return {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in d.items()}

    bundle = {
        "return": clean(dict(r)),
        "agent_runs": [clean(dict(x)) for x in runs],
        "human_actions": [clean(dict(x)) for x in audit],
        "retrieval": [dict(x) for x in tool_calls],
        "policy_version": next((x["policy_version"] for x in runs if x["policy_version"]), None),
        "audit_chain_tip": audit[-1]["row_hash"] if audit else None,
    }
    return bundle
