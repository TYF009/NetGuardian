"""Database rejects orphan and cross-tenant writes even without API checks."""

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from service.database import (
    Agent,
    Incident,
    Investigation,
    Job,
    Monitor,
    MonitorRun,
    Report,
    Workspace,
    database,
)
from service.schema import upgrade


@pytest.mark.parametrize(
    "case",
    [
        "workspace",
        "job_agent",
        "monitor_agent",
        "run_job",
        "run_monitor",
        "incident",
        "report",
        "investigation",
        "delete",
    ],
)
def test_database_tenant_constraints(tmp_path, case):
    url = f"sqlite:///{tmp_path / 'constraints.db'}"
    upgrade(url)
    engine, sessions = database(url)
    with sessions.begin() as session:
        for tenant in ("one", "two"):
            session.add_all(
                [
                    Workspace(id=tenant),
                    Agent(id=tenant, workspace=tenant, name="Fixture", credential_hash=tenant),
                    Job(
                        id=tenant,
                        workspace=tenant,
                        kind="dns",
                        target="https://example.com",
                        policy_version="v1",
                    ),
                    Monitor(
                        id=tenant,
                        workspace=tenant,
                        kind="dns",
                        target="https://example.com",
                        name="Fixture",
                    ),
                    Incident(id=tenant, workspace=tenant, monitor_id=tenant),
                    Report(
                        id=tenant,
                        workspace=tenant,
                        incident_id=tenant,
                        snapshot={},
                        content_hash="a" * 64,
                    ),
                ]
            )
    invalid = {
        "workspace": Job(
            workspace="missing", kind="dns", target="https://example.com", policy_version="v1"
        ),
        "job_agent": Job(
            workspace="one",
            agent_id="two",
            kind="dns",
            target="https://example.com",
            policy_version="v1",
        ),
        "monitor_agent": Monitor(
            workspace="one",
            agent_id="two",
            kind="dns",
            target="https://example.com",
            name="Invalid",
        ),
        "run_job": MonitorRun(workspace="one", job_id="two", monitor_id="one"),
        "run_monitor": MonitorRun(workspace="one", job_id="one", monitor_id="two"),
        "incident": Incident(workspace="one", monitor_id="two"),
        "report": Report(workspace="one", incident_id="two", snapshot={}, content_hash="a" * 64),
        "investigation": Investigation(
            workspace="one",
            report_id="two",
            model="fixture",
            prompt_version="1",
            evidence_hash="a" * 64,
            output={},
        ),
    }
    with pytest.raises(IntegrityError), sessions.begin() as session:
        if case == "delete":
            session.execute(delete(Workspace).where(Workspace.id == "one"))
        else:
            session.add(invalid[case])
    with engine.connect() as connection:
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
