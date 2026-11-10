"""Schema upgrades must be explicit, repeatable and consistent with ORM metadata."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from service.database import Base, database
from service.schema import require_schema, upgrade


def test_empty_database_upgrade_and_repeat(tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    upgrade(url)
    upgrade(url)
    engine, _ = database(url)
    require_schema(engine)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_existing_rows_backfilled_and_invalid_history_rejected(tmp_path):
    from pathlib import Path

    import pytest
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text

    from service.database import Job, Monitor, Workspace

    for invalid in (False, True):
        url = f"sqlite:///{tmp_path / f'legacy-{invalid}.db'}"
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "76bda0e91542")
        engine, _ = database(url)
        with engine.begin() as connection:
            connection.execute(Workspace.__table__.insert(), [{"id": "one"}, {"id": "two"}])
            connection.execute(
                Job.__table__.insert(),
                {
                    "id": "job",
                    "workspace": "one",
                    "kind": "dns",
                    "target": "https://example.com",
                    "policy_version": "v1",
                },
            )
            connection.execute(
                Monitor.__table__.insert(),
                {
                    "id": "monitor",
                    "workspace": "two" if invalid else "one",
                    "kind": "dns",
                    "target": "https://example.com",
                    "name": "Fixture",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO monitor_runs(job_id, monitor_id, processed) "
                    "VALUES ('job', 'monitor', 0)"
                )
            )
        if invalid:
            with pytest.raises(RuntimeError, match="Invalid monitor run tenant"):
                command.upgrade(config, "head")
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "76bda0e91542"
                )
                assert "workspace" not in {
                    c["name"] for c in inspect(connection).get_columns("monitor_runs")
                }
                assert connection.scalar(text("SELECT COUNT(*) FROM monitor_runs")) == 1
        else:
            command.upgrade(config, "head")
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT workspace FROM monitor_runs")) == "one"
                assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        engine.dispose()
