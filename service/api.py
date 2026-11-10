"""Authenticated durable diagnostic jobs; execution belongs to the worker."""

import secrets
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError

from probe_core.contracts import Measurement
from probe_core.policy import PolicyDenied
from service.agents import mount_agent_routes
from service.audit import mount_audit_routes, record_audit
from service.database import (
    Agent,
    DiagnosticPair,
    Incident,
    Job,
    Monitor,
    MonitorRun,
    Workspace,
    database,
    initialize_workspaces,
)
from service.evidence import mount_evidence_routes
from service.investigation import mount_investigation_routes
from service.job_lifecycle import expire_cloud_jobs
from service.monitoring import telemetry_state
from service.quotas import within_job_rate
from service.rate_limits import RequestAdmission
from service.request_limits import RequestBodyLimit
from service.schema import require_schema
from service.settings import Settings


class CreateJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["dns", "tcp", "tls", "http", "icmp", "traceroute"]
    target: str = Field(min_length=1, max_length=2048)
    agent_id: UUID | None = None


JobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class JobAccepted(BaseModel):
    id: str
    state: Literal["queued"]


class JobSummary(BaseModel):
    id: str
    kind: Literal["dns", "tcp", "tls", "http", "icmp", "traceroute"]
    target: str
    state: JobState
    created_at: datetime


class JobDetail(BaseModel):
    id: str
    state: JobState
    result: Measurement | None


class CreatePair(CreateJob):
    agent_id: UUID


class CreateMonitor(CreateJob):
    name: str = Field(min_length=1, max_length=128)
    interval_seconds: int = Field(default=60, ge=60, le=86400)
    open_after: int = Field(default=3, ge=1, le=20)
    recover_after: int = Field(default=2, ge=1, le=20)


class UpdateMonitor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)


def create_app(settings: Settings) -> FastAPI:
    engine, sessions = database(settings.database_url)
    require_schema(engine)
    initialize_workspaces(engine, settings.credentials.values())
    app = FastAPI(title="NetGuardian API", version="0.2.0")
    app.add_middleware(RequestBodyLimit)
    app.add_middleware(RequestAdmission, credentials=settings.credentials)
    app.state.sessions = sessions
    bearer = HTTPBearer()

    credential_dependency = Depends(bearer)

    def workspace(auth: HTTPAuthorizationCredentials = credential_dependency):
        if not auth.credentials.isascii():
            raise HTTPException(401, "Invalid credential")
        for token, tenant in settings.credentials.items():
            if secrets.compare_digest(auth.credentials, token):
                return tenant
        raise HTTPException(401, "Invalid credential")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def readiness():
        try:
            require_schema(engine)
        except (SQLAlchemyError, RuntimeError):
            raise HTTPException(503, "Database unavailable or migration required") from None
        return {"status": "ready", "database": "reachable", "schema": "current"}

    @app.get("/api/targets")
    def targets(tenant: str = Depends(workspace)):
        policy = settings.policies.get(tenant)
        return {"origins": sorted(policy.allowed_origins) if policy else []}

    def enqueue(body: CreateJob, tenant: str, paired=False):
        policy = settings.policies.get(tenant)
        if not policy:
            raise HTTPException(403, "No target policy configured")
        try:
            policy.authorize(body.target)
        except PolicyDenied as exc:
            raise HTTPException(403, str(exc)) from exc
        with sessions.begin() as session:
            session.execute(
                update(Workspace)
                .where(Workspace.id == tenant)
                .values(revision=Workspace.revision + 1)
            )
            expire_cloud_jobs(session, datetime.now(UTC), tenant)
            count = session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.workspace == tenant, Job.state.in_(["queued", "running"]))
            )
            if not within_job_rate(session, tenant, 2 if paired else 1):
                raise HTTPException(
                    429, "Workspace job rate limit reached", headers={"Retry-After": "60"}
                )
            if count + (2 if paired else 1) > 20:
                raise HTTPException(429, "Pending job limit reached")
            if body.agent_id is not None:
                agent = session.scalar(
                    select(Agent).where(
                        Agent.id == str(body.agent_id),
                        Agent.workspace == tenant,
                        Agent.revoked == 0,
                    )
                )
                if agent is None:
                    raise HTTPException(404, "Agent not found")
            now = datetime.now(UTC)
            destinations = (
                [None, str(body.agent_id)]
                if paired
                else [str(body.agent_id) if body.agent_id else None]
            )
            jobs = [
                Job(
                    agent_id=destination,
                    workspace=tenant,
                    kind=body.kind,
                    target=body.target,
                    policy_version=policy.version,
                    created_at=now,
                )
                for destination in destinations
            ]
            session.add_all(jobs)
            session.flush()
            for job in jobs:
                record_audit(session, tenant, "job.queued", job.id)
            if paired:
                pair = DiagnosticPair(
                    workspace=tenant,
                    cloud_job_id=jobs[0].id,
                    agent_job_id=jobs[1].id,
                    created_at=now,
                )
                session.add(pair)
                session.flush()
                return {
                    "id": pair.id,
                    "cloud_job_id": jobs[0].id,
                    "agent_job_id": jobs[1].id,
                    "state": "queued",
                    "limitation": "Execution times are not synchronized.",
                }
            return {"id": jobs[0].id, "state": jobs[0].state}

    @app.post("/api/jobs", status_code=202, response_model=JobAccepted)
    def submit(body: CreateJob, tenant: str = Depends(workspace)):
        return enqueue(body, tenant)

    @app.post("/api/diagnostic-pairs", status_code=202)
    def submit_pair(body: CreatePair, tenant: str = Depends(workspace)):
        return enqueue(body, tenant, paired=True)

    @app.get("/api/diagnostic-pairs")
    def pair_history(tenant: str = Depends(workspace)):
        with sessions() as session:
            return [
                {
                    "id": pair.id,
                    "cloud_job_id": pair.cloud_job_id,
                    "agent_job_id": pair.agent_job_id,
                    "created_at": pair.created_at,
                }
                for pair in session.scalars(
                    select(DiagnosticPair)
                    .where(DiagnosticPair.workspace == tenant)
                    .order_by(DiagnosticPair.created_at.desc(), DiagnosticPair.id.desc())
                    .limit(100)
                )
            ]

    @app.get("/api/jobs", response_model=list[JobSummary])
    def history(tenant: str = Depends(workspace)):
        with sessions.begin() as session:
            expire_cloud_jobs(session, datetime.now(UTC), tenant)
            jobs = session.scalars(
                select(Job)
                .where(Job.workspace == tenant)
                .order_by(Job.created_at.desc())
                .limit(100)
            ).all()
            return [
                {
                    "id": j.id,
                    "kind": j.kind,
                    "target": j.target,
                    "state": j.state,
                    "created_at": j.created_at,
                }
                for j in jobs
            ]

    @app.get("/api/jobs/{job_id}", response_model=JobDetail)
    def detail(job_id: str, tenant: str = Depends(workspace)):
        with sessions.begin() as session:
            expire_cloud_jobs(session, datetime.now(UTC), tenant)
            job = session.scalar(select(Job).where(Job.id == job_id, Job.workspace == tenant))
            if job is None:
                raise HTTPException(404, "Job not found")
            return {"id": job.id, "state": job.state, "result": job.result}

    @app.post("/api/monitors", status_code=201)
    def add_monitor(body: CreateMonitor, tenant: str = Depends(workspace)):
        policy = settings.policies.get(tenant)
        if policy is None:
            raise HTTPException(403, "No target policy configured")
        try:
            policy.authorize(body.target)
        except PolicyDenied as exc:
            raise HTTPException(403, str(exc)) from exc
        with sessions.begin() as session:
            session.execute(
                update(Workspace)
                .where(Workspace.id == tenant)
                .values(revision=Workspace.revision + 1)
            )
            count = session.scalar(
                select(func.count()).select_from(Monitor).where(Monitor.workspace == tenant)
            )
            if count >= 20:
                raise HTTPException(429, "Monitor limit reached")
            if body.agent_id is not None:
                agent = session.scalar(
                    select(Agent).where(
                        Agent.id == str(body.agent_id),
                        Agent.workspace == tenant,
                        Agent.revoked == 0,
                    )
                )
                if agent is None:
                    raise HTTPException(404, "Agent not found")
            monitor = Monitor(
                workspace=tenant,
                agent_id=str(body.agent_id) if body.agent_id else None,
                **body.model_dump(exclude={"agent_id"}),
            )
            session.add(monitor)
            session.flush()
            record_audit(session, tenant, "monitor.created", monitor.id)
            return {"id": monitor.id}

    @app.get("/api/monitors")
    def monitors(tenant: str = Depends(workspace)):
        with sessions() as session:
            return [
                {
                    "id": m.id,
                    "name": m.name,
                    "target": m.target,
                    "kind": m.kind,
                    "enabled": bool(m.enabled),
                    "agent_id": m.agent_id,
                    "interval_seconds": m.interval_seconds,
                    "next_due": m.next_due,
                    "failure_count": m.failure_count,
                    "telemetry": telemetry_state(session, m),
                }
                for m in session.scalars(select(Monitor).where(Monitor.workspace == tenant))
            ]

    @app.get("/api/monitors/{monitor_id}/runs")
    def monitor_history(monitor_id: UUID, tenant: str = Depends(workspace)):
        with sessions() as session:
            monitor = session.scalar(
                select(Monitor).where(Monitor.id == str(monitor_id), Monitor.workspace == tenant)
            )
            if monitor is None:
                raise HTTPException(404, "Monitor not found")
            jobs = session.scalars(
                select(Job)
                .join(MonitorRun, MonitorRun.job_id == Job.id)
                .where(MonitorRun.monitor_id == monitor.id, Job.workspace == tenant)
                .order_by(Job.created_at.desc(), Job.id.desc())
                .limit(100)
            ).all()
            return {
                "monitor_id": monitor.id,
                "name": monitor.name,
                "runs": [
                    {
                        "id": job.id,
                        "created_at": job.created_at.replace(tzinfo=UTC),
                        "state": job.state,
                        "status": job.result.get("status") if job.result else None,
                        "http_status": job.result.get("http_status") if job.result else None,
                        "timings": job.result.get("timings", {}) if job.result else {},
                    }
                    for job in reversed(jobs)
                ],
            }

    def set_monitor_enabled(monitor_id: str, enabled: bool, tenant: str):
        with sessions.begin() as session:
            # Use the scheduler's workspace lock so pause cannot race a new enqueue.
            session.execute(
                update(Workspace)
                .where(Workspace.id == tenant)
                .values(revision=Workspace.revision + 1)
            )
            monitor = session.scalar(
                select(Monitor).where(Monitor.id == monitor_id, Monitor.workspace == tenant)
            )
            if monitor is None:
                raise HTTPException(404, "Monitor not found")
            if enabled:
                if monitor.agent_id is not None:
                    agent = session.scalar(
                        select(Agent).where(
                            Agent.id == monitor.agent_id,
                            Agent.workspace == tenant,
                            Agent.revoked == 0,
                        )
                    )
                    if agent is None:
                        raise HTTPException(409, "Monitor agent unavailable or revoked")
                policy = settings.policies.get(tenant)
                if policy is None:
                    raise HTTPException(403, "No target policy configured")
                try:
                    policy.authorize(monitor.target)
                except PolicyDenied as exc:
                    raise HTTPException(403, str(exc)) from exc
            if bool(monitor.enabled) != enabled:
                record_audit(
                    session, tenant, "monitor.resumed" if enabled else "monitor.paused", monitor.id
                )
                monitor.enabled = int(enabled)
                if enabled:
                    monitor.next_due = datetime.now(UTC)
                    monitor.failure_count = monitor.success_count = 0
            return {"id": monitor.id, "enabled": bool(monitor.enabled)}

    @app.patch("/api/monitors/{monitor_id}")
    def update_monitor(monitor_id: str, body: UpdateMonitor, tenant: str = Depends(workspace)):
        return set_monitor_enabled(monitor_id, body.enabled, tenant)

    @app.delete("/api/monitors/{monitor_id}", status_code=204)
    def disable_monitor(monitor_id: str, tenant: str = Depends(workspace)):
        set_monitor_enabled(monitor_id, False, tenant)

    @app.get("/api/incidents")
    def incidents(tenant: str = Depends(workspace)):
        with sessions() as session:
            return [
                {
                    "id": i.id,
                    "monitor_id": i.monitor_id,
                    "state": i.state,
                    "opened_at": i.opened_at,
                    "recovered_at": i.recovered_at,
                    "evidence": i.evidence,
                }
                for i in session.scalars(
                    select(Incident)
                    .where(Incident.workspace == tenant)
                    .order_by(Incident.opened_at.desc())
                    .limit(100)
                )
            ]

    mount_audit_routes(app, sessions, workspace)
    mount_agent_routes(app, sessions, workspace)
    mount_evidence_routes(app, sessions, workspace)
    mount_investigation_routes(app, sessions, workspace)
    return app


def app_factory():
    return create_app(Settings.from_environment())
