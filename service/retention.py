"""Conservative operator retention: preview by default, bounded deletion batches."""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update

from service.audit import record_audit
from service.database import (
    DiagnosticPair,
    Incident,
    IncidentEvidence,
    Job,
    Monitor,
    MonitorRun,
    Workspace,
    database,
)
from service.schema import require_schema


def prune(sessions, workspace, days=30, apply=False, batch=500):
    if days < 1 or not 1 <= batch <= 500:
        raise ValueError("Retention requires at least one day and a batch of 1–500")
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with sessions.begin() as session:
        locked = session.execute(
            update(Workspace).where(Workspace.id == workspace).values(revision=Workspace.revision)
        )
        if locked.rowcount != 1:
            raise ValueError("Workspace not found")
        # Serialize incident transitions while collecting protected evidence links.
        for identifier in session.scalars(
            select(Monitor.id).where(Monitor.workspace == workspace).order_by(Monitor.id)
        ).all():
            session.execute(
                update(Monitor).where(Monitor.id == identifier).values(enabled=Monitor.enabled)
            )
        protected = set()
        for evidence in session.scalars(
            select(Incident.evidence).where(Incident.workspace == workspace)
        ):
            protected.update(evidence)
        ranked = (
            select(
                MonitorRun.job_id.label("job_id"),
                func.row_number()
                .over(
                    partition_by=MonitorRun.monitor_id,
                    order_by=(Job.created_at.desc(), Job.id.desc()),
                )
                .label("position"),
            )
            .join(Job, Job.id == MonitorRun.job_id)
            .where(Job.workspace == workspace)
            .subquery()
        )
        keep_recent = select(ranked.c.job_id).where(ranked.c.position <= 100)
        candidates = session.scalars(
            select(Job.id)
            .where(
                Job.workspace == workspace,
                Job.created_at < cutoff,
                Job.state.in_(["succeeded", "failed"]),
                Job.id.not_in(keep_recent),
                Job.id.not_in(select(IncidentEvidence.job_id)),
                Job.id.not_in(select(DiagnosticPair.cloud_job_id)),
                Job.id.not_in(select(DiagnosticPair.agent_job_id)),
                Job.id.not_in(select(MonitorRun.job_id).where(MonitorRun.processed == 0)),
            )
            .order_by(Job.created_at, Job.id)
        ).yield_per(500)
        selected = []
        for identifier in candidates:
            if identifier not in protected:
                selected.append(identifier)
                if len(selected) == batch:
                    break
        if apply and selected:
            session.execute(delete(MonitorRun).where(MonitorRun.job_id.in_(selected)))
            session.execute(delete(Job).where(Job.workspace == workspace, Job.id.in_(selected)))
            for identifier in selected:
                record_audit(session, workspace, "job.deleted_by_retention", identifier)
        return {
            "mode": "apply" if apply else "preview",
            "workspace": workspace,
            "older_than": cutoff.isoformat(),
            "count": len(selected),
            "job_ids": selected,
            "limit": batch,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Preview or prune expired, unreferenced job records"
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine, sessions = database(
        os.environ.get("NETGUARDIAN_DATABASE_URL", "sqlite:///netguardian.db")
    )
    require_schema(engine)
    try:
        print(json.dumps(prune(sessions, args.workspace, args.days, args.apply), indent=2))
    finally:
        engine.dispose()
