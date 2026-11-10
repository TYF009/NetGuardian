"""Evidence snapshots and conservative comparisons; no inferred root causes."""

import hashlib
import json
import secrets
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from probe_core.contracts import Measurement
from service.audit import record_audit
from service.database import Incident, IncidentEvidence, Job, Report


def snapshot_hash(snapshot):
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def verify_report(record):
    try:
        valid = secrets.compare_digest(snapshot_hash(record.snapshot), record.content_hash)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise HTTPException(409, "Report integrity check failed")


def redact_measurement(payload):
    result = Measurement.model_validate(payload).model_dump(mode="json")
    url = urlsplit(result["target"])
    result["target"] = urlunsplit((url.scheme, url.netloc, url.path, "", ""))
    if result["error"]:
        result["error"]["message"] = result["error"]["code"]
    return result


def observation_claim(item):
    text = f"Recorded {item['kind']} probe execution status: {item['status']}."
    if item.get("http_status") is not None:
        text += f" HTTP response status: {item['http_status']}."
        if item["status"] == "success":
            text += " Successful probe execution does not imply application health."
    return {"text": text, "evidence_ids": [item["job_id"]]}


def compare(left: Measurement, right: Measurement):
    reasons = []
    if left.target != right.target or left.kind != right.kind:
        reasons.append("Target or probe kind differs")
    if left.configuration_hash != right.configuration_hash:
        reasons.append("Probe configuration differs")
    if left.probe_version != right.probe_version:
        reasons.append("Probe implementation version differs")
    if left.vantage_id == right.vantage_id:
        reasons.append("Measurements have the same vantage")
    skew = abs((left.observed_at - right.observed_at).total_seconds())
    if skew > 30:
        reasons.append("Observation times differ by more than 30 seconds")
    if left.status != "success" or right.status != "success":
        reasons.append("One or both measurements did not succeed")
    if left.kind == "dns":
        reasons.append(
            "DNS timing comparison is withheld: resolver endpoint alone "
            "cannot establish cache equivalence"
        )
    if left.kind in {"tcp", "tls", "http"} and (
        left.connected_ip is None or right.connected_ip is None
    ):
        reasons.append("Connected destination is missing")
    if left.connected_ip != right.connected_ip:
        reasons.append("Connected destinations differ")
    deltas = {}
    if not reasons:
        for key, value in left.timings.model_dump().items():
            if key == "dns_lookup_ms":
                continue  # Resolver cache equivalence is unknown for every probe kind.
            other = getattr(right.timings, key)
            if value is not None and other is not None:
                deltas[key] = other - value
    return {
        "comparable": not reasons,
        "limitations": reasons,
        "skew_seconds": skew,
        "metric_limitations": [
            "DNS timing deltas are withheld because resolver cache equivalence is unknown.",
            "HTTP total duration includes DNS and connection setup; it is not ICMP RTT.",
        ],
        "right_minus_left_ms": deltas,
        "evidence_ids": [str(left.job_id), str(right.job_id)],
        "resolved_addresses": [
            list(map(str, left.resolved_ips)),
            list(map(str, right.resolved_ips)),
        ],
        "interpretation": "Observed differences do not establish a root cause.",
    }


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_job_id: UUID
    right_job_id: UUID


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: UUID


def mount_evidence_routes(app, sessions, workspace):
    @app.post("/api/comparisons")
    def comparison(body: CompareRequest, tenant: str = Depends(workspace)):
        with sessions() as session:
            pair = []
            for identifier in (body.left_job_id, body.right_job_id):
                job = session.scalar(
                    select(Job).where(Job.id == str(identifier), Job.workspace == tenant)
                )
                if job is None:
                    raise HTTPException(404, "Job not found")
                if job.result is None:
                    raise HTTPException(409, "Measurement not available")
                pair.append(Measurement.model_validate(job.result))
            return compare(*pair)

    @app.get("/api/incidents/{incident_id}/evidence")
    def incident_history(
        incident_id: UUID,
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        tenant: str = Depends(workspace),
    ):
        with sessions() as session:
            incident = session.scalar(
                select(Incident).where(
                    Incident.id == str(incident_id), Incident.workspace == tenant
                )
            )
            if incident is None:
                raise HTTPException(404, "Incident not found")
            rows = session.scalars(
                select(IncidentEvidence)
                .where(
                    IncidentEvidence.incident_id == incident.id,
                    IncidentEvidence.workspace == tenant,
                    IncidentEvidence.position > after,
                )
                .order_by(IncidentEvidence.position)
                .limit(limit + 1)
            ).all()
            page = rows[:limit]
            return {
                "items": [{"position": row.position, "job_id": row.job_id} for row in page],
                "next_after": page[-1].position if len(rows) > limit else None,
                "limitations": [
                    "History predating the evidence-link migration may already be truncated."
                ],
            }

    @app.post("/api/reports", status_code=201)
    def create_report(body: ReportRequest, tenant: str = Depends(workspace)):
        with sessions.begin() as session:
            incident = session.scalar(
                select(Incident).where(
                    Incident.id == str(body.incident_id), Incident.workspace == tenant
                )
            )
            if incident is None:
                raise HTTPException(404, "Incident not found")
            total_links = session.scalar(
                select(func.count())
                .select_from(IncidentEvidence)
                .where(
                    IncidentEvidence.incident_id == incident.id,
                    IncidentEvidence.workspace == tenant,
                )
            )
            evidence, missing = [], []
            for identifier in incident.evidence:
                job = session.scalar(
                    select(Job).where(Job.id == identifier, Job.workspace == tenant)
                )
                if job is None or job.result is None:
                    missing.append(identifier)
                else:
                    evidence.append(redact_measurement(job.result))
            claims = [observation_claim(item) for item in evidence]
            snapshot = {
                "schema_version": "1",
                "incident_id": incident.id,
                "state": incident.state,
                "opened_at": incident.opened_at.replace(tzinfo=UTC).isoformat(),
                "recovered_at": (
                    incident.recovered_at.replace(tzinfo=UTC).isoformat()
                    if incident.recovered_at
                    else None
                ),
                "generated_at": datetime.now(UTC).isoformat(),
                "evidence": evidence,
                "history": {
                    "stored_link_count": total_links,
                    "included_link_count": len(incident.evidence),
                    "scope": "latest_1000_links",
                    "earlier_history_may_be_unavailable": True,
                },
                "missing_evidence_ids": missing,
                "claims": claims,
                "limitations": [
                    "No root cause has been established.",
                    "This snapshot includes at most the latest 1000 linked observations. "
                    "Use the paginated incident evidence API for retained earlier links.",
                    "History predating the evidence-link migration may already be truncated.",
                    "Agent observations are self-reported.",
                    "URL query strings and free-form errors are redacted.",
                ],
            }
            content_hash = snapshot_hash(snapshot)
            report = Report(
                workspace=tenant,
                incident_id=incident.id,
                snapshot=snapshot,
                content_hash=content_hash,
            )
            session.add(report)
            session.flush()
            record_audit(session, tenant, "report.created", report.id)
            return {"id": report.id, "content_hash": content_hash}

    @app.get("/api/reports")
    def reports(tenant: str = Depends(workspace)):
        with sessions() as session:
            return [
                {
                    "id": record.id,
                    "incident_id": record.incident_id,
                    "created_at": record.created_at.replace(tzinfo=UTC),
                    "content_hash": record.content_hash,
                }
                for record in session.scalars(
                    select(Report)
                    .where(Report.workspace == tenant)
                    .order_by(Report.created_at.desc(), Report.id.desc())
                    .limit(100)
                )
            ]

    @app.get("/api/reports/{report_id}")
    def report(report_id: str, tenant: str = Depends(workspace)):
        with sessions() as session:
            record = session.scalar(
                select(Report).where(Report.id == report_id, Report.workspace == tenant)
            )
            if record is None:
                raise HTTPException(404, "Report not found")
            verify_report(record)
            return {
                "integrity": "verified",
                "id": record.id,
                "content_hash": record.content_hash,
                "snapshot": record.snapshot,
            }
