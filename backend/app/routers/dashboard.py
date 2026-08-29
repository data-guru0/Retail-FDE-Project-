"""Reviewer + admin dashboard API. Every mutation writes `returns` (or
`feature_flags` / `policy_docs`) AND an `audit_log` row in one transaction.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.logging import log
from app.security import Principal, require_role
from app.services import mail
from app.services.audit import append as audit_append

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
reviewer = require_role("reviewer", "admin")
admin = require_role("admin")

CLAIM_TIMEOUT = dt.timedelta(minutes=15)


# ------------------------------------------------------------------ queue
@router.get("/queue")
async def queue(
    p: Principal = Depends(reviewer),
    session: AsyncSession = Depends(get_session),
    status: str = "escalated",
    mine: bool = False,
) -> list[dict]:
    q = """
      SELECT r.id::text, r.status, r.decision, r.decision_reason, r.amount,
             r.reason_code, r.created_at, r.claimed_by::text, r.claimed_at,
             r.graph_run_id, u.email AS customer, oi.name_snapshot AS item
      FROM returns r
      JOIN users u ON u.id = r.user_id
      JOIN order_items oi ON oi.id = r.order_item_id
      WHERE r.status = :st
    """
    params = {"st": status}
    if mine:
        q += " AND r.claimed_by = :rev"
        params["rev"] = p.reviewer_id
    q += " ORDER BY r.created_at"
    rows = (await session.execute(text(q), params)).mappings().all()
    return [dict(r) for r in rows]


@router.post("/returns/{rid}/claim")
async def claim(rid: str, p: Principal = Depends(reviewer),
                session: AsyncSession = Depends(get_session)) -> dict:
    row = (await session.execute(
        text("SELECT claimed_by::text, claimed_at FROM returns WHERE id=:r FOR UPDATE"),
        {"r": rid})).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "return not found")
    stale = row["claimed_at"] and dt.datetime.now(dt.UTC) - row["claimed_at"] > CLAIM_TIMEOUT
    if row["claimed_by"] and row["claimed_by"] != p.reviewer_id and not stale:
        raise HTTPException(409, "already claimed by another reviewer")
    await session.execute(
        text("UPDATE returns SET claimed_by=:rev, claimed_at=now() WHERE id=:r"),
        {"rev": p.reviewer_id, "r": rid})
    await audit_append(session, actor_type="human", actor_id=p.sub, action="claim",
                       entity_type="return", entity_id=rid, data={"reviewer": p.reviewer_id})
    await session.commit()
    return {"claimed": True}


@router.post("/returns/{rid}/release")
async def release(rid: str, p: Principal = Depends(reviewer),
                  session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(
        text("UPDATE returns SET claimed_by=NULL, claimed_at=NULL WHERE id=:r AND claimed_by=:rev"),
        {"r": rid, "rev": p.reviewer_id})
    await audit_append(session, actor_type="human", actor_id=p.sub, action="release",
                       entity_type="return", entity_id=rid, data={})
    await session.commit()
    return {"released": True}


# ------------------------------------------------------------------ case detail
@router.get("/returns/{rid}")
async def case_detail(rid: str, p: Principal = Depends(reviewer),
                      session: AsyncSession = Depends(get_session)) -> dict:
    r = (await session.execute(text(
        "SELECT r.*, u.email AS customer FROM returns r JOIN users u ON u.id=r.user_id "
        "WHERE r.id=:r"), {"r": rid})).mappings().one_or_none()
    if r is None:
        raise HTTPException(404, "not found")
    runs = (await session.execute(text(
        "SELECT agent, model, prompt_version, policy_version, confidence, parsed_output, "
        "tokens_in, tokens_out, cost_usd, latency_ms, sa_subject, langfuse_trace_id, created_at "
        "FROM agent_runs WHERE graph_run_id=:g ORDER BY created_at"),
        {"g": r["graph_run_id"]})).mappings().all()
    events = (await session.execute(text(
        "SELECT seq, agent, kind, payload FROM agent_run_events WHERE return_id=:r ORDER BY seq"),
        {"r": rid})).mappings().all()
    photos = (await session.execute(text(
        "SELECT object_key FROM return_photos WHERE return_id=:r"), {"r": rid})).scalars().all()
    from app.services import storage
    return {
        "return": {k: (str(v) if isinstance(v, dt.datetime) else v) for k, v in dict(r).items()},
        "agent_runs": [dict(x) for x in runs],
        "events": [dict(x) for x in events],
        "photo_urls": [storage.presigned_get(k) for k in photos],
    }


# ------------------------------------------------------------------ decide
class Decide(BaseModel):
    decision: str          # approve | deny
    note: str = ""
    confirm: bool = False   # required for deny


@router.post("/returns/{rid}/decide")
async def decide(rid: str, body: Decide, p: Principal = Depends(reviewer),
                 session: AsyncSession = Depends(get_session)) -> dict:
    if body.decision not in ("approve", "deny"):
        raise HTTPException(422, "decision must be approve or deny")
    if body.decision == "deny" and not body.confirm:
        raise HTTPException(400, "denial requires the explicit confirm step")

    r = (await session.execute(text(
        "SELECT status, decision, user_id::text, decided_by::text, amount "
        "FROM returns WHERE id=:r FOR UPDATE"), {"r": rid})).mappings().one_or_none()
    if r is None:
        raise HTTPException(404, "not found")
    if r["status"] in ("approved", "denied", "refunded"):
        raise HTTPException(409, f"already {r['status']}")

    # conflict of interest: can't action a case you previously decided
    if r["decided_by"] == p.reviewer_id:
        raise HTTPException(403, "conflict of interest: you already decided this case")

    new_status = "approved" if body.decision == "approve" else "denied"
    refund = "pending" if body.decision == "approve" else "none"
    await session.execute(text(
        "UPDATE returns SET status=:s, final_decision=:d, refund_state=:rf, "
        "decided_by=:rev, decided_at=now(), decision_reason=COALESCE(NULLIF(:note,''), decision_reason) "
        "WHERE id=:r"),
        {"s": new_status, "d": body.decision, "rf": refund, "rev": p.reviewer_id,
         "note": body.note, "r": rid})

    # agent-vs-human agreement sample
    agent_dec = r["decision"]
    if agent_dec in ("approve", "deny", "escalate"):
        agreed = agent_dec == body.decision
        await session.execute(text(
            "INSERT INTO agreement_samples (return_id, agent, decision_type, agent_decision, "
            "human_decision, agreed, kind) VALUES (:r,'decision','human_review',:a,:h,:ag,'override')"),
            {"r": rid, "a": agent_dec, "h": body.decision, "ag": agreed})

    await audit_append(session, actor_type="human", actor_id=p.sub, action=f"decide_{body.decision}",
                       entity_type="return", entity_id=rid,
                       data={"reviewer": p.reviewer_id, "note": body.note,
                             "agent_had_proposed": agent_dec, "confirm": body.confirm})
    await session.commit()

    cust = (await session.execute(text("SELECT email FROM users WHERE id=:u"),
                                  {"u": r["user_id"]})).scalar_one()
    mail.send(cust, f"Your return was {body.decision}d",
              f"Return {rid}: {body.decision}. {body.note}")
    log.info("dashboard.decide", return_id=rid, decision=body.decision, reviewer=p.reviewer_id)
    return {"status": new_status, "agent_agreement": agent_dec == body.decision}


# ------------------------------------------------------------------ request info
class InfoReq(BaseModel):
    question: str


@router.post("/returns/{rid}/request-info")
async def request_info(rid: str, body: InfoReq, p: Principal = Depends(reviewer),
                       session: AsyncSession = Depends(get_session)) -> dict:
    r = (await session.execute(text("SELECT user_id::text FROM returns WHERE id=:r"),
                               {"r": rid})).mappings().one_or_none()
    if r is None:
        raise HTTPException(404, "not found")
    await session.execute(text(
        "INSERT INTO info_requests (return_id, asked_by, question) VALUES (:r,:by,:q)"),
        {"r": rid, "by": p.reviewer_id, "q": body.question})
    await session.execute(text("UPDATE returns SET status='info_requested' WHERE id=:r"), {"r": rid})
    await audit_append(session, actor_type="human", actor_id=p.sub, action="request_info",
                       entity_type="return", entity_id=rid, data={"question": body.question})
    await session.commit()
    cust = (await session.execute(text("SELECT email FROM users WHERE id=:u"),
                                  {"u": r["user_id"]})).scalar_one()
    mail.send(cust, "We need more information about your return",
              f"Return {rid}: {body.question}\nPlease reply in the shop.")
    return {"status": "info_requested"}


# ------------------------------------------------------------------ governance (admin)
class Governance(BaseModel):
    scope: str = "global"
    automation_level: str | None = None
    kill_switch: bool | None = None
    qa_sample_pct: int | None = None
    tau_risk: float | None = None
    tau_conf: float | None = None


@router.get("/governance")
async def get_governance(p: Principal = Depends(reviewer),
                         session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(text(
        "SELECT scope, automation_level, kill_switch, qa_sample_pct, tau_risk, tau_conf "
        "FROM feature_flags ORDER BY scope"))).mappings().all()
    return [dict(r) for r in rows]


@router.put("/governance")
async def set_governance(body: Governance, p: Principal = Depends(admin),
                         session: AsyncSession = Depends(get_session)) -> dict:
    fields = {k: v for k, v in body.model_dump().items()
              if k != "scope" and v is not None}
    if not fields:
        raise HTTPException(400, "nothing to update")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    await session.execute(text(
        f"INSERT INTO feature_flags (scope, {', '.join(fields)}) "
        f"VALUES (:scope, {', '.join(':' + k for k in fields)}) "
        f"ON CONFLICT (scope) DO UPDATE SET {sets}"),
        {"scope": body.scope, **fields})
    await audit_append(session, actor_type="human", actor_id=p.sub, action="edit_governance",
                       entity_type="feature_flags", entity_id=body.scope, data=fields)
    await session.commit()
    log.info("dashboard.governance", scope=body.scope, **fields)
    return {"updated": body.scope, **fields}


# ------------------------------------------------------------------ policy editor (admin)
class PolicyEdit(BaseModel):
    slug: str
    title: str
    body: str


@router.get("/policy")
async def get_policy(p: Principal = Depends(reviewer),
                     session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(text(
        "SELECT slug, title, body, version FROM policy_docs "
        "WHERE version = (SELECT max(version) FROM policy_docs) ORDER BY slug"))).mappings().all()
    return [dict(r) for r in rows]


@router.post("/policy")
async def edit_policy(edits: list[PolicyEdit], p: Principal = Depends(admin),
                      session: AsyncSession = Depends(get_session)) -> dict:
    cur = (await session.execute(text("SELECT max(version) FROM policy_docs"))).scalar_one() or 0
    new_v = cur + 1
    existing = {r["slug"]: r for r in (await session.execute(text(
        "SELECT slug, title, body FROM policy_docs WHERE version=:v"), {"v": cur})).mappings().all()}
    edited = {e.slug: e for e in edits}
    for slug, row in existing.items():
        e = edited.get(slug)
        title = e.title if e else row["title"]
        body_ = e.body if e else row["body"]
        await session.execute(text(
            "INSERT INTO policy_docs (version, slug, title, body, active) "
            "VALUES (:v,:s,:t,:b,true)"),
            {"v": new_v, "s": slug, "t": title, "b": body_})
    await session.execute(text("UPDATE policy_docs SET active=false WHERE version=:v"), {"v": cur})
    await audit_append(session, actor_type="human", actor_id=p.sub, action="edit_policy",
                       entity_type="policy_docs", entity_id=str(new_v),
                       data={"slugs": [e.slug for e in edits], "new_version": new_v})
    await session.commit()

    # re-embed to Qdrant via the worker
    from app.services.queue import _pool  # noqa: F401
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.settings import get_settings
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    await pool.enqueue_job("reembed_policy")
    log.info("dashboard.policy_edit", new_version=new_v)
    return {"new_version": new_v, "reembed": "queued"}
