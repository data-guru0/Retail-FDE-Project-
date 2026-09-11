"""Appeals + the conflict-of-interest guard.

A denied return can be appealed by the customer. That creates a review task
routed to a **different** reviewer; a reviewer cannot action their own appeal or
a case they previously decided.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.security import Principal, current_user, require_role
from app.services.audit import append as audit_append

router = APIRouter(prefix="/appeals", tags=["appeals"])
reviewer = require_role("reviewer", "admin")


class AppealIn(BaseModel):
    reason: str


@router.post("/returns/{rid}")
async def open_appeal(rid: str, body: AppealIn, p: Principal = Depends(current_user),
                      session: AsyncSession = Depends(get_session)) -> dict:
    r = (await session.execute(text(
        "SELECT status, user_id::text, decided_by::text FROM returns WHERE id=:r"),
        {"r": rid})).mappings().one_or_none()
    if r is None or r["user_id"] != p.user_id:
        raise HTTPException(404, "return not found")
    if r["status"] != "denied":
        raise HTTPException(409, "only a denied return can be appealed")

    dup = (await session.execute(text(
        "SELECT 1 FROM appeals WHERE return_id=:r AND status <> 'resolved'"),
        {"r": rid})).first()
    if dup:
        raise HTTPException(409, "an appeal is already open for this return")

    # route to a different reviewer than the one who decided it
    other = (await session.execute(text(
        "SELECT rv.id::text FROM reviewers rv WHERE rv.active AND rv.id <> :orig "
        "ORDER BY random() LIMIT 1"),
        {"orig": r["decided_by"]})).scalar_one_or_none()
    await session.execute(text(
        "INSERT INTO appeals (return_id, reason, status, assigned_to, original_reviewer) "
        "VALUES (:r,:reason,'assigned',:asg,:orig)"),
        {"r": rid, "reason": body.reason, "asg": other, "orig": r["decided_by"]})
    await session.execute(text(
        "UPDATE returns SET status='escalated', claimed_by=NULL, claimed_at=NULL WHERE id=:r"),
        {"r": rid})
    await audit_append(session, actor_type="human", actor_id=p.sub, action="appeal_open",
                       entity_type="return", entity_id=rid,
                       data={"reason": body.reason, "routed_to": other,
                             "original_reviewer": r["decided_by"]})
    await session.commit()
    return {"appeal": "assigned", "assigned_to": other, "coi_excluded": r["decided_by"]}


@router.get("")
async def list_appeals(p: Principal = Depends(reviewer),
                       session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(text(
        "SELECT a.id::text, a.return_id::text, a.reason, a.status, a.assigned_to::text, "
        "a.original_reviewer::text, a.outcome FROM appeals a ORDER BY a.created_at DESC"))).mappings().all()
    return [dict(r) for r in rows]


@router.post("/{appeal_id}/resolve")
async def resolve_appeal(appeal_id: str, outcome: str, p: Principal = Depends(reviewer),
                         session: AsyncSession = Depends(get_session)) -> dict:
    if outcome not in ("approve", "deny"):
        raise HTTPException(422, "outcome must be approve or deny")
    a = (await session.execute(text(
        "SELECT return_id::text, assigned_to::text, original_reviewer::text, status "
        "FROM appeals WHERE id=:a FOR UPDATE"), {"a": appeal_id})).mappings().one_or_none()
    if a is None:
        raise HTTPException(404, "appeal not found")
    if a["original_reviewer"] == p.reviewer_id:
        raise HTTPException(403, "conflict of interest: you decided the original case")
    if a["assigned_to"] not in (None, p.reviewer_id):
        raise HTTPException(403, "this appeal is assigned to a different reviewer")

    new_status = "approved" if outcome == "approve" else "denied"
    refund = "pending" if outcome == "approve" else "none"
    await session.execute(text(
        "UPDATE returns SET status=:s, final_decision=:o, decided_by=:rev, decided_at=now(), "
        "refund_state=:rf WHERE id=:r"),
        {"s": new_status, "o": outcome, "rf": refund, "rev": p.reviewer_id, "r": a["return_id"]})
    await session.execute(text(
        "UPDATE appeals SET status='resolved', outcome=:o, resolved_at=now() WHERE id=:a"),
        {"o": outcome, "a": appeal_id})
    await audit_append(session, actor_type="human", actor_id=p.sub, action="appeal_resolve",
                       entity_type="appeal", entity_id=appeal_id,
                       data={"outcome": outcome, "return_id": a["return_id"]})
    await session.commit()
    return {"resolved": outcome}
