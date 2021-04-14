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
