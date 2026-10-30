import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make `app` importable when alembic is invoked from apps/api/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import every model (registers them on Base.metadata) and the app's own
# settings, so migrations are generated from the same models and the same
# DATABASE_URL the running app uses — never a second, hand-maintained URL
# in alembic.ini.
import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
# Prefer an explicit DATABASE_URL env var (used by tests to point Alembic
# at a throwaway DB) over the cached app Settings, so test runs never risk
# touching the developer's real database even if Settings was already
# instantiated earlier in the process.
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL") or get_settings().DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """Skip a unique constraint that exactly duplicates its table's primary key.

    Several association tables declare both PRIMARY KEY (a, b) and UNIQUE (a, b). PostgreSQL folds the duplicate into
    the primary-key index, so reflection no longer sees it and `alembic check` reports false drift there, while SQLite
    keeps both. Uniqueness is enforced by the primary key in every case; no schema change is involved.
    """
    if type_ == "unique_constraint" and getattr(obj, "table", None) is not None:
        pk_columns = {c.name for c in obj.table.primary_key.columns}
        if pk_columns and {c.name for c in obj.columns} == pk_columns:
            return False
    return True


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite can't ALTER most things directly; batch mode rebuilds the
        # table under the hood instead. Harmless no-op on Postgres.
        render_as_batch=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
