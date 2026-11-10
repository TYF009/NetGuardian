"""Persist atomic diagnostic pair membership with tenant constraints."""

import sqlalchemy as sa
from alembic import op

revision = "ce2d9e13a712"
down_revision = "b81d245fa690"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "diagnostic_pairs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace", sa.String(128), nullable=False),
        sa.Column("cloud_job_id", sa.String(36), nullable=False),
        sa.Column("agent_job_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_pairs_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["workspace", "cloud_job_id"],
            ["jobs.workspace", "jobs.id"],
            name="fk_pairs_cloud_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["workspace", "agent_job_id"],
            ["jobs.workspace", "jobs.id"],
            name="fk_pairs_agent_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("cloud_job_id", name="uq_pairs_cloud_job"),
        sa.UniqueConstraint("agent_job_id", name="uq_pairs_agent_job"),
    )
    op.create_index("ix_diagnostic_pairs_workspace", "diagnostic_pairs", ["workspace"])


def downgrade():
    op.drop_table("diagnostic_pairs")
