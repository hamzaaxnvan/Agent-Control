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
