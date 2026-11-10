"""Agent enrollment and scoped outbound polling protocol."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, update

from probe_core.contracts import Measurement, ProbeRequest, configuration_hash
from service.audit import record_audit
from service.database import Agent, Enrollment, Job, Monitor
from service.job_lifecycle import AGENT_QUEUE_MAX_AGE, expire_agent_jobs


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class EnrollmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)


class RedeemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=128)


class RotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ResultUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_token: str = Field(min_length=36, max_length=36)
    measurement: Measurement


def mount_agent_routes(app, sessions, workspace):
    bearer_dependency = Depends(HTTPBearer())

    def identity(auth: HTTPAuthorizationCredentials = bearer_dependency):
        with sessions() as session:
            agent = session.scalar(
                select(Agent).where(
                    Agent.credential_hash == digest(auth.credentials), Agent.revoked == 0
                )
            )
            if agent is None:
                raise HTTPException(401, "Invalid agent credential")
            return agent.id

    @app.post("/api/agent/rotate")
    def rotate(body: RotateRequest, auth: HTTPAuthorizationCredentials = bearer_dependency):
        current_hash, next_hash = digest(auth.credentials), digest(body.credential)
        with sessions.begin() as session:
            agent = session.scalar(
                select(Agent).where(Agent.credential_hash == current_hash, Agent.revoked == 0)
            )
            if agent is None:
                raise HTTPException(401, "Invalid agent credential")
            if current_hash == next_hash:
                return {"rotated": True}
            if session.scalar(select(Agent.id).where(Agent.credential_hash == next_hash)):
                raise HTTPException(409, "Credential unavailable")
            changed = session.execute(
                update(Agent)
                .where(
                    Agent.id == agent.id, Agent.credential_hash == current_hash, Agent.revoked == 0
                )
                .values(credential_hash=next_hash)
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Credential changed concurrently")
            record_audit(
                session, agent.workspace, "agent.credential_rotated", agent.id, actor_kind="agent"
            )
            return {"rotated": True}

    @app.post("/api/agents/enrollment", status_code=201)
    def issue(body: EnrollmentRequest, tenant: str = Depends(workspace)):
        token = secrets.token_urlsafe(32)
        with sessions.begin() as session:
            session.add(
                Enrollment(
                    token_hash=digest(token),
                    workspace=tenant,
                    name=body.name,
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )
            # Issuance affects the workspace; do not copy tokens, hashes or names to audit.
            record_audit(session, tenant, "agent.enrollment_issued", str(uuid4()))
        return {"token": token, "expires_in_seconds": 600}

    @app.post("/api/agent/enroll", status_code=201)
    def redeem(body: RedeemRequest):
        with sessions.begin() as session:
            claimed = session.execute(
                update(Enrollment)
                .where(
                    Enrollment.token_hash == digest(body.token),
                    Enrollment.consumed == 0,
                    Enrollment.expires_at > datetime.now(UTC),
                )
                .values(consumed=1)
            )
            if claimed.rowcount != 1:
                raise HTTPException(401, "Invalid or expired enrollment token")
            enrollment = session.get(Enrollment, digest(body.token))
            credential = secrets.token_urlsafe(32)
            agent = Agent(
                workspace=enrollment.workspace,
                name=enrollment.name,
                credential_hash=digest(credential),
            )
            session.add(agent)
            session.flush()
            record_audit(
                session,
                enrollment.workspace,
                "agent.enrolled",
                agent.id,
                actor_kind="enrollment_token_holder",
            )
            return {"agent_id": agent.id, "credential": credential}

    @app.get("/api/agents")
    def agents(tenant: str = Depends(workspace)):
        with sessions() as session:
            return [
                {"id": a.id, "name": a.name, "revoked": bool(a.revoked), "last_seen": a.last_seen}
                for a in session.scalars(select(Agent).where(Agent.workspace == tenant))
            ]

    @app.delete("/api/agents/{agent_id}", status_code=204)
    def revoke(agent_id: str, tenant: str = Depends(workspace)):
        with sessions.begin() as session:
            changed = session.execute(
                update(Agent)
                .where(Agent.id == agent_id, Agent.workspace == tenant)
                .values(revoked=1)
            )
            if changed.rowcount != 1:
                raise HTTPException(404, "Agent not found")
            record_audit(session, tenant, "agent.revoked", agent_id)
            session.execute(
                update(Monitor)
                .where(Monitor.agent_id == agent_id, Monitor.workspace == tenant)
                .values(enabled=0)
            )
            session.execute(
                update(Job)
                .where(
                    Job.agent_id == agent_id,
                    Job.workspace == tenant,
                    Job.state.in_(["queued", "running"]),
                )
                .values(state="failed", lease_token=None, lease_until=None)
            )

    @app.post("/api/agent/poll")
    def poll(agent_id: str = Depends(identity)):
        now = datetime.now(UTC)
        with sessions.begin() as session:
            live = session.execute(
                update(Agent).where(Agent.id == agent_id, Agent.revoked == 0).values(last_seen=now)
            )
            if live.rowcount != 1:
                raise HTTPException(401, "Agent revoked")
            expire_agent_jobs(session, now, agent_id)
            eligible = (
                (Job.agent_id == agent_id)
                & (Job.created_at >= now - AGENT_QUEUE_MAX_AGE)
                & or_(Job.state == "queued", (Job.state == "running") & (Job.lease_until < now))
            )
            job = session.scalar(
                select(Job).where(eligible, Job.attempts < 3).order_by(Job.created_at).limit(1)
            )
            if job is None:
                return {"job": None}
            lease = str(uuid4())
            claimed = session.execute(
                update(Job)
                .execution_options(synchronize_session="fetch")
                .where(Job.id == job.id, eligible)
                .values(
                    state="running",
                    attempts=Job.attempts + 1,
                    lease_token=lease,
                    lease_until=now + timedelta(seconds=30),
                )
            )
            if claimed.rowcount != 1:
                return {"job": None}
            return {
                "job": {
                    "schema_version": "1",
                    "job_id": job.id,
                    "kind": job.kind,
                    "target": job.target,
                    "policy_version": job.policy_version,
                    "deadline_ms": 10000,
                },
                "lease_token": lease,
                "attempt": job.attempts,
                "expires_at": (now + timedelta(seconds=30)).isoformat(),
            }

    @app.post("/api/agent/results")
    def upload(body: ResultUpload, agent_id: str = Depends(identity)):
        result = body.measurement
        with sessions.begin() as session:
            live = session.execute(
                update(Agent)
                .where(Agent.id == agent_id, Agent.revoked == 0)
                .values(last_seen=datetime.now(UTC))
            )
            if live.rowcount != 1:
                raise HTTPException(401, "Agent revoked")
            job = session.scalar(
                select(Job).where(Job.id == str(result.job_id), Job.agent_id == agent_id)
            )
            if job is None:
                raise HTTPException(404, "Job not found")
            payload = result.model_copy(update={"received_at": None}).model_dump(mode="json")
            if job.result is not None:
                # Receipt time is server metadata, never part of Agent replay identity.
                if {**job.result, "received_at": None} == payload:
                    return {"accepted": True, "duplicate": True}
                raise HTTPException(409, "Conflicting result")
            expected_hash = configuration_hash(
                ProbeRequest(
                    job_id=UUID(job.id),
                    kind=job.kind,
                    target=job.target,
                    policy_version=job.policy_version,
                )
            )
            if (
                result.configuration_hash != expected_hash
                or str(result.vantage_id) != agent_id
                or result.target != job.target
                or result.kind != job.kind
                or result.attempt != job.attempts
                or result.policy_version != job.policy_version
            ):
                raise HTTPException(422, "Result does not match assigned job")
            received_at = datetime.now(UTC)
            payload = result.model_copy(update={"received_at": received_at}).model_dump(mode="json")
            changed = session.execute(
                update(Job)
                .execution_options(synchronize_session="fetch")
                .where(
                    Job.id == job.id,
                    Job.lease_token == body.lease_token,
                    Job.state == "running",
                    Job.lease_until > datetime.now(UTC),
                )
                .values(
                    result=payload,
                    state="succeeded" if result.status == "success" else "failed",
                    lease_until=None,
                    lease_token=None,
                )
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Expired or stale lease")
            return {"accepted": True, "duplicate": False}
