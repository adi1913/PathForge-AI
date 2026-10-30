"""
Exercises the actual Alembic migration chain — not just that the models
import cleanly — against a throwaway temp SQLite file so the developer's
real pathforge.db is never touched.
"""

import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config

API_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config_for(db_url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    # env.py reads DATABASE_URL from app settings via env var override.
    os.environ["DATABASE_URL"] = db_url
    return cfg


def test_migration_upgrade_downgrade_upgrade_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "migration_test.db"
        db_url = f"sqlite:///{db_path}"
        cfg = _alembic_config_for(db_url)

        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        tables_after_upgrade = set(inspect(engine).get_table_names())
        assert "users" in tables_after_upgrade
        assert "roadmap_items" in tables_after_upgrade
        assert "mcp_tool_logs" in tables_after_upgrade
        assert {"job_applications", "application_events"} <= tables_after_upgrade
        assert {"repository_evaluations", "skill_evidence"} <= tables_after_upgrade
        engine.dispose()

        command.downgrade(cfg, "base")
        engine = create_engine(db_url)
        tables_after_downgrade = set(inspect(engine).get_table_names()) - {"alembic_version"}
        assert tables_after_downgrade == set()
        engine.dispose()

        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        tables_after_reupgrade = set(inspect(engine).get_table_names())
        assert tables_after_reupgrade == tables_after_upgrade
        engine.dispose()

        del os.environ["DATABASE_URL"]
