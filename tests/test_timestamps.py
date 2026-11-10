"""SQLite timestamp round trips preserve instants and expose UTC offsets."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import StatementError

from service.database import Job, Workspace, database
from service.schema import upgrade


def test_offset_roundtrip_and_naive_write_rejection(tmp_path):
    url = f"sqlite:///{tmp_path / 'time.db'}"
    upgrade(url)
    engine, sessions = database(url)
    instant = datetime(2026, 11, 5, 0, 30, tzinfo=timezone(timedelta(hours=8)))
    with sessions.begin() as session:
        session.add(Workspace(id="one"))
        job = Job(
            workspace="one",
            target="https://example.com",
            kind="dns",
            policy_version="fixture",
            created_at=instant,
        )
        session.add(job)
        session.flush()
        identifier = job.id
    with sessions() as session:
        recorded = session.get(Job, identifier).created_at
        assert recorded == instant
        assert recorded.tzinfo == UTC
        assert recorded.isoformat() == "2026-11-04T16:30:00+00:00"
    with pytest.raises(StatementError), sessions.begin() as session:
        session.add(
            Job(
                workspace="one",
                target="https://example.com",
                kind="dns",
                policy_version="fixture",
                created_at=instant.replace(tzinfo=None),
            )
        )
    engine.dispose()
