"""Minimal transaction-bound audit: identifiers only, never credentials or targets."""

from fastapi import Depends
from sqlalchemy import select

from service.database import AuditEvent


def record_audit(session, workspace, action, resource_id, actor_kind="workspace_operator"):
    session.add(
        AuditEvent(
            workspace=workspace, action=action, resource_id=resource_id, actor_kind=actor_kind
        )
    )


def mount_audit_routes(app, sessions, workspace):
    @app.get("/api/audit-events")
    def history(tenant: str = Depends(workspace)):
        with sessions() as session:
            return [
                {
                    "id": event.id,
                    "created_at": event.created_at,
                    "action": event.action,
                    "resource_id": event.resource_id,
                    "actor_kind": event.actor_kind,
                }
                for event in session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.workspace == tenant)
                    .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                    .limit(100)
                )
            ]
