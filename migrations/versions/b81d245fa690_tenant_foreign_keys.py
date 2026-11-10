"""Enforce tenant-scoped relational links; reject inconsistent legacy data."""

import sqlalchemy as sa
from alembic import op

revision = "b81d245fa690"
down_revision = "76bda0e91542"
branch_labels = None
depends_on = None

TABLES = (
    "agents",
    "jobs",
    "monitors",
    "incidents",
    "reports",
    "investigations",
    "enrollments",
    "audit_events",
    "monitor_runs",
)
UNIQUE = ("agents", "jobs", "monitors", "incidents", "reports")
LINKS = {
    "jobs": (("agent_id", "agents"),),
    "monitors": (("agent_id", "agents"),),
    "incidents": (("monitor_id", "monitors"),),
    "reports": (("incident_id", "incidents"),),
    "investigations": (("report_id", "reports"),),
    "monitor_runs": (("job_id", "jobs"), ("monitor_id", "monitors")),
}


def upgrade():
    connection = op.get_bind()
    # Check before the first DDL statement. Never delete or reassign invalid history.
    for table in TABLES[:-1]:
        if connection.scalar(
            sa.text(
                f"SELECT COUNT(*) FROM {table} c LEFT JOIN workspaces p "  # noqa: S608 - fixed table list
                "ON c.workspace=p.id WHERE p.id IS NULL"
            )
        ):
            raise RuntimeError(f"Orphan workspace in {table}; repair before migration")
    for table, links in LINKS.items():
        if table == "monitor_runs":
            continue
        for column, parent in links:
            if connection.scalar(
                sa.text(
                    f"SELECT COUNT(*) FROM {table} c LEFT JOIN {parent} p "  # noqa: S608 - fixed names
                    f"ON c.{column}=p.id AND c.workspace=p.workspace "
                    f"WHERE c.{column} IS NOT NULL AND p.id IS NULL"
                )
            ):
                raise RuntimeError(f"Invalid tenant link in {table}; repair before migration")
    if connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM monitor_runs r LEFT JOIN jobs j ON r.job_id=j.id "
            "LEFT JOIN monitors m ON r.monitor_id=m.id "
            "WHERE j.id IS NULL OR m.id IS NULL OR j.workspace<>m.workspace"
        )
    ):
        raise RuntimeError("Invalid monitor run tenant link; repair before migration")
    op.add_column("monitor_runs", sa.Column("workspace", sa.String(128), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE monitor_runs SET workspace=(SELECT workspace FROM jobs WHERE jobs.id=job_id)"
        )
    )
    for table in UNIQUE:
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(f"uq_{table}_workspace_id", ["workspace", "id"])
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            if table == "monitor_runs":
                batch.alter_column("workspace", existing_type=sa.String(128), nullable=False)
            batch.create_foreign_key(
                f"fk_{table}_workspace",
                "workspaces",
                ["workspace"],
                ["id"],
                deferrable=True,
                initially="DEFERRED",
            )
            for column, parent in LINKS.get(table, ()):
                batch.create_foreign_key(
                    f"fk_{table}_{column}_tenant",
                    parent,
                    ["workspace", column],
                    ["workspace", "id"],
                    deferrable=True,
                    initially="DEFERRED",
                )
    if connection.dialect.name == "sqlite":
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
            raise RuntimeError("Foreign key validation failed")


def downgrade():
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            for column, _ in LINKS.get(table, ()):
                batch.drop_constraint(f"fk_{table}_{column}_tenant", type_="foreignkey")
            batch.drop_constraint(f"fk_{table}_workspace", type_="foreignkey")
    for table in reversed(UNIQUE):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"uq_{table}_workspace_id", type_="unique")
    with op.batch_alter_table("monitor_runs") as batch:
        batch.drop_column("workspace")
