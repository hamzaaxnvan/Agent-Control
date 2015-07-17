"""Galileo Decision Models evaluator."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx
from agent_control_evaluators import Evaluator, EvaluatorMetadata, register_evaluator
from agent_control_models import EvaluatorResult, JSONObject, JSONValue, Step

from .client import (
    DecisionModelsExecutionContext,
    DecisionModelsInvokeInputs,
    DecisionModelsInvokeResponse,
    GalileoDecisionModelsClient,
)
from .config import (
    DecisionModelsEvaluatorConfig,
    decision_models_evaluator_enabled,
    scorer_invoke_runtime_enabled,
)

logger = logging.getLogger(__name__)

try:
    _PACKAGE_VERSION = version("agent-control-evaluator-galileo")
except PackageNotFoundError:
    _PACKAGE_VERSION = "0.0.0.dev"


def _contains(value: JSONValue, threshold: JSONValue) -> bool:
    if isinstance(value, str):
        return str(threshold) in value
    if isinstance(value, list):
        return threshold in value
    if isinstance(value, dict):
        return threshold in value.values()
    return False


@register_evaluator
class DecisionModelsEvaluator(Evaluator[DecisionModelsEvaluatorConfig]):
    """Evaluate data using a pinned Galileo Decision Models scorer."""

    metadata = EvaluatorMetadata(
        name="galileo.decision_models",
        version=_PACKAGE_VERSION,
        description="Galileo Decision Models scoring",
        requires_api_key=True,
        timeout_ms=10000,
    )
    config_model = DecisionModelsEvaluatorConfig

    @classmethod
    def is_available(cls) -> bool:
        """Expose Decision Models only when its feature flag and scorer runtime are enabled."""
        return decision_models_evaluator_enabled() and scorer_invoke_runtime_enabled()

    def __init__(self, config: DecisionModelsEvaluatorConfig) -> None:
        super().__init__(config)
        self._client = GalileoDecisionModelsClient()

    async def evaluate(self, data: Any) -> EvaluatorResult:
        """Return an actionable error because Decision Models requires runtime context."""
        if not scorer_invoke_runtime_enabled() or not self._client.runtime_enabled:
            return self._error(
                RuntimeError(
                    "Galileo scorer-invoke runtime is disabled; galileo.decision_models requires "
                    "GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME=enabled."
                )
            )
        return self._error(
            RuntimeError(
                "galileo.decision_models requires Step context and authenticated execution "
                "metadata from runtime extensions"
            )
        )

    async def evaluate_with_context(self, data: Any, step: Step) -> EvaluatorResult:
        """Evaluate a step when only step context is available.

        Decision Models also needs authenticated execution metadata, which this method does not
        receive. The explicit error helps callers distinguish missing runtime metadata from a
        missing step.
        """
        return await self._evaluate(data, step, None)

    async def evaluate_with_extensions(
        self, data: Any, step: Step, extensions: JSONObject | None
    ) -> EvaluatorResult:
        """Evaluate with execution identity forwarded from trusted runtime extensions."""
        try:
            context = self._execution_context(extensions)
            if context is None:
                raise ValueError(
                    "galileo.decision_models requires authenticated execution metadata from "
                    "runtime extensions"
                )
            return await self._evaluate(data, step, context)
        except Exception as exc:
            return self._error(exc)

    async def _evaluate(
        self, data: Any, step: Step, execution_context: DecisionModelsExecutionContext | None
    ) -> EvaluatorResult:
        try:
            if not scorer_invoke_runtime_enabled() or not self._client.runtime_enabled:
                raise RuntimeError(
                    "Galileo scorer-invoke runtime is disabled; galileo.decision_models requires "
                    "GALILEO_FEATURE_FLAG_SCORER_INVOKE_RUNTIME=enabled."
                )
            if execution_context is None:
                raise ValueError(
                    "galileo.decision_models requires authenticated execution metadata from "
                    "runtime extensions; Step context alone is not sufficient"
                )
            inputs = self._inputs(data, step)
            response = await self._client.invoke(
                scorer_id=self.config.scorer_id,
                scorer_version_id=self.config.scorer_version_id,
                scorer_label=self.config.scorer_label,
                step=step,
                execution_context=execution_context,
                inputs=inputs,
