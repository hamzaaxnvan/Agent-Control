from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate-method-names-overlay.py"
)


@pytest.fixture(scope="module")
def overlay_gen():
    spec = importlib.util.spec_from_file_location(
        "generate_method_names_overlay",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_controls_patch_uses_update_metadata_exception(overlay_gen):
    schema = {
        "paths": {
            "/api/v1/controls/{control_id}": {
                "patch": {
                    "operationId": "patch_control_api_v1_controls__control_id__patch",
                },
                "get": {
                    "operationId": "get_control_api_v1_controls__control_id__get",
                },
            },
            "/api/v1/controls/{control_id}/data": {
                "put": {
                    "operationId": "set_control_data_api_v1_controls__control_id__data_put",
                },
            },
        },
    }
    operations = overlay_gen.iter_operations(schema)
    names = overlay_gen.resolve_names(operations)

    assert names[("/api/v1/controls/{control_id}", "patch")] == (
        "controls",
        "updateMetadata",
    )
    assert names[("/api/v1/controls/{control_id}", "get")] == ("controls", "get")
    assert names[("/api/v1/controls/{control_id}/data", "put")] == (
        "controls",
        "updateData",
    )


def test_plural_collection_get_is_list_but_singular_get_is_get(overlay_gen):
    schema = {
        "paths": {
            "/api/v1/agents": {
                "get": {
                    "operationId": "list_agents_api_v1_agents_get",
                },
            },
            "/api/v1/agents/{agent_name}": {
                "get": {
                    "operationId": "get_agent_api_v1_agents__agent_name__get",
                },
            },
            "/health": {
                "get": {
                    "operationId": "health_check_health_get",
                    "tags": ["system"],
                },
            },
        },
    }
    operations = overlay_gen.iter_operations(schema)
    names = overlay_gen.resolve_names(operations)

    assert names[("/api/v1/agents", "get")] == ("agents", "list")
    assert names[("/api/v1/agents/{agent_name}", "get")] == ("agents", "get")
    assert names[("/health", "get")] == ("system", "healthCheck")


def test_collision_resolution_is_deterministic(overlay_gen):
    operations = [
        overlay_gen.Operation(
            path="/api/v1/things/{thing_id}/policy/{policy_id}",
            method="post",
            group="things",
            group_tokens=["things"],
            tokens=["set", "thing", "policy"],
        ),
        overlay_gen.Operation(
            path="/api/v1/things/{thing_id}/policy/{policy_id}/duplicate",
            method="post",
            group="things",
            group_tokens=["things"],
            tokens=["update", "thing", "policy"],
