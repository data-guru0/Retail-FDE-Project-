"""The LangGraph nodes. Each takes the pipeline state and returns a partial update.
Every LLM node routes through Bifrost with the agent's virtual key; every step
writes an agent_runs row and streams agent_run_events. Nothing here is final —
GovernanceGate (pipeline/governance.py) is the only place a decision is finalized.
"""
from __future__ import annotations

import json
import time

import structlog

from pipeline import db
from pipeline.nodes.base import RunCtx, record_local_agent, run_llm_agent

log = structlog.get_logger()


def _rc(state: dict) -> RunCtx:
    return RunCtx(
        return_id=state["return_id"],
        graph_run_id=state["graph_run_id"],
        automation_level=state["automation_level"],
        policy_version=state.get("policy", {}).get("policy_version"),
    )


def _facts(ctx: dict) -> dict:
    age_days = None
    if ctx.get("age_since_order") is not None:
        age_days = round(ctx["age_since_order"].total_seconds() / 86400, 1)
    return {
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
    }


# --------------------------------------------------------------- data quality
async def data_quality(state: dict) -> dict:
    rc = _rc(state)
    t0 = time.perf_counter()
    ctx = state["context"]
    problems = []
    if not ctx.get("item_name"):
        problems.append("order item missing")
    if ctx["reason_code"] in ("damaged", "defective", "not_as_described", "wrong_item") \
            and ctx["photo_count"] == 0:
        problems.append("evidence photo required for this reason but none provided")
    if not ctx.get("product_description"):
        problems.append("no reference product data")
    ok = len(problems) == 0
    out = {"ok": ok, "reason": "; ".join(problems) or "inputs sufficient",
           "confidence": 0.95}
    await record_local_agent(rc, state, agent="data_quality", output=out,
                             model="rule:data_quality", latency_ms=int((time.perf_counter() - t0) * 1000))
    await rc.emit(state, "node_end", "data_quality", {"output": out})
    return {"data_quality": out}


# --------------------------------------------------------------- planner
async def planner(state: dict) -> dict:
    rc = _rc(state)
    ctx = state["context"]
    facts = _facts(ctx)
    facts["reference_image_available"] = bool(ctx.get("product_description"))
    schema = {
        "type": "object", "required": ["plan"],
        "properties": {"plan": {"type": "array", "items": {"type": "string"}},
                       "rationale": {"type": "string"}},
    }
    out = await run_llm_agent(rc, state, agent="planner", prompt_name="planner",
                              role="fast", facts=facts, schema=schema, max_tokens=400)
    plan = [p for p in out["plan"] if p in
            ("intake", "policy", "image", "behavior", "decision", "critic", "explanation")]
    for must in ("intake", "policy", "behavior", "decision", "critic", "explanation"):
        if must not in plan:
            plan.append(must)
    if ctx["photo_count"] == 0 and "image" in plan:
        plan.remove("image")
    return {"plan": plan}


# --------------------------------------------------------------- intake
async def intake(state: dict) -> dict:
    rc = _rc(state)
    schema = {
        "type": "object", "required": ["complete", "reason"],
        "properties": {"complete": {"type": "boolean"},
                       "missing": {"type": "array", "items": {"type": "string"}},
                       "reason": {"type": "string"},
                       "confidence": {"type": "number"}},
    }
    out = await run_llm_agent(rc, state, agent="intake", prompt_name="intake",
                              role="fast", facts=_facts(state["context"]), schema=schema)
    return {"intake": out}


# --------------------------------------------------------------- policy (RAG)
async def policy(state: dict) -> dict:
    rc = _rc(state)
    from pipeline.policy_index import retrieve

    ctx = state["context"]
    query = (f"{ctx['reason_code']} return of a {ctx['category']} item "
             f"{_facts(ctx)['days_since_order']} days after delivery, "
             f"refund ${float(ctx['amount'])}. {ctx['reason_text'][:200]}")
    docs, version = retrieve(query, k=3)
    await rc.emit(state, "rag", "policy",
                  {"query": query, "hits": [d["slug"] for d in docs], "policy_version": version})

    facts = _facts(ctx)
    facts["retrieved_policy"] = [{"slug": d["slug"], "title": d["title"], "text": d["body"]}
                                for d in docs]
    schema = {
        "type": "object", "required": ["eligible", "reason"],
        "properties": {"eligible": {"enum": ["yes", "no", "unclear"]},
                       "reason": {"type": "string"},
                       "citations": {"type": "array", "items": {"type": "string"}},
                       "high_value_flag": {"type": "boolean"},
                       "confidence": {"type": "number"}},
    }
    rc.policy_version = version
    high_value = float(ctx["amount"]) > 250
    out = await run_llm_agent(
        rc, state, agent="policy", prompt_name="policy", role="reason",
        facts=facts, schema=schema, max_tokens=700,
        merge={"high_value_flag": high_value, "policy_version": version},
    )
    return {"policy": out}


# --------------------------------------------------------------- image (CLIP + detector + vision)
async def image(state: dict) -> dict:
    rc = _rc(state)
    t0 = time.perf_counter()
    ctx = state["context"]
    from pipeline import storage_worker as st
    from pipeline.models_local import ai_generated_score, clip_similarity

    ref = await st.product_image_bytes(ctx["return_id"])
    ret_photo = await st.return_photo_bytes(ctx["return_id"])
    if ref is None or ret_photo is None:
        out = {"checked": False, "reason": "reference or return image unavailable"}
        await record_local_agent(rc, state, agent="image", output=out, model="clip:skipped",
                                 latency_ms=int((time.perf_counter() - t0) * 1000))
        await rc.emit(state, "node_end", "image", {"output": out})
        return {"image": out}

    sim = clip_similarity(ref, ret_photo)
    ai = ai_generated_score(ret_photo)
    verdict = "match" if sim >= 0.75 else "borderline" if sim >= 0.6 else "mismatch"
    vision_note = None
    if verdict == "borderline":
        vision_note = await _vision_llm(rc, state, ctx)
        if vision_note and vision_note.get("matches") is False:
            verdict = "mismatch"
    out = {
        "checked": True,
        "clip_similarity": round(sim, 4),
        "ai_generated_score": ai["ai_generated_score"],
        "detector": ai["model"],
        "verdict": verdict,
        "vision_llm": vision_note,
        "reason": _image_reason(sim, ai["ai_generated_score"], verdict),
        "confidence": 0.8,
    }
    await record_local_agent(rc, state, agent="image", output=out,
                             model=f"clip+{ai['model']}",
                             latency_ms=int((time.perf_counter() - t0) * 1000))
    await rc.emit(state, "node_end", "image", {"output": out})
    return {"image": out}


def _image_reason(sim: float, ai_score: float, verdict: str) -> str:
    bits = [f"photo-vs-product similarity {sim:.2f} ({verdict})"]
    if ai_score >= 0.5:
        bits.append(f"AI-generated likelihood {ai_score:.2f}")
    return "; ".join(bits)


async def _vision_llm(rc: RunCtx, state: dict, ctx: dict) -> dict | None:
    from pipeline import storage_worker as st
    from pipeline.llm import chat_vision

    photo = await st.return_photo_bytes(ctx["return_id"])
    if not photo:
        return None
    try:
        res = chat_vision(
            role="vision",
            system="You compare a customer's return photo to the product they ordered. "
                   "Answer ONLY JSON: {\"matches\": true|false, \"note\": \"<short>\"}",
            text=f"The product ordered: {ctx['item_name']} — "
                 f"{ctx.get('product_description', '')[:200]}. Does the attached photo "
                 f"plausibly show this product, its packaging, or its damage?",
            image_bytes=photo,
        )
        start, end = res.find("{"), res.rfind("}")
        return json.loads(res[start:end + 1]) if start != -1 else None
    except Exception as e:  # noqa: BLE001
        log.warning("image.vision_failed", error=str(e))
        return None


# --------------------------------------------------------------- behavior (ML + ring + LLM)
async def behavior(state: dict) -> dict:
    rc = _rc(state)
    t0 = time.perf_counter()
    ctx = state["context"]
    from pipeline import behavior_model as bm

    await bm.prepare(ctx)
    score, model_version, feats = bm.risk_score(ctx)
    ring = await bm.ring_accounts(ctx["user_id"])
    await record_local_agent(
        rc, state, agent="behavior",
        output={"risk_score": score, "model_version": model_version,
                "ring_accounts": ring, "features": feats},
        model=f"behavior_risk:{model_version}",
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
    await rc.emit(state, "node_end", "behavior",
                  {"risk_score": score, "model_version": model_version, "ring_accounts": ring})

    schema = {
        "type": "object", "required": ["pattern", "abuse_likelihood"],
        "properties": {"pattern": {"type": "string"},
                       "abuse_likelihood": {"enum": ["low", "medium", "high"]},
                       "confidence": {"type": "number"}},
    }
    facts = {
        "model_risk_score": score,
        "customer_lifetime_orders": ctx["user_order_count"],
        "customer_lifetime_returns": ctx["user_return_count"],
        "shared_fingerprint_accounts": len(ring),
        "ring_account_ids": ring[:10],
    }
    llm = await run_llm_agent(rc, state, agent="behavior", prompt_name="behavior",
                              role="reason", facts=facts, schema=schema, max_tokens=400)
    return {"behavior": {"risk_score": score, "model_version": model_version,
                         "ring_accounts": ring, **llm}}


# --------------------------------------------------------------- decision
async def decision(state: dict) -> dict:
    rc = _rc(state)
    ctx = state["context"]
    facts = {
        "return_facts": _facts(ctx),
        "intake": state.get("intake"),
        "policy": state.get("policy"),
        "image": state.get("image"),
        "behavior": state.get("behavior"),
    }
    schema = {
        "type": "object", "required": ["decision", "confidence", "risk", "reason"],
        "properties": {"decision": {"enum": ["approve", "deny", "escalate"]},
                       "confidence": {"type": "number"}, "risk": {"type": "number"},
                       "reason": {"type": "string"},
                       "signals": {"type": "array", "items": {"type": "string"}}},
    }
    out = await run_llm_agent(rc, state, agent="decision", prompt_name="decision",
                              role="reason", facts=facts, schema=schema, max_tokens=700)
    return {"decision": out}


# --------------------------------------------------------------- critic
async def critic(state: dict) -> dict:
    rc = _rc(state)
    facts = {
        "proposed_decision": state["decision"],
        "intake": state.get("intake"), "policy": state.get("policy"),
        "image": state.get("image"), "behavior": state.get("behavior"),
    }
    schema = {
        "type": "object", "required": ["agree", "veto", "concern"],
        "properties": {"agree": {"type": "boolean"}, "veto": {"type": "boolean"},
                       "concern": {"type": "string"}, "confidence": {"type": "number"}},
    }
    out = await run_llm_agent(rc, state, agent="critic", prompt_name="critic",
                              role="deep", facts=facts, schema=schema, max_tokens=400)
    return {"critic": out}


# --------------------------------------------------------------- explanation
async def explanation(state: dict) -> dict:
    rc = _rc(state)
    facts = {
        "decision": state["decision"], "critic": state.get("critic"),
        "policy_reason": state.get("policy", {}).get("reason"),
        "image_reason": state.get("image", {}).get("reason"),
        "behavior_pattern": state.get("behavior", {}).get("pattern"),
    }
    schema = {"type": "object", "required": ["explanation"],
              "properties": {"explanation": {"type": "string"}}}
    out = await run_llm_agent(rc, state, agent="explanation", prompt_name="explanation",
                              role="deep", facts=facts, schema=schema, max_tokens=300)
    return {"explanation": out["explanation"]}
