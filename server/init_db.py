#!/usr/bin/env python
"""Initialize the database with tables."""

import asyncio

from sqlalchemy import create_engine

from src.agent_control_server.config import db_config
