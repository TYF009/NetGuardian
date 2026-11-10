"""Concurrent initializers preserve existing workspace state."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import select

from service.database import Workspace, database, initialize_workspaces
from service.schema import upgrade


def test_concurrent_workspace_initialization(tmp_path):
    url = f"sqlite:///{tmp_path / 'startup.db'}"
    upgrade(url)
    engine, sessions = database(url)
    with sessions.begin() as session:
        session.add(Workspace(id="existing", revision=42))
    barrier = Barrier(4)

    def start(index):
        own_engine, _ = database(url)
        try:
            barrier.wait(timeout=5)
            tenants = ["existing", "new", "other", "new"]
            initialize_workspaces(own_engine, tenants if index % 2 else reversed(tenants))
        finally:
            own_engine.dispose()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(start, range(4)))
    with sessions() as session:
        rows = session.scalars(select(Workspace)).all()
        assert {row.id for row in rows} == {"existing", "new", "other"}
        assert session.get(Workspace, "existing").revision == 42
        assert session.get(Workspace, "new").revision == 0
    engine.dispose()
