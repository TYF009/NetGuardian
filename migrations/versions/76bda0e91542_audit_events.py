"""Record transaction-bound operator audit events."""

import sqlalchemy as sa
from alembic import op

revision = "76bda0e91542"
down_revision = "6eacf7b14120"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("actor_kind", sa.String(32), nullable=False),
    )
    op.create_index("ix_audit_events_workspace", "audit_events", ["workspace"])


def downgrade():
    op.drop_index("ix_audit_events_workspace", table_name="audit_events")
    op.drop_table("audit_events")
