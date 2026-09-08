from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Order, OrderItem, Outbox, Return, ReturnPhoto
from app.ratelimit import limiter
from app.schemas import ReturnCreateOut, ReturnOut
from app.security import Principal, current_user
from app.services import mail, storage
from app.services.images import clean_image
from app.services.queue import enqueue_review

router = APIRouter(prefix="/returns", tags=["returns"])

REASON_CODES = {
    "damaged", "not_as_described", "wrong_item", "no_longer_needed",
    "defective", "arrived_late", "quality",
}


async def _photo_urls(session: AsyncSession, return_id) -> list[str]:
    keys = (
        await session.execute(
            select(ReturnPhoto.object_key).where(ReturnPhoto.return_id == return_id)
        )
    ).scalars().all()
    return [storage.presigned_get(k) for k in keys]


def _out(r: Return, photo_urls: list[str]) -> ReturnOut:
    return ReturnOut(
        id=str(r.id), order_id=str(r.order_id), order_item_id=str(r.order_item_id),
        reason_code=r.reason_code, reason_text=r.reason_text, status=r.status,
        refund_state=r.refund_state, amount=r.amount, decision=r.decision,
        decision_reason=r.decision_reason, final_decision=r.final_decision,
        created_at=r.created_at, photo_urls=photo_urls,
    )


@router.post("", response_model=ReturnCreateOut, status_code=201)
@limiter.limit("60/minute")
async def submit_return(
    request: Request,
    order_item_id: str = Form(...),
    reason_code: str = Form(...),
    reason_text: str = Form(""),
    photo: UploadFile = File(...),
    p: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ReturnCreateOut:
    if reason_code not in REASON_CODES:
        raise HTTPException(422, f"reason_code must be one of {sorted(REASON_CODES)}")

    item = (
        await session.execute(
            select(OrderItem).options(selectinload(OrderItem.order)).where(OrderItem.id == order_item_id)
        )
    ).scalar_one_or_none()
    if item is None or str(item.order.user_id) != p.user_id:
        raise HTTPException(404, "order item not found")

    dup = (
        await session.execute(
            select(Return).where(
                Return.order_item_id == order_item_id,
                Return.status.notin_(("denied",)),
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(409, "a return for this item is already in progress")

    raw = await photo.read()
    clean, content_type = clean_image(raw)
    sha = hashlib.sha256(clean).hexdigest()

    return_id = uuid.uuid4()
    key = f"returns/{return_id}/{uuid.uuid4().hex}.jpg"
    storage.put_bytes(key, clean, content_type)  # real MinIO write before the DB tx

    amount = item.unit_price * item.qty
    r = Return(
        id=return_id, order_id=item.order_id, order_item_id=item.id, user_id=p.user_id,
        reason_code=reason_code, reason_text=reason_text[:2000], status="pending",
        refund_state="none", amount=amount,
    )
    session.add(r)
    session.add(
        ReturnPhoto(
            return_id=return_id, object_key=key, content_type=content_type,
            bytes=len(clean), sha256=sha,
        )
    )
    session.add(
        Outbox(topic="return.submitted", payload={"return_id": str(return_id)})
    )
    await session.commit()  # returns + photo + outbox in one transaction

    await enqueue_review(str(return_id))  # best-effort; outbox + cron is the backstop
    mail.send(
        p.email, "We received your return request",
        f"Return {return_id} for order {item.order_id} is under review.",
    )
    return ReturnCreateOut(id=str(return_id), status="pending", amount=amount)


@router.get("", response_model=list[ReturnOut])
async def my_returns(
    p: Principal = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[ReturnOut]:
    rows = (
        await session.execute(
            select(Return).where(Return.user_id == p.user_id).order_by(Return.created_at.desc())
        )
    ).scalars().all()
    return [_out(r, await _photo_urls(session, r.id)) for r in rows]


@router.get("/{return_id}", response_model=ReturnOut)
async def get_return(
    return_id: str,
    p: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ReturnOut:
    r = await session.get(Return, return_id)
    if r is None or str(r.user_id) != p.user_id:
        raise HTTPException(404, "return not found")
    return _out(r, await _photo_urls(session, r.id))


@router.get("/{return_id}/info-request")
async def open_info_request(
    return_id: str,
    p: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from sqlalchemy import text

    row = (await session.execute(text(
        "SELECT i.id::text, i.question FROM info_requests i JOIN returns r ON r.id=i.return_id "
        "WHERE i.return_id=:r AND i.answered_at IS NULL AND r.user_id=:u "
        "ORDER BY i.created_at DESC LIMIT 1"),
        {"r": return_id, "u": p.user_id})).mappings().one_or_none()
    return dict(row) if row else {}


@router.post("/{return_id}/info-request")
async def answer_info_request(
    return_id: str,
    answer: str = Form(...),
    p: Principal = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from sqlalchemy import text

    from app.services.queue import enqueue_review

    upd = (await session.execute(text(
        "UPDATE info_requests SET answer=:a, answered_at=now() "
        "WHERE return_id=:r AND answered_at IS NULL "
        "AND return_id IN (SELECT id FROM returns WHERE user_id=:u) RETURNING id"),
        {"a": answer[:2000], "r": return_id, "u": p.user_id})).first()
    if not upd:
        raise HTTPException(404, "no open info request")
    await session.execute(text(
        "UPDATE returns SET status='pending', review_attempts=0 WHERE id=:r"), {"r": return_id})
    await session.commit()
    await enqueue_review(return_id)
    return {"answered": True, "status": "re-queued"}
