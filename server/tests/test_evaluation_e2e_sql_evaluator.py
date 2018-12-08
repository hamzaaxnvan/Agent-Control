"""End-to-end tests for SQL evaluator."""

from agent_control_models import EvaluationRequest, Step
from fastapi.testclient import TestClient

from .utils import create_and_assign_policy

# =============================================================================
# Step Tests - Pre-check validation
# SQL queries in tool input, validated before execution
# =============================================================================


def test_sql_read_only_agent(client: TestClient):
    """Test read-only agent with LIMIT enforcement."""
    # Given: A control allowing only SELECT with LIMIT enforcement
    control_data = {
        "description": "Read-only agent with LIMIT",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "input.query"},
        "evaluator": {
            "name": "sql",
            "config": {
                "allowed_operations": ["SELECT"],
                "require_limit": True,
                "max_limit": 1000
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(
        client, control_data, agent_name="ReadOnlyAgent"
    )

    # When: evaluating a SELECT with LIMIT 100
    req_safe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM users LIMIT 100"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_safe.model_dump(mode="json"))
    # Then: evaluation is safe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is True

    # When: evaluating an INSERT query (not allowed)
    req_insert = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "INSERT INTO users (name) VALUES ('test')"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_insert.model_dump(mode="json"))
    # Then: evaluation is unsafe and matches the control
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False
    assert resp.json()["matches"][0]["control_name"] == control_name

    # When: evaluating a SELECT without LIMIT
    req_no_limit = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM users"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_no_limit.model_dump(mode="json"))
    # Then: evaluation is unsafe (LIMIT required)
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False

    # When: evaluating a SELECT with LIMIT 5000 (exceeds max_limit)
    req_high_limit = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM users LIMIT 5000"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_high_limit.model_dump(mode="json"))
    # Then: evaluation is unsafe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False


def test_sql_multi_tenant_security(client: TestClient):
    """Test multi-tenant isolation with required tenant_id filtering."""
    # Given: A control requiring tenant_id in WHERE clause
    control_data = {
        "description": "Multi-tenant security",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "input.query"},
        "evaluator": {
            "name": "sql",
            "config": {
                "required_columns": ["tenant_id"],
                "column_context": "where"
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(
        client, control_data, agent_name="MultiTenantAgent"
    )

    # When: evaluating a query with tenant_id in WHERE
    req_safe = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM orders WHERE tenant_id = 123"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_safe.model_dump(mode="json"))
    # Then: evaluation is safe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is True

    # When: evaluating a query without tenant_id in WHERE
    req_no_tenant = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM orders WHERE status = 'active'"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_no_tenant.model_dump(mode="json"))
    # Then: evaluation is unsafe and matches the control
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False
    assert resp.json()["matches"][0]["control_name"] == control_name

    # When: evaluating a query with tenant_id only in SELECT
    req_select_only = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT tenant_id, name FROM orders"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_select_only.model_dump(mode="json"))
    # Then: evaluation is unsafe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False


def test_sql_block_destructive_operations(client: TestClient):
    """Test production safety - block dangerous operations."""
    # Given: A control blocking destructive operations
    control_data = {
        "description": "Block destructive operations",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "input.query"},
        "evaluator": {
            "name": "sql",
            "config": {
                "blocked_operations": ["DROP", "TRUNCATE", "DELETE"]
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(
        client, control_data, agent_name="SafeAgent"
    )

    # When: evaluating a safe SELECT query
    req_select = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM users"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_select.model_dump(mode="json"))
    # Then: evaluation is safe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is True

    # When: evaluating a non-destructive INSERT query
    req_insert = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "INSERT INTO logs (message) VALUES ('test')"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_insert.model_dump(mode="json"))
    # Then: evaluation is safe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is True

    # When: evaluating a DROP TABLE query
    req_drop = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "DROP TABLE users"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_drop.model_dump(mode="json"))
    # Then: evaluation is unsafe and matches the control
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False
    assert resp.json()["matches"][0]["control_name"] == control_name

    # When: evaluating a DELETE query
    req_delete = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "DELETE FROM users WHERE id = 1"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_delete.model_dump(mode="json"))
    # Then: evaluation is unsafe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False

    # When: evaluating a TRUNCATE TABLE query
    req_truncate = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "TRUNCATE TABLE logs"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_truncate.model_dump(mode="json"))
    # Then: evaluation is unsafe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False


def test_sql_table_restrictions(client: TestClient):
    """Test restricting access to specific tables (analytics use case)."""
    # Given: A control allowing only specific tables
    control_data = {
        "description": "Restrict to analytics tables",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["tool"], "stages": ["pre"]},
        "selector": {"path": "input.query"},
        "evaluator": {
            "name": "sql",
            "config": {
                "allowed_tables": ["users", "orders"]
            }
        },
        "action": {"decision": "deny"}
    }
    agent_name, control_name = create_and_assign_policy(
        client, control_data, agent_name="AnalyticsAgent"
    )

    # When: evaluating a query against an allowed table (users)
    req_users = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM users"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_users.model_dump(mode="json"))
    # Then: evaluation is safe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is True

    # When: evaluating a query against an allowed table (orders)
    req_orders = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM orders"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_orders.model_dump(mode="json"))
    # Then: evaluation is safe
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is True

    # When: evaluating a query against a disallowed table (admin_data)
    req_admin = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM admin_data"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_admin.model_dump(mode="json"))
    # Then: evaluation is unsafe and matches the control
    assert resp.status_code == 200
    assert resp.json()["is_safe"] is False
    assert resp.json()["matches"][0]["control_name"] == control_name

    # When: evaluating a query against a disallowed table (sensitive_data)
    req_sensitive = EvaluationRequest(
        agent_name=agent_name,
        step=Step(type="tool", 
            name="execute_sql",
            input={"query": "SELECT * FROM sensitive_data"},
            output=None
        ),
        stage="pre"
    )
    resp = client.post("/api/v1/evaluation", json=req_sensitive.model_dump(mode="json"))
