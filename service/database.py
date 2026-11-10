"""SQLAlchemy persistence shared by the API and worker."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from service.timestamps import UTCDateTime


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_jobs_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("workspace", "id", name="uq_jobs_workspace_id"),
        ForeignKeyConstraint(
            ["workspace", "agent_id"],
            ["agents.workspace", "agents.id"],
            name="fk_jobs_agent_id_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(2048))
    policy_version: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lease_token: Mapped[str | None] = mapped_column(String(36))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON)


def database(url: str):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine, sessionmaker(engine, expire_on_commit=False)


class Monitor(Base):
    __tablename__ = "monitors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_monitors_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("workspace", "id", name="uq_monitors_workspace_id"),
        ForeignKeyConstraint(
            ["workspace", "agent_id"],
            ["agents.workspace", "agents.id"],
            name="fk_monitors_agent_id_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace: Mapped[str] = mapped_column(String(128), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(128))
    target: Mapped[str] = mapped_column(String(2048))
    kind: Mapped[str] = mapped_column(String(16))
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    next_due: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    open_after: Mapped[int] = mapped_column(Integer, default=3)
    recover_after: Mapped[int] = mapped_column(Integer, default=2)


class MonitorRun(Base):
    __tablename__ = "monitor_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_monitor_runs_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["workspace", "job_id"],
            ["jobs.workspace", "jobs.id"],
            name="fk_monitor_runs_job_id_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["workspace", "monitor_id"],
            ["monitors.workspace", "monitors.id"],
            name="fk_monitor_runs_monitor_id_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    workspace: Mapped[str] = mapped_column(String(128))
    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    monitor_id: Mapped[str] = mapped_column(String(36), index=True)
    processed: Mapped[int] = mapped_column(Integer, default=0)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_incidents_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("workspace", "id", name="uq_incidents_workspace_id"),
        ForeignKeyConstraint(
            ["workspace", "monitor_id"],
            ["monitors.workspace", "monitors.id"],
            name="fk_incidents_monitor_id_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace: Mapped[str] = mapped_column(String(128), index=True)
    monitor_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(16), default="open")
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))
    recovered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    evidence: Mapped[list] = mapped_column(JSON, default=list)


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_agents_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("workspace", "id", name="uq_agents_workspace_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128))
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True)
    revoked: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_enrollments_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    consumed: Mapped[int] = mapped_column(Integer, default=0)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_reports_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("workspace", "id", name="uq_reports_workspace_id"),
        ForeignKeyConstraint(
            ["workspace", "incident_id"],
            ["incidents.workspace", "incidents.id"],
            name="fk_reports_incident_id_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace: Mapped[str] = mapped_column(String(128), index=True)
    incident_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))
    snapshot: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_investigations_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["workspace", "report_id"],
            ["reports.workspace", "reports.id"],
            name="fk_investigations_report_id_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace: Mapped[str] = mapped_column(String(128), index=True)
    report_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict] = mapped_column(JSON)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_audit_events_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))
    action: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(36))
    actor_kind: Mapped[str] = mapped_column(String(32), default="workspace_operator")


def initialize_workspaces(engine, tenants):
    """Atomically insert configured workspaces without resetting existing state."""
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError("NetGuardian supports PostgreSQL and SQLite databases")
    # Stable ordering avoids opposite lock acquisition when multiple APIs start.
    with engine.begin() as connection:
        for tenant in sorted(set(tenants)):
            connection.execute(
                insert(Workspace)
                .values(id=tenant, revision=0)
                .on_conflict_do_nothing(index_elements=[Workspace.id])
            )


class DiagnosticPair(Base):
    __tablename__ = "diagnostic_pairs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace"],
            ["workspaces.id"],
            name="fk_pairs_workspace",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["workspace", "cloud_job_id"],
            ["jobs.workspace", "jobs.id"],
            name="fk_pairs_cloud_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["workspace", "agent_job_id"],
            ["jobs.workspace", "jobs.id"],
            name="fk_pairs_agent_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("cloud_job_id", name="uq_pairs_cloud_job"),
        UniqueConstraint("agent_job_id", name="uq_pairs_agent_job"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace: Mapped[str] = mapped_column(String(128), index=True)
    cloud_job_id: Mapped[str] = mapped_column(String(36))
    agent_job_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(UTC))


class IncidentEvidence(Base):
    """Append-only incident links, including identifiers with missing measurements."""

    __tablename__ = "incident_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace", "incident_id"],
            ["incidents.workspace", "incidents.id"],
            name="fk_incident_evidence_tenant",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("incident_id", "job_id", name="uq_incident_evidence_job"),
    )
    incident_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace: Mapped[str] = mapped_column(String(128))
    job_id: Mapped[str] = mapped_column(String(36), index=True)
