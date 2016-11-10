"""Direct HTTP client for Galileo LLM-as-judge scorer invocation."""

from __future__ import annotations

import logging
import os
import ssl
from asyncio import Lock
from base64 import urlsafe_b64encode
from hashlib import sha256
from hmac import new as hmac_new
from json import dumps
from time import time
from typing import Any, Literal, get_args
from urllib.parse import urlsplit

import httpx
from agent_control_models import JSONObject, JSONValue, Step
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from ..records import UnsupportedStepTypeError, record_from_step
from .config import ScorerInvokeConfig

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECS = 10.0
SERVER_TIMEOUT_RATIO = 0.8
DEFAULT_INTERNAL_TOKEN_TTL_SECS = 3600
DEFAULT_LLM_SCORER_INVOKE_PATH = "/api/v1/scorers/invoke"
LLM_INVOKE_URL_ENV = "GALILEO_LUNA_INVOKE_URL"
LLM_INVOKE_CA_FILE_ENV = "GALILEO_LUNA_INVOKE_CA_FILE"
AUTH_UPSTREAM_CA_FILE_ENV = "AGENT_CONTROL_AUTH_UPSTREAM_CA_FILE"

# Headers that must never be forwarded to the scorer invoke endpoint (checked case-insensitively).
_BLOCKED_REQUEST_HEADERS = frozenset({"galileo-api-key"})

# Keep pooled-connection reuse shorter than typical server keepalive/worker
# recycle windows so requests do not pick up sockets the server already closed.
DEFAULT_KEEPALIVE_EXPIRY_SECS = 1.0
DEFAULT_MAX_CONNECTIONS = 100
DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 20
DEFAULT_CLIENT_POOL_SIZE = 1
LLM_KEEPALIVE_EXPIRY_ENV = "GALILEO_LUNA_KEEPALIVE_EXPIRY_SECONDS"
LLM_MAX_CONNECTIONS_ENV = "GALILEO_LUNA_MAX_CONNECTIONS"
LLM_MAX_KEEPALIVE_CONNECTIONS_ENV = "GALILEO_LUNA_MAX_KEEPALIVE_CONNECTIONS"
LLM_CLIENT_POOL_SIZE_ENV = "GALILEO_LUNA_CLIENT_POOL_SIZE"

# These values mirror Orbit's StepType discriminator. Agent Control's generic
# Step remains extensible; only the Galileo transport boundary is constrained.
ScorerInvokeRecordType = Literal[
    "llm",
    "retriever",
    "tool",
    "workflow",
    "agent",
    "control",
    "trace",
    "session",
]
SUPPORTED_SCORER_INVOKE_RECORD_TYPES = frozenset(get_args(ScorerInvokeRecordType))
_MISSING_SELECTED_DATA = object()


def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _internal_auth_token(
    api_secret: str,
    ttl_seconds: int = DEFAULT_INTERNAL_TOKEN_TTL_SECS,
) -> str:
    """Create the internal JWT expected by LLM scorer invoke routes."""
    now = int(time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "internal": True,
        "scope": "scorers.invoke",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    signing_input = ".".join(
        [
            _b64url(dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url(dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac_new(api_secret.encode("utf-8"), signing_input.encode("ascii"), sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _normalize_llm_invoke_url(raw_url: str) -> str:
    """Use full invoke URLs as-is and append the default path to bare service roots."""
    url = raw_url.strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return url
    return f"{url}{DEFAULT_LLM_SCORER_INVOKE_PATH}"


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
            f"{LLM_KEEPALIVE_EXPIRY_ENV}={keepalive_expiry_seconds} "
            "must be greater than or equal to 0."
        )
    if max_connections <= 0:
        raise ValueError(f"{LLM_MAX_CONNECTIONS_ENV}={max_connections} must be greater than 0.")
    if max_keepalive_connections < 0:
        raise ValueError(
            f"{LLM_MAX_KEEPALIVE_CONNECTIONS_ENV}={max_keepalive_connections} "
            "must be greater than or equal to 0."
        )
    if max_keepalive_connections > max_connections:
        raise ValueError(
            f"{LLM_MAX_KEEPALIVE_CONNECTIONS_ENV}={max_keepalive_connections} "
            f"must be less than or equal to {LLM_MAX_CONNECTIONS_ENV}={max_connections}."
        )
    if client_pool_size <= 0:
        raise ValueError(f"{LLM_CLIENT_POOL_SIZE_ENV}={client_pool_size} must be greater than 0.")


def _as_float_or_none(value: JSONValue) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _has_value(value: JSONValue) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _effective_scorer_timeout(
    config: ScorerInvokeConfig,
    *,
    http_timeout_seconds: float,
) -> ScorerInvokeConfig:
    """Resolve an Orbit execution timeout that expires before the HTTP request.

    The server execution budget defaults to 80% of the caller's HTTP deadline,
    leaving time for Orbit to serialize and return the result. Explicit caller
    overrides are preserved only when they maintain the same ordering.

    Args:
        config: Caller-provided scorer-invoke configuration.
        http_timeout_seconds: Agent Control's HTTP request deadline in seconds.

    Returns:
        A scorer-invoke configuration with an effective execution timeout.

    Raises:
        ValueError: If either deadline is invalid or the explicit server timeout
            is not shorter than the HTTP deadline.
    """
    if http_timeout_seconds <= 0:
        raise ValueError("HTTP timeout must be greater than 0 seconds.")

    server_timeout = config.request_timeout_seconds
    if server_timeout is None:
        server_timeout = http_timeout_seconds * SERVER_TIMEOUT_RATIO
    elif server_timeout >= http_timeout_seconds:
        raise ValueError(
            "config.request_timeout_seconds must be shorter than the HTTP "
            f"timeout ({http_timeout_seconds:g} seconds)."
        )

    return config.model_copy(update={"request_timeout_seconds": server_timeout})


class ScorerInvokeRecord(BaseModel):
    """Caller-controlled subset of Orbit's partial runtime-record contract.

    Identity, ownership, persistence, and execution IDs are intentionally not
    represented here. Orbit hydrates those fields from trusted server context.
    """

    model_config = ConfigDict(extra="allow")

    type: ScorerInvokeRecordType
    name: str | None = None
    input: JSONValue = None
    output: JSONValue = None
    context: JSONObject | None = None
    tools: list[JSONObject] | None = None
    dataset_output: JSONValue = None


class GalileoExecutionContext(BaseModel):
    """Authenticated organization and optional identity fields for Galileo scorer invocation."""

    organization_id: str = Field(min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    project_id: str | None = Field(default=None, min_length=1)
    run_id: str | None = Field(default=None, min_length=1)


class ScorerInvokeRequest(BaseModel):
    """Request payload for LLM scorer invocation.

    Attributes:
        scorer_id: Required scorer identifier.
        scorer_version_id: Required scorer version identifier. Orbit uses this
            to route the request to the correct scorer version.
        scorer_label: Optional display/metadata label.
        record: Optional Orbit-compatible structured runtime record.
        execution_context: Required authenticated execution context; Orbit uses
            it to fetch LLM credentials.
        config: Scorer-specific configuration, always emitted.
    """

    scorer_id: str = Field(min_length=1)
    scorer_version_id: str = Field(min_length=1)
    scorer_label: str | None = Field(default=None, min_length=1)
    record: ScorerInvokeRecord | None = None
    execution_context: GalileoExecutionContext
    config: ScorerInvokeConfig = Field(default_factory=ScorerInvokeConfig)

    def to_dict(self) -> JSONObject:
        """Convert to the LLM scorer invoke request shape."""
        request = self.model_dump(mode="json", exclude_none=True)
        request["execution_context"] = self.execution_context.model_dump(mode="json")
        return request


def _scorer_invoke_record_from_step(
    step: Step | None,
    *,
    selected_input: JSONValue,
    selected_output: JSONValue,
    selected_data: Any = _MISSING_SELECTED_DATA,
    payload_field: str = "input",
) -> ScorerInvokeRecord | None:
    """Translate a generic Agent Control step into Orbit's record contract.

    Selector-selected values remain the primary scorer input. When a selector
    supplies one side, that value is written to both the legacy and structured
    representations so Orbit's conflict validation cannot observe two meanings.
    The complete step supplies the unselected side and additional record context.

    Unknown Agent Control step types are not supported. ``None`` is returned
    so the caller can raise a clear error before sending the request.

    Args:
        step: Complete Agent Control step, when contextual evaluation is used.
        selected_input: Selector-selected value written to the record's input field.
        selected_output: Selector-selected value written to the record's output field.
        selected_data: Raw selector-selected value used to construct the record,
            preserving its structure for the scorer.
        payload_field: Record input/output side for scalar selector values.

    Returns:
        An Orbit-compatible record, or ``None`` for absent/unsupported steps.
    """
    if step is None:
        return None
    try:
        if selected_data is _MISSING_SELECTED_DATA:
            galileo_core_record = record_from_step(
                step,
                selected_input=selected_input,
                selected_output=selected_output,
            )
        else:
            galileo_core_record = record_from_step(
                step,
                selected_data=selected_data,
                payload_field=payload_field,
            )
    except UnsupportedStepTypeError:
        return None
    # record_from_step() returns Galileo Core models (LlmSpan, Trace, etc.). Dumping
    # and revalidating coerces the model into the LLM request shape while preserving
    # extra canonical fields that Orbit accepts but ScorerInvokeRecord does not declare.
    canonical_record = galileo_core_record.model_dump(mode="json", exclude_none=True)
    if canonical_record.get("type") not in SUPPORTED_SCORER_INVOKE_RECORD_TYPES:
        return None
    return ScorerInvokeRecord.model_validate(canonical_record)


class ScorerInvokeResponse(BaseModel):
    """Response from LLM scorer invocation.

    Attributes:
        scorer_label: Echoed scorer label, when returned.
        score: Raw scorer value.
        status: Invocation status.
        execution_time: Execution time in seconds, when returned.
        error_message: Error detail for non-success statuses.
    """

    scorer_label: str | None = None
    score: JSONValue
    status: str = "unknown"
    execution_time: float | None = None
    error_message: str | None = None
    _raw_response: JSONObject = PrivateAttr(default_factory=dict)

    @property
    def raw_response(self) -> JSONObject:
        return self._raw_response

    @classmethod
    def from_dict(cls, data: JSONObject) -> ScorerInvokeResponse:
        """Create a response model from the LLM scorer invoke JSON object."""
        response = cls.model_validate(
            data | {"execution_time": _as_float_or_none(data.get("execution_time"))}
        )
        response._raw_response = data
        return response


class GalileoLLMClient:
    """Thin HTTP client for Galileo LLM-as-judge scorer invocation.

    Environment Variables:
        GALILEO_FEATURE_FLAG_LLM_EVALUATOR: Set to ``enabled`` to activate the evaluator.
            Required; the evaluator is unavailable until this flag is set.
        GALILEO_API_SECRET_KEY or GALILEO_API_SECRET: JWT signing secret for internal auth.
        GALILEO_LUNA_INVOKE_URL: LLM scorer invoke URL or service root (required).
        GALILEO_LUNA_INVOKE_CA_FILE: CA bundle used to verify invoke TLS.
        AGENT_CONTROL_AUTH_UPSTREAM_CA_FILE: Shared internal CA fallback.
        GALILEO_LUNA_KEEPALIVE_EXPIRY_SECONDS: HTTP pooled connection expiry.
        GALILEO_LUNA_MAX_CONNECTIONS: Maximum outbound HTTP connections.
        GALILEO_LUNA_MAX_KEEPALIVE_CONNECTIONS: Maximum idle pooled HTTP connections.
        GALILEO_LUNA_CLIENT_POOL_SIZE: Number of outbound HTTP clients to rotate across.
    """

    def __init__(
        self,
        api_secret: str | None = None,
        llm_invoke_url: str | None = None,
        llm_invoke_ca_file: str | None = None,
    ) -> None:
        """Initialize the Galileo LLM client.

        Args:
            api_secret: Internal JWT signing secret. If not provided, reads from
