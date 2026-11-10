"""Migration environment; administrator configuration supplies the database URL."""

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from service.database import Base

config = context.config
url = os.environ.get("NETGUARDIAN_DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
if context.is_offline_mode():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
