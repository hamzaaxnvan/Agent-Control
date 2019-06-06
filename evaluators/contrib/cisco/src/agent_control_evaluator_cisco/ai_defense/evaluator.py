from __future__ import annotations

import json
import os
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from agent_control_evaluators import (
    Evaluator,
    EvaluatorMetadata,
    register_evaluator,
)
from agent_control_models import EvaluatorResult

from .client import AI_DEFENSE_HTTPX_AVAILABLE, REGION_BASE_URLS, AIDefenseClient, build_endpoint
from .config import CiscoAIDefenseConfig


def _resolve_package_version() -> str:
    """Return the installed package version, or a dev fallback during local imports."""
    try:
        return version("agent-control-evaluator-cisco")
    except PackageNotFoundError:
        return "0.0.0.dev"


_PACKAGE_VERSION = _resolve_package_version()


def _load_api_key(env_name: str) -> str:
    key = os.getenv(env_name)
    if not key:
        raise RuntimeError(
            f"Missing Cisco AI Defense API key in env '{env_name}'. Set it on the server."
        )
    return key


def _build_messages(
    data: Any,
    strategy: str,
    payload_field: str | None,
) -> list[dict[str, str]]:
    """Build Chat Inspection messages from selected data.

