"""server-side gen_random_uuid() defaults on all uuid primary keys

so raw-SQL inserts (worker) don't need to supply the id.

Revision ID: a1b2c3d4e5f6
Revises: 73c8d6d4999e
Create Date: 2026-08-29
"""
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "73c8d6d4999e"
branch_labels = None
depends_on = None

_TABLES = [
    "users", "reviewers", "products", "orders", "order_items", "returns",
    "return_photos", "policy_docs", "agent_runs", "feature_flags", "appeals",
    "info_requests", "fingerprints", "model_registry", "dead_letter", "outbox",
]


def upgrade() -> None:
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ALTER COLUMN id SET DEFAULT gen_random_uuid()")


def downgrade() -> None:
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ALTER COLUMN id DROP DEFAULT")
