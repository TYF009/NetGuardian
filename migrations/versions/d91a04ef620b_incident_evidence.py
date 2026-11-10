"""Preserve incident links independently of the bounded UI summary."""

import sqlalchemy as sa
from alembic import op

revision = "d91a04ef620b"
down_revision = "ce2d9e13a712"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "incident_evidence",
        sa.Column("incident_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("workspace", sa.String(128), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace", "incident_id"],
            ["incidents.workspace", "incidents.id"],
            name="fk_incident_evidence_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("incident_id", "job_id", name="uq_incident_evidence_job"),
    )
    op.create_index("ix_incident_evidence_job_id", "incident_evidence", ["job_id"])
    incidents = sa.table(
        "incidents", sa.column("id"), sa.column("workspace"), sa.column("evidence", sa.JSON())
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(incidents)).mappings():
        identifiers = list(dict.fromkeys(row["evidence"]))
        if identifiers:
            connection.execute(
                table.insert(),
                [
                    dict(
                        incident_id=row["id"],
                        workspace=row["workspace"],
                        position=index + 1,
                        job_id=job_id,
                    )
                    for index, job_id in enumerate(identifiers)
                ],
            )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM incident_evidence")):
        raise RuntimeError(
            "Refusing downgrade: incident history would be lost. Export and review it first."
        )
    op.drop_table("incident_evidence")
