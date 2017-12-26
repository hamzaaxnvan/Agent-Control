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
