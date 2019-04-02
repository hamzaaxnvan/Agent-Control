"""Reset the configured SDK test database to an empty schema."""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine, text

from agent_control_server.config import db_config

