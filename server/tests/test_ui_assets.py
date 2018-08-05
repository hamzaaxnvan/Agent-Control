from __future__ import annotations

from pathlib import Path

from agent_control_server.ui_assets import (
    configure_ui_routes,
    get_ui_dist_dir,
    resolve_ui_asset_path,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_ui_bundle(root: Path) -> Path:
    (root / "agents").mkdir(parents=True)
    (root / "_next" / "static").mkdir(parents=True)

    (root / "index.html").write_text("<html><body>home</body></html>")
    (root / "agents" / "index.html").write_text("<html><body>agents</body></html>")
    (root / "_next" / "static" / "app.js").write_text("console.log('agent-control');")
    (root / "site.webmanifest").write_text('{"name":"agent-control"}')

    return root


def test_get_ui_dist_dir_prefers_configured_directory(
    monkeypatch, tmp_path: Path
) -> None:
    ui_bundle = _create_ui_bundle(tmp_path / "configured-ui")

    from agent_control_server.config import ui_settings

    monkeypatch.setattr(ui_settings, "dist_dir", str(ui_bundle))

    assert get_ui_dist_dir() == ui_bundle.resolve()


def test_resolve_ui_asset_path_serves_route_specific_index(tmp_path: Path) -> None:
    ui_bundle = _create_ui_bundle(tmp_path / "ui")

    assert resolve_ui_asset_path(ui_bundle, "/") == ui_bundle / "index.html"
    assert (
