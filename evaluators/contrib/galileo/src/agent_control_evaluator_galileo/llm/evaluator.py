"""Direct Galileo LLM-as-judge evaluator implementation."""

from __future__ import annotations

import json
import logging
import os
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx
from agent_control_evaluators import Evaluator, EvaluatorMetadata, register_evaluator
from agent_control_models import EvaluatorResult, JSONObject, JSONValue, Step

from .client import GalileoExecutionContext, GalileoLLMClient, ScorerInvokeResponse
from .config import LlmEvaluatorConfig, coerce_number, llm_evaluator_enabled

logger = logging.getLogger(__name__)


def _resolve_package_version() -> str:
    """Return the installed package version, or a dev fallback during local imports."""
    try:
        return version("agent-control-evaluator-galileo")
    except PackageNotFoundError:
        return "0.0.0.dev"


_PACKAGE_VERSION = _resolve_package_version()
LLM_AVAILABLE = True
_HTTP_ERROR_BODY_LIMIT = 500


def _coerce_payload_text(value: Any) -> str | None:
    """Coerce selected data into scorer text without losing structured values."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _has_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def _extract_dict_text(data: dict[str, Any], key: str) -> str | None:
    if key not in data:
        return None
    return _coerce_payload_text(data.get(key))


def _contains(score: JSONValue, threshold: JSONValue) -> bool:
    if threshold is None:
        return False
    if isinstance(score, str):
        return str(threshold) in score
    if isinstance(score, list):
        return threshold in score
    if isinstance(score, dict):
        return threshold in score.values()
    return False


def _confidence_from_score(score: JSONValue) -> float:
    if isinstance(score, bool):
        return 1.0 if score else 0.0
    number = coerce_number(score)
    if number is not None and 0.0 <= number <= 1.0:
        return number
    return 1.0


def _truncated_http_response_body(body: str) -> tuple[str, bool]:
    if len(body) <= _HTTP_ERROR_BODY_LIMIT:
        return body, False
    return body[:_HTTP_ERROR_BODY_LIMIT], True


def _http_status_error_metadata(error: httpx.HTTPStatusError) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    request = error.request
    metadata["http_method"] = request.method
    metadata["http_endpoint_path"] = request.url.path

    response = error.response
    metadata["http_status_code"] = response.status_code
    metadata["http_response_content_type"] = response.headers.get("content-type")

    body = response.text
    if body:
        metadata["http_response_body"], metadata["http_response_body_truncated"] = (
            _truncated_http_response_body(body)
        )

    return {key: value for key, value in metadata.items() if value is not None}


@register_evaluator
class LlmEvaluator(Evaluator[LlmEvaluatorConfig]):
    """Galileo LLM-as-judge evaluator using the direct scorer invocation API.

    This evaluator requires Agent Control's authenticated execution context to
    invoke the Galileo scorer.  ``target_type`` and ``target_id`` are optional
    fields in the general SDK API, but ``galileo.llm`` depends on them being
    supplied via a *targeted* SDK initialisation (e.g. a log-stream or
    agent-stream target) so that a ``run_id`` can be forwarded to Galileo.
    Without a supported ``target_type`` (``"log_stream"`` or
    ``"agent_stream"``) the ``run_id`` in the execution context will be
    ``None``, which may limit Galileo's ability to associate the scorer result
    with a specific run.

    Typical targeted SDK usage::

        agent_control.init(
            agent_name="my-agent",
            target_type="log_stream",
            target_id="<log-stream-id>",
        )
    """

    metadata = EvaluatorMetadata(
        name="galileo.llm",
        version=_PACKAGE_VERSION,
        description="Galileo LLM-as-judge direct scorer evaluation",
        requires_api_key=True,
        timeout_ms=10000,
    )
    config_model = LlmEvaluatorConfig

    @classmethod
    def is_available(cls) -> bool:
        """Return True only when the LLM invoke runtime feature flag is enabled.

        The LLM evaluator requires Orbit-side support for ``execution_context`` to
        fetch LLM credentials. It is unavailable until
        ``GALILEO_FEATURE_FLAG_LLM_EVALUATOR=enabled`` is set.
        """
        return LLM_AVAILABLE and llm_evaluator_enabled()

    def __init__(self, config: LlmEvaluatorConfig) -> None:
        """Initialize the direct LLM-as-judge evaluator.

        Args:
            config: Validated LlmEvaluatorConfig instance.

        Raises:
            ValueError: If neither GALILEO_API_SECRET_KEY nor GALILEO_API_SECRET is set.
        """
        has_secret = os.getenv("GALILEO_API_SECRET_KEY") or os.getenv("GALILEO_API_SECRET")
        if not has_secret:
            raise ValueError(
                "GALILEO_API_SECRET_KEY or GALILEO_API_SECRET is required for LLM "
                "scorer invocation. Set one as an environment variable before using "
                "galileo.llm."
            )

        super().__init__(config)
        self._client = GalileoLLMClient()

    def _get_client(self) -> GalileoLLMClient:
        """Get the Galileo LLM client."""
        return self._client

    def _prepare_payload(self, data: Any) -> tuple[str | None, str | None]:
        """Prepare scorer input/output fields from selected data."""
        if isinstance(data, dict):
            input_text = _extract_dict_text(data, "input")
