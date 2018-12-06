"""Serve an exported Agent Control UI bundle from the FastAPI server."""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .config import ui_settings

logger = logging.getLogger(__name__)


def get_ui_dist_dir() -> Path | None:
    """Resolve the static UI bundle directory if one is available."""
    configured_dist_dir = ui_settings.dist_dir
    if configured_dist_dir:
        candidate = Path(configured_dist_dir).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        logger.warning("Configured UI dist dir does not exist: %s", candidate)

    server_dir = Path(__file__).resolve().parents[2]
    repo_root = Path(__file__).resolve().parents[3]
    candidates = (
        server_dir / "ui-dist",
        repo_root / "ui" / "out",
    )

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    return None
