"""Explicit schema upgrade command; applications must not mutate schemas at startup."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory


def upgrade(url: str):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")


def require_schema(engine):
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    if revision != ScriptDirectory.from_config(config).get_current_head():
        raise RuntimeError("Database is not initialized. Run: uv run alembic upgrade head")
