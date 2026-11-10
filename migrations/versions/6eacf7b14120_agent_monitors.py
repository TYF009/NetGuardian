"""Allow monitors to target an enrolled agent."""

import sqlalchemy as sa
from alembic import op

revision = "6eacf7b14120"
down_revision = "2da7379c3e58"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("monitors", sa.Column("agent_id", sa.String(36), nullable=True))
    op.create_index("ix_monitors_agent_id", "monitors", ["agent_id"])


def downgrade():
    op.drop_index("ix_monitors_agent_id", table_name="monitors")
    op.drop_column("monitors", "agent_id")
