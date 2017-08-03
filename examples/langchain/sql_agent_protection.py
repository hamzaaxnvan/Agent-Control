"""
LangGraph SQL Agent with Agent Control integration.

This example demonstrates using the @control() decorator to protect SQL queries
with graceful error handling.

PREREQUISITE:
    Run setup_sql_controls.py FIRST to create the SQL control and direct agent association:
    
        $ uv run setup_sql_controls.py
    
    Then run this example:
    
        $ uv run sql_agent_protection.py

The @control() decorator automatically:
1. Detects this is a tool step (from @tool decorator)
2. Sends the query to the server for evaluation
3. Blocks dangerous operations (DROP, DELETE, TRUNCATE, etc.)
4. Requires LIMIT clauses on SELECT statements
5. Prevents multi-statement SQL injection

Error Handling:
- ControlViolationError: Returns error message (query blocked)
- RuntimeError: Returns error message (server unavailable)
- Agent continues running even if control check fails
"""

import asyncio
import os
import pathlib
from typing import Annotated, Literal, TypedDict

import agent_control
from agent_control import (
    AgentControlClient,
    ControlViolationError,
    agents,
    check_evaluation_with_local,
    control,
)
import requests
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# --- Configuration ---
AGENT_NAME = "langchain-sql-example"
AGENT_DESCRIPTION = "SQL agent with server-side controls"
USE_LOCAL_CONTROLS = os.getenv("AGENT_CONTROL_LOCAL_EVAL", "false").lower() == "true"
# When enabled, controls must be configured with execution="sdk".

# --- 1. Setup Database ---
def setup_database():
    url = "https://storage.googleapis.com/benchmarks-artifacts/chinook/Chinook.db"
    local_path = pathlib.Path("Chinook.db")

    # Check if database exists and has Artist table
    needs_download = True
    if local_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(local_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Artist")
            count = cursor.fetchone()[0]
            conn.close()
            print(f"✓ Database exists with {count} artists")
            needs_download = False
        except Exception as e:
            print(f"⚠️  Database corrupted or missing Artist table: {e}")
            needs_download = True
    
    if needs_download:
        print(f"📥 Downloading fresh Chinook database...")
        response = requests.get(url)
        if response.status_code == 200:
            local_path.write_bytes(response.content)
            print("✓ Download complete")
        else:
            raise Exception(f"Failed to download database: {response.status_code}")
    
    return SQLDatabase.from_uri("sqlite:///Chinook.db")

# --- 2. Define Tools with Server-Side Controls ---
def create_safe_tools(db, llm, *, use_local_controls: bool, local_controls: list[dict] | None):
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    original_tools = toolkit.get_tools()
    
    # Find the query tool
    query_tool = next(t for t in original_tools if t.name == "sql_db_query")
    
    # Create controlled SQL tool with graceful error handling
    
    # Inner function with @control decorator for validation
    async def _execute_query_with_validation(query: str):
        """Execute SQL query (this function is protected by @control)."""
        return query_tool.invoke(query)
    
    # Set tool name for @control detection
    _execute_query_with_validation.name = "sql_db_query"  # type: ignore
    _execute_query_with_validation.tool_name = "sql_db_query"  # type: ignore
    
    # Apply @control decorator
    validated_query_func = control()(_execute_query_with_validation)
    
    # Outer wrapper: catches exceptions and returns error messages gracefully
    @tool("sql_db_query", description="Execute a SQL query after safety validation")
    async def safe_query_tool(query: str):
        """Execute a SQL query with safety checks."""
        print(f"\n[SQL Safety Check] Validating query: {query[:60]}...")
        try:
            if use_local_controls:
                agent = agent_control.current_agent()
                if agent is None:
                    raise RuntimeError("Agent is not initialized.")
                if not local_controls:
                    raise RuntimeError("No local controls available for SDK evaluation.")

                step = {
                    "type": "tool",
                    "name": "sql_db_query",
                    "input": {"query": query},
                }
                async with AgentControlClient() as client:
                    result = await check_evaluation_with_local(
                        client=client,
                        agent_name=agent.agent_name,
                        step=step,
                        stage="pre",
                        controls=local_controls,
                    )
                if getattr(result, "errors", None):
                    raise RuntimeError("Local control evaluation failed.")
                if not result.is_safe:
