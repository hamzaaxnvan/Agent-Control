"""Direct Galileo Luna evaluator implementation."""

from __future__ import annotations

import json
import logging
import os
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx
from agent_control_evaluators import Evaluator, EvaluatorMetadata, register_evaluator
from agent_control_models import EvaluatorResult, JSONObject, JSONValue, Step

from .client import GalileoExecutionContext, GalileoLunaClient, ScorerInvokeResponse
from .config import LunaEvaluatorConfig, coerce_number

logger = logging.getLogger(__name__)


def _resolve_package_version() -> str:
    """Return the installed package version, or a dev fallback during local imports."""
    try:
        return version("agent-control-evaluator-galileo")
    except PackageNotFoundError:
        return "0.0.0.dev"


_PACKAGE_VERSION = _resolve_package_version()
LUNA_AVAILABLE = True
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
class LunaEvaluator(Evaluator[LunaEvaluatorConfig]):
    """Galileo Luna evaluator using the direct scorer invocation API."""

    metadata = EvaluatorMetadata(
        name="galileo.luna",
        version=_PACKAGE_VERSION,
        description="Galileo Luna direct scorer evaluation",
        requires_api_key=True,
        timeout_ms=10000,
    )
    config_model = LunaEvaluatorConfig

    @classmethod
    def is_available(cls) -> bool:
        """Check whether required runtime dependencies are available."""
        return LUNA_AVAILABLE

    def __init__(self, config: LunaEvaluatorConfig) -> None:
        """Initialize the direct Luna evaluator.

        Args:
            config: Validated LunaEvaluatorConfig instance.

        Raises:
            ValueError: If neither GALILEO_API_SECRET_KEY nor GALILEO_API_SECRET is set.
        """
        has_secret = os.getenv("GALILEO_API_SECRET_KEY") or os.getenv("GALILEO_API_SECRET")
        if not has_secret:
            raise ValueError(
                "GALILEO_API_SECRET_KEY or GALILEO_API_SECRET is required for Luna "
                "scorer invocation. Set one as an environment variable before using "
                "galileo.luna."
            )

        super().__init__(config)
        self._client = GalileoLunaClient()

    def _get_client(self) -> GalileoLunaClient:
        """Get the Galileo Luna client."""
        return self._client

    def _prepare_payload(self, data: Any) -> tuple[str | None, str | None]:
        """Prepare scorer input/output fields from selected data."""
        if isinstance(data, dict):
            input_text = _extract_dict_text(data, "input")
            output_text = _extract_dict_text(data, "output")
            if _has_text(input_text) or _has_text(output_text):
                return input_text, output_text

        text = _coerce_payload_text(data)
        if self.config.payload_field == "output":
            return None, text
        return text, None

    def _score_matches(self, score: JSONValue) -> bool:
        """Apply the configured local threshold comparison to a raw Luna score."""
        operator = self.config.operator
        threshold = self.config.threshold

        if operator == "any":
            return bool(score)
        if operator == "eq":
            return score == threshold
        if operator == "ne":
            return score != threshold
        if operator == "contains":
            return _contains(score, threshold)

        score_number = coerce_number(score)
        threshold_number = coerce_number(threshold)
        if score_number is None:
            raise ValueError(f"Luna score {score!r} is not numeric")
        if threshold_number is None:
            raise ValueError(f"Luna threshold {threshold!r} is not numeric")

        if operator == "gt":
            return score_number > threshold_number
        if operator == "gte":
            return score_number >= threshold_number
        if operator == "lt":
            return score_number < threshold_number
        if operator == "lte":
            return score_number <= threshold_number
