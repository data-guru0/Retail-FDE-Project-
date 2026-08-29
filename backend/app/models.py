"""Full ReturnGuard schema. One module — ~20 related tables, read top to bottom.
ponytail: single module until it genuinely hurts; split by domain if it grows.

Schema changes ship as Alembic migrations (backend/alembic/versions), never create_all.
This module is the source the baseline migration was written from and what the ORM uses.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class TS:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


PK = lambda: mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)  # noqa: E731

RETURN_STATUS = ("pending", "in_review", "escalated", "approved", "denied", "refunded", "info_requested")
REFUND_STATE = ("none", "pending", "refunded")
AUTOMATION_LEVEL = ("shadow", "suggest", "assist", "auto")
DECISION = ("approve", "deny", "escalate")
FINGERPRINT_TYPE = ("address", "device", "payment")
APPEAL_STATUS = ("open", "assigned", "resolved")
AGENT_NAMES = (
    "data_quality", "planner", "intake", "policy", "image",
    "behavior", "decision", "critic", "explanation", "governance",
)


# --------------------------------------------------------------------- identity
class User(Base, TS):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = PK()
    keycloak_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="customer")  # customer|reviewer|admin
    __table_args__ = (CheckConstraint("role in ('customer','reviewer','admin')", name="ck_user_role"),)


class Reviewer(Base, TS):
    __tablename__ = "reviewers"
    id: Mapped[uuid.UUID] = PK()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------- catalog
class Product(Base, TS):
    __tablename__ = "products"
    id: Mapped[uuid.UUID] = PK()
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    image_key: Mapped[str] = mapped_column(String(300))  # MinIO object key
    stock: Mapped[int] = mapped_column(Integer, default=100)
    __table_args__ = (CheckConstraint("price >= 0", name="ck_product_price"),)


# --------------------------------------------------------------------- orders
class Order(Base, TS):
    __tablename__ = "orders"
    id: Mapped[uuid.UUID] = PK()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="placed")
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    shipping_address: Mapped[dict] = mapped_column(JSONB)
    payment_last4: Mapped[str] = mapped_column(String(4))
    placed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    __table_args__ = (CheckConstraint("total >= 0", name="ck_order_total"),)


class OrderItem(Base, TS):
    __tablename__ = "order_items"
    id: Mapped[uuid.UUID] = PK()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    name_snapshot: Mapped[str] = mapped_column(String(300))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    qty: Mapped[int] = mapped_column(Integer)
    order: Mapped["Order"] = relationship(back_populates="items")
    __table_args__ = (CheckConstraint("qty > 0", name="ck_item_qty"),)


# --------------------------------------------------------------------- returns
class Return(Base, TS):
    __tablename__ = "returns"
    id: Mapped[uuid.UUID] = PK()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    order_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("order_items.id", ondelete="RESTRICT"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    reason_code: Mapped[str] = mapped_column(String(40))
    reason_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    refund_state: Mapped[str] = mapped_column(String(20), default="none")
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)      # agent proposal
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)  # human/gov final
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)
    claimed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    graph_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_attempts: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    __table_args__ = (
        CheckConstraint(f"status in {RETURN_STATUS}", name="ck_return_status"),
        CheckConstraint(f"refund_state in {REFUND_STATE}", name="ck_return_refund_state"),
        CheckConstraint("amount >= 0", name="ck_return_amount"),
        Index("ix_returns_status_created", "status", "created_at"),
    )


class ReturnPhoto(Base, TS):
    __tablename__ = "return_photos"
    id: Mapped[uuid.UUID] = PK()
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("returns.id", ondelete="CASCADE"), index=True)
    object_key: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(60))
    bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))


# --------------------------------------------------------------------- policy
class PolicyDoc(Base, TS):
    __tablename__ = "policy_docs"
    id: Mapped[uuid.UUID] = PK()
    version: Mapped[int] = mapped_column(Integer, index=True)
    slug: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    embedded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("version", "slug", name="uq_policy_version_slug"),)


# --------------------------------------------------------------------- agent runs
class AgentRun(Base, TS):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = PK()
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("returns.id", ondelete="CASCADE"), index=True)
    graph_run_id: Mapped[str] = mapped_column(String(64), index=True)
    agent: Mapped[str] = mapped_column(String(30))
    sa_subject: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Keycloak service account
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    automation_level: Mapped[str] = mapped_column(String(20))
    input_hash: Mapped[str] = mapped_column(String(64))
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        CheckConstraint(f"agent in {AGENT_NAMES}", name="ck_agent_run_name"),
        CheckConstraint(f"automation_level in {AUTOMATION_LEVEL}", name="ck_agent_run_level"),
    )


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("returns.id", ondelete="CASCADE"), index=True)
    graph_run_id: Mapped[str] = mapped_column(String(64), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(30))  # node_start|node_end|token|error
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------- audit (hash-chained)
class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_type: Mapped[str] = mapped_column(String(20))   # human|agent|system
    actor_id: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64))
    row_hash: Mapped[str] = mapped_column(String(64), unique=True)


# --------------------------------------------------------------------- reliability
class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[uuid.UUID] = PK()
    topic: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index(
            "ix_outbox_undispatched",
            "created_at",
            postgresql_where=text("dispatched_at IS NULL"),
        ),
    )


class DeadLetter(Base):
    __tablename__ = "dead_letter"
    id: Mapped[uuid.UUID] = PK()
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("returns.id", ondelete="CASCADE"))
    attempts: Mapped[int] = mapped_column(Integer)
    last_error: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------- governance
class FeatureFlag(Base, TS):
    __tablename__ = "feature_flags"
    id: Mapped[uuid.UUID] = PK()
    scope: Mapped[str] = mapped_column(String(80), default="global")  # 'global' or category name
    automation_level: Mapped[str] = mapped_column(String(20), default="shadow")
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    qa_sample_pct: Mapped[int] = mapped_column(Integer, default=10)
    tau_risk: Mapped[float] = mapped_column(Numeric(4, 3), default=0.30)
    tau_conf: Mapped[float] = mapped_column(Numeric(4, 3), default=0.80)
    __table_args__ = (
        UniqueConstraint("scope", name="uq_flag_scope"),
        CheckConstraint(f"automation_level in {AUTOMATION_LEVEL}", name="ck_flag_level"),
        CheckConstraint("qa_sample_pct between 0 and 100", name="ck_flag_qa_pct"),
    )


# --------------------------------------------------------------------- appeals / COI
class Appeal(Base, TS):
    __tablename__ = "appeals"
    id: Mapped[uuid.UUID] = PK()
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("returns.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)
    original_reviewer: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reviewers.id"), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint(f"status in {APPEAL_STATUS}", name="ck_appeal_status"),)


class InfoRequest(Base, TS):
    __tablename__ = "info_requests"
    id: Mapped[uuid.UUID] = PK()
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("returns.id", ondelete="CASCADE"), index=True)
    asked_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviewers.id"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgreementSample(Base):
    __tablename__ = "agreement_samples"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("returns.id", ondelete="CASCADE"))
    agent: Mapped[str] = mapped_column(String(30))
    decision_type: Mapped[str] = mapped_column(String(20))
    agent_decision: Mapped[str] = mapped_column(String(20))
    human_decision: Mapped[str] = mapped_column(String(20))
    agreed: Mapped[bool] = mapped_column(Boolean)
    kind: Mapped[str] = mapped_column(String(20), default="override")  # override|qa_sample
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# --------------------------------------------------------------------- fraud signals
class Fingerprint(Base):
    __tablename__ = "fingerprints"
    id: Mapped[uuid.UUID] = PK()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    value_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(f"kind in {FINGERPRINT_TYPE}", name="ck_fp_kind"),
        UniqueConstraint("user_id", "kind", "value_hash", name="uq_fp"),
        Index("ix_fp_kind_value", "kind", "value_hash"),
    )


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id: Mapped[uuid.UUID] = PK()
    name: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(40))
    artifact_path: Mapped[str] = mapped_column(String(300))
    metrics: Mapped[dict] = mapped_column(JSONB)
    dataset_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)
