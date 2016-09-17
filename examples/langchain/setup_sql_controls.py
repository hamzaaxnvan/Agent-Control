"""
Setup script for SQL agent controls.

This script creates the SQL control and associates it directly to the agent.
Run this once before running sql_agent_protection.py.

NOTE: This script is designed to run once. If resources already exist,
you may need to either:
  - Delete them from the server first
  - Manually note their IDs for use in the agent code
"""

import asyncio
import os
import pathlib

import requests

from agent_control import Agent, AgentControlClient, agents, controls

AGENT_NAME = "langchain-sql-example"
SERVER_URL = os.getenv("AGENT_CONTROL_URL", "http://localhost:8000")


def setup_database():
    """Download and setup a fresh Chinook database."""
    url = "https://storage.googleapis.com/benchmarks-artifacts/chinook/Chinook.db"
    local_path = pathlib.Path("Chinook.db")
    
    # Always download fresh database for setup
    print("📥 Downloading fresh Chinook database...")
    response = requests.get(url)
    if response.status_code == 200:
        local_path.write_bytes(response.content)
        print("✓ Database downloaded successfully")
    else:
        raise Exception(f"Failed to download database: {response.status_code}")
    
    # Verify the Artist table exists
    import sqlite3
    conn = sqlite3.connect(str(local_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Artist")
    count = cursor.fetchone()[0]
    conn.close()
    
    print(f"✓ Database verified: {count} artists in Artist table")


async def setup_sql_controls():
    """Create SQL control and associate it directly with the agent."""
    async with AgentControlClient(base_url=SERVER_URL) as client:
        # 1. Register Agent
        agent_name = AGENT_NAME

        agent = Agent(
            agent_name=agent_name,
            agent_description="SQL agent with server-side controls"
        )

        try:
            await agents.register_agent(client, agent, steps=[])
            print(f"✓ Agent registered: {AGENT_NAME}")
        except Exception as e:
            print(f"ℹ️  Agent might already exist: {e}")

        # 2. Create SQL Control
        sql_control_data = {
            "description": "Prevent dangerous SQL operations",
            "enabled": True,
            "execution": "server",
            "scope": {
                "step_types": ["tool"],
                "step_names": ["sql_db_query"],
                "stages": ["pre"]
            },
            "condition": {
                "selector": {
                    "path": "input.query"
