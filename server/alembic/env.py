import os
import sys

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import agent_control_server.models  # noqa: E402,F401
from agent_control_server.config import db_config  # noqa: E402
from agent_control_server.db import Base  # noqa: E402

config = context.config

target_metadata = Base.metadata


def _get_migration_url() -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url
    return db_config.get_url()
