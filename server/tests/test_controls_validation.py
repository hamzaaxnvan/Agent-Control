"""Tests for control validation and schema enforcement."""

import json
import uuid
from copy import deepcopy

from fastapi.testclient import TestClient
from sqlalchemy import text

from .conftest import engine
from .utils import VALID_CONTROL_PAYLOAD


def create_control(client: TestClient) -> int:
    name = f"control-{uuid.uuid4()}"
    resp = client.put("/api/v1/controls", json={"name": name, "data": VALID_CONTROL_PAYLOAD})
    assert resp.status_code == 200
    return resp.json()["control_id"]

def test_validation_invalid_logic_enum(client: TestClient):
    """Test that invalid enum values in config are rejected."""
    # Given: a control and a payload with invalid 'logic' value
    control_id = create_control(client)
    payload = deepcopy(VALID_CONTROL_PAYLOAD)
    payload["condition"]["evaluator"] = {
        "name": "list",
        "config": {
            "values": ["a", "b"],
            "logic": "invalid_logic", # Should be 'any' or 'all'
            "match_on": "match"
        }
    }

    # When: setting control data
    resp = client.put(f"/api/v1/controls/{control_id}/data", json={"data": payload})

    # Then: 422 Unprocessable Entity
    assert resp.status_code == 422

    # Then: error message mentions the field (RFC 7807 format)
    response_data = resp.json()
    errors = response_data.get("errors", [])
    assert any("logic" in str(e.get("field", "")) for e in errors)
    assert any("any" in e.get("message", "") or "all" in e.get("message", "") for e in errors)


def test_validation_discriminator_mismatch(client: TestClient):
    """Test that config must match the evaluator type."""
    # Given: a control and type='list' but config has 'pattern' (RegexEvaluatorConfig)
    control_id = create_control(client)
    payload = deepcopy(VALID_CONTROL_PAYLOAD)
    payload["condition"]["evaluator"] = {
        "name": "list",
        "config": {
            "pattern": "some_regex", # Invalid for ListEvaluatorConfig
            # Missing 'values'
        }
    }

    # When: setting control data
    resp = client.put(f"/api/v1/controls/{control_id}/data", json={"data": payload})

    # Then: 422 Unprocessable Entity
    assert resp.status_code == 422

    # Then: error mentions missing required field for ListEvaluatorConfig (RFC 7807 format)
    response_data = resp.json()
    errors = response_data.get("errors", [])
    # Expecting 'values' field missing
    assert any("values" in str(e.get("field", "")) for e in errors)
    assert any("Field required" in e.get("message", "") for e in errors)


def test_validation_regex_flags_list(client: TestClient):
    """Test validation of regex flags list."""
    # Given: a control and regex config with invalid flags type (string instead of list)
    control_id = create_control(client)
    payload = deepcopy(VALID_CONTROL_PAYLOAD)
    payload["condition"]["evaluator"] = {
        "name": "regex",
        "config": {
            "pattern": "abc",
            "flags": "IGNORECASE" # Should be ["IGNORECASE"]
        }
    }

    # When: setting control data
    resp = client.put(f"/api/v1/controls/{control_id}/data", json={"data": payload})

    # Then: 422 (RFC 7807 format)
    assert resp.status_code == 422
    response_data = resp.json()
    errors = response_data.get("errors", [])
    assert any("flags" in str(e.get("field", "")) for e in errors)


def test_validation_list_values_reject_blank_strings(client: TestClient):
    """Test that list evaluator config rejects empty and whitespace-only entries."""
    # Given: a control and a list evaluator payload with a whitespace-only value
    control_id = create_control(client)
    payload = deepcopy(VALID_CONTROL_PAYLOAD)
    payload["condition"]["evaluator"] = {
        "name": "list",
        "config": {
            "values": [" "],
            "logic": "any",
            "match_on": "match",
            "match_mode": "contains",
        },
    }

    # When: setting control data
    resp = client.put(f"/api/v1/controls/{control_id}/data", json={"data": payload})

    # Then: the invalid config is rejected
    assert resp.status_code == 422
    response_data = resp.json()
    errors = response_data.get("errors", [])
    assert any("values" in str(e.get("field", "")) for e in errors)
