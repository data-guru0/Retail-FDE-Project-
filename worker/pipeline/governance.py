"""GovernanceGate — the ONLY place a decision is finalized.

Reads automation_level (+ per-category flags + kill switch) and applies the
non-negotiable rules:
  * kill switch on            -> escalate (every case, regardless of anything)
  * data-quality failed       -> escalate ("insufficient data", proposed=escalate)
  * Decision agent said deny   -> escalate (proposed=deny)   [auto-deny never ships]
  * Policy high-value flag     -> escalate (proposed=<decision>)
  * Critic veto                -> escalate
  * auto-approve  ONLY IF  risk < tau_risk AND confidence > tau_conf
                  AND automation_level in (assist, auto)
                  -> in assist, sample X% into the human queue for QA
  * everything else            -> escalate
"""
from __future__ import annotations

import random

import structlog

from pipeline import audit, db
from pipeline.nodes.base import RunCtx, record_local_agent

log = structlog.get_logger()


async def _flags(category: str | None) -> dict:
    row = await db.fetchrow(
        "SELECT automation_level, kill_switch, qa_sample_pct, tau_risk, tau_conf "
        "FROM feature_flags WHERE scope = %(s)s", {"s": category or "global"}
    )
    if row is None:
        row = await db.fetchrow(
            "SELECT automation_level, kill_switch, qa_sample_pct, tau_risk, tau_conf "
            "FROM feature_flags WHERE scope = 'global'"
        )
    return row


async def run(state: dict) -> dict:
    rc = RunCtx(state["return_id"], state["graph_run_id"], state["automation_level"],
                state.get("policy", {}).get("policy_version"))
    f = await _flags(state.get("category"))
    level = f["automation_level"]
    tau_risk, tau_conf = float(f["tau_risk"]), float(f["tau_conf"])

    dec = state.get("decision", {}) or {}
    proposed = dec.get("decision", "escalate")
    conf = float(dec.get("confidence", 0) or 0)
    risk = float(dec.get("risk", 1) or 1)
    dq_ok = state.get("data_quality", {}).get("ok", True)
    critic_veto = bool(state.get("critic", {}).get("veto"))
    high_value = bool(state.get("policy", {}).get("high_value_flag"))

    reasons = []
    route = "escalate"
    auto = False

    if f["kill_switch"]:
        reasons.append("kill switch is on — every case goes to human review")
    elif not dq_ok:
        proposed = "escalate"
        reasons.append(f"data-quality gate failed: {state['data_quality'].get('reason')}")
    elif proposed == "deny":
        reasons.append("auto-deny is never final; routed for human confirmation of the denial")
    elif high_value:
        reasons.append("refund exceeds the high-value threshold; human sign-off required")
    elif critic_veto:
        reasons.append(f"Critic vetoed: {state['critic'].get('concern')}")
    elif proposed == "approve" and risk < tau_risk and conf > tau_conf and level in ("assist", "auto"):
        route = "auto_approve"
        auto = True
        reasons.append(
            f"auto-approved: risk {risk:.2f} < {tau_risk}, confidence {conf:.2f} > {tau_conf}, "
            f"level={level}, no Critic veto"
        )
    else:
        if proposed == "approve" and level in ("assist", "auto"):
            reasons.append(
                f"not eligible for auto-approve (risk {risk:.2f} / conf {conf:.2f} vs "
                f"tau {tau_risk}/{tau_conf})"
            )
        elif level in ("shadow", "suggest"):
            reasons.append(f"automation_level={level}: agent decides, human acts")
        else:
            reasons.append("conditions for autonomy not met")

    qa_sample = False
    if route == "auto_approve" and level == "assist" and random.random() < f["qa_sample_pct"] / 100:
        qa_sample = True
        reasons.append(f"QA sample: 1-in-{max(1, round(100 / max(f['qa_sample_pct'], 1)))} auto-approvals reviewed")

    final = {
        "route": route,                      # auto_approve | escalate
        "proposed": proposed,                # approve | deny | escalate
        "automation_level": level,
        "kill_switch": bool(f["kill_switch"]),
        "auto": auto,
        "qa_sample": qa_sample,
        "reason": "; ".join(reasons),
        "tau_risk": tau_risk, "tau_conf": tau_conf,
        "risk": risk, "confidence": conf,
    }
    await record_local_agent(rc, state, agent="governance", output=final,
                             model="governance_gate", latency_ms=0)
    await _apply(rc, state, final)
    await rc.emit(state, "node_end", "governance", final)
    return {"final": final}


async def _apply(rc: RunCtx, state: dict, final: dict) -> None:
    rid = state["return_id"]
    explanation = state.get("explanation") or state.get("decision", {}).get("reason", "")

    if final["route"] == "auto_approve":
        await db.execute(
            "UPDATE returns SET status='approved', decision=%(d)s, final_decision='approve', "
            "decision_reason=%(r)s, refund_state='pending', review_attempts=review_attempts "
            "WHERE id=%(id)s",
            {"d": final["proposed"], "r": explanation, "id": rid},
        )
        rh = await audit.append(
            actor_type="system", actor_id="governance_gate", action="auto_approve",
            entity_type="return", entity_id=rid,
            data={"final": final, "decision": state.get("decision"),
                  "graph_run_id": state["graph_run_id"]},
        )
        if final["qa_sample"]:
            await db.execute(
                "INSERT INTO agreement_samples "
                "(return_id, agent, decision_type, agent_decision, human_decision, agreed, kind) "
                "VALUES (%(r)s,'decision','auto_approve','approve','', true, 'qa_sample')",
                {"r": rid},
            )
        log.info("governance.auto_approve", return_id=rid, audit=rh[:12])
    else:
        await db.execute(
            "UPDATE returns SET status='escalated', decision=%(d)s, decision_reason=%(r)s "
            "WHERE id=%(id)s",
            {"d": final["proposed"], "r": explanation, "id": rid},
        )
        await audit.append(
            actor_type="system", actor_id="governance_gate", action="escalate",
            entity_type="return", entity_id=rid,
            data={"final": final, "decision": state.get("decision"),
                  "proposed": final["proposed"], "graph_run_id": state["graph_run_id"]},
        )
        log.info("governance.escalate", return_id=rid, proposed=final["proposed"])
