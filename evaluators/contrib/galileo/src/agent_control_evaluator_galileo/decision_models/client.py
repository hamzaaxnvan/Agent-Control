"""HTTP client for Galileo Decision Models scorer invocation."""

from __future__ import annotations

import logging
import os
from asyncio import Lock
from base64 import urlsafe_b64encode
from hashlib import sha256
from hmac import new as hmac_new
from json import dumps
from time import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from agent_control_models import JSONObject, JSONValue, Step
from pydantic import BaseModel, Field

from ..records import record_from_step
from .config import DecisionModelsPayloadField, scorer_invoke_runtime_enabled

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECS = 10.0
DEFAULT_INTERNAL_TOKEN_TTL_SECS = 3600
DEFAULT_INVOKE_PATH = "/api/v1/scorers/invoke"
LUNA_INVOKE_URL_ENV = "GALILEO_LUNA_INVOKE_URL"
AUTH_UPSTREAM_CA_FILE_ENV = "AGENT_CONTROL_AUTH_UPSTREAM_CA_FILE"
DEFAULT_KEEPALIVE_EXPIRY_SECS = 1.0
DEFAULT_MAX_CONNECTIONS = 100
DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 20
DEFAULT_CLIENT_POOL_SIZE = 1
LUNA_KEEPALIVE_EXPIRY_ENV = "GALILEO_LUNA_KEEPALIVE_EXPIRY_SECONDS"
LUNA_MAX_CONNECTIONS_ENV = "GALILEO_LUNA_MAX_CONNECTIONS"
LUNA_MAX_KEEPALIVE_CONNECTIONS_ENV = "GALILEO_LUNA_MAX_KEEPALIVE_CONNECTIONS"
LUNA_CLIENT_POOL_SIZE_ENV = "GALILEO_LUNA_CLIENT_POOL_SIZE"


def _load_float_env(env_name: str, default: float) -> float:
    raw = os.getenv(env_name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name}={raw!r} is not a number.") from exc


def _load_int_env(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name}={raw!r} is not an integer.") from exc


def _validate_connection_config(
    *,
    keepalive_expiry_seconds: float,
    max_connections: int,
    max_keepalive_connections: int,
    client_pool_size: int,
) -> None:
    if keepalive_expiry_seconds < 0:
        raise ValueError(
            f"{LUNA_KEEPALIVE_EXPIRY_ENV}={keepalive_expiry_seconds} "
            "must be greater than or equal to 0."
        )
    if max_connections <= 0:
        raise ValueError(f"{LUNA_MAX_CONNECTIONS_ENV}={max_connections} must be greater than 0.")
    if max_keepalive_connections < 0:
        raise ValueError(
            f"{LUNA_MAX_KEEPALIVE_CONNECTIONS_ENV}={max_keepalive_connections} "
            "must be greater than or equal to 0."
        )
    if max_keepalive_connections > max_connections:
        raise ValueError(
            f"{LUNA_MAX_KEEPALIVE_CONNECTIONS_ENV}={max_keepalive_connections} "
            f"must be less than or equal to {LUNA_MAX_CONNECTIONS_ENV}={max_connections}."
        )
    if client_pool_size <= 0:
        raise ValueError(f"{LUNA_CLIENT_POOL_SIZE_ENV}={client_pool_size} must be greater than 0.")


class DecisionModelsExecutionContext(BaseModel):
    """Authenticated organization and optional identity fields for scorer invocation."""

    organization_id: str = Field(min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    project_id: str | None = Field(default=None, min_length=1)
    run_id: str | None = Field(default=None, min_length=1)


def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


