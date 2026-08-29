"""server defaults on feature_flags so per-category rows can be created with a
partial column list (the governance editor).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-29
"""
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE feature_flags ALTER COLUMN automation_level SET DEFAULT 'shadow'")
    op.execute("ALTER TABLE feature_flags ALTER COLUMN kill_switch SET DEFAULT false")
    op.execute("ALTER TABLE feature_flags ALTER COLUMN qa_sample_pct SET DEFAULT 10")
    op.execute("ALTER TABLE feature_flags ALTER COLUMN tau_risk SET DEFAULT 0.30")
    op.execute("ALTER TABLE feature_flags ALTER COLUMN tau_conf SET DEFAULT 0.80")


def downgrade() -> None:
    for col in ("automation_level", "kill_switch", "qa_sample_pct", "tau_risk", "tau_conf"):
        op.execute(f"ALTER TABLE feature_flags ALTER COLUMN {col} DROP DEFAULT")
