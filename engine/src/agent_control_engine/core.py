"""Core logic for the control engine.

Evaluates controls in parallel with cancel-on-deny for efficiency.
"""

import asyncio
import functools
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import re2
from agent_control_evaluators import get_evaluator_instance
from agent_control_models import (
    ConditionNode,
    ControlAction,
    ControlMatch,
    ControlScope,
    EvaluationRequest,
    EvaluationResponse,
    EvaluatorResult,
    JSONObject,
)

from .selectors import select_data

logger = logging.getLogger(__name__)


def _env_positive_int(*names: str, default: int) -> int:
    """Read a positive integer from the first configured environment variable."""
    for name in names:
        value = os.environ.get(name)
        if value is None or value.strip() == "":
            continue
        try:
            parsed = int(value)
        except ValueError as exc:
            raise RuntimeError(f"{name}={value!r} must be an integer.") from exc
        if parsed < 1:
            raise RuntimeError(f"{name}={value!r} must be greater than or equal to 1.")
        return parsed
    return default


# Default timeout for evaluator execution (seconds)
DEFAULT_EVALUATOR_TIMEOUT = float(os.environ.get("EVALUATOR_TIMEOUT_SECONDS", "30"))

# Max concurrent evaluations (limits task spawning overhead for large policies).
# Prefer the namespaced env var; MAX_CONCURRENT_EVALUATIONS is kept for compatibility.
MAX_CONCURRENT_EVALUATIONS = _env_positive_int(
    "AGENT_CONTROL_MAX_CONCURRENT_EVALUATIONS",
    "MAX_CONCURRENT_EVALUATIONS",
    default=3,
)

SELECTED_DATA_PREVIEW_MAX_CHARS = int(
    os.environ.get("AGENT_CONTROL_SELECTED_DATA_PREVIEW_MAX_CHARS", "500")
)
SELECTED_DATA_PREVIEW_MAX_ITEMS = int(
    os.environ.get("AGENT_CONTROL_SELECTED_DATA_PREVIEW_MAX_ITEMS", "20")
)
SELECTED_DATA_PREVIEW_MAX_DEPTH = int(
    os.environ.get("AGENT_CONTROL_SELECTED_DATA_PREVIEW_MAX_DEPTH", "3")
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Read a boolean environment flag."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key is likely to contain a secret."""
    normalized = str(key).lower()
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _truncate_string(value: str, max_chars: int) -> tuple[str, bool]:
    """Return a bounded string preview and whether it was truncated."""
    if len(value) <= max_chars:
        return value, False
    if max_chars <= 3:
        return value[:max_chars], True
    return f"{value[: max_chars - 3]}...", True


def _selected_data_preview_value(
    value: Any,
    *,
    depth: int = 0,
) -> tuple[Any, bool]:
    """Build a bounded, redacted preview of selected data."""
    if depth >= SELECTED_DATA_PREVIEW_MAX_DEPTH:
        return "<max depth reached>", True

    if value is None or isinstance(value, bool | int | float):
        return value, False

    if isinstance(value, str):
        return _truncate_string(value, SELECTED_DATA_PREVIEW_MAX_CHARS)

    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        truncated = len(value) > SELECTED_DATA_PREVIEW_MAX_ITEMS
        for index, (key, item) in enumerate(value.items()):
            if index >= SELECTED_DATA_PREVIEW_MAX_ITEMS:
                break
            preview_key = str(key)
            if _is_sensitive_key(key):
                preview[preview_key] = "<redacted>"
                truncated = True
                continue
            preview_item, item_truncated = _selected_data_preview_value(
                item,
                depth=depth + 1,
            )
            preview[preview_key] = preview_item
            truncated = truncated or item_truncated
        return preview, truncated

    if isinstance(value, list | tuple):
        preview_items: list[Any] = []
        truncated = len(value) > SELECTED_DATA_PREVIEW_MAX_ITEMS
        for item in value[:SELECTED_DATA_PREVIEW_MAX_ITEMS]:
            preview_item, item_truncated = _selected_data_preview_value(
                item,
                depth=depth + 1,
            )
            preview_items.append(preview_item)
            truncated = truncated or item_truncated
        return preview_items, truncated

    text_preview, truncated = _truncate_string(str(value), SELECTED_DATA_PREVIEW_MAX_CHARS)
    return text_preview, truncated


def _selected_data_preview(value: Any) -> dict[str, Any]:
    """Return UI-safe selector output details for evaluator-level inspection."""
    preview, truncated = _selected_data_preview_value(value)
    return {
        "type": type(value).__name__,
        "value": preview,
        "truncated": truncated,
    }


@functools.lru_cache(maxsize=256)
def _compile_regex(pattern: str) -> Any:
    """Compile and cache RE2 regex patterns.

    Caching avoids recompiling the same pattern on every request.
    """
    return re2.compile(pattern)


class ControlDefinitionLike(Protocol):
    """Runtime control shape required by the engine."""

    enabled: bool
    execution: Literal["server", "sdk"]
    scope: ControlScope
    condition: ConditionNode
    action: ControlAction


class ControlWithIdentity(Protocol):
    """Protocol for a control with identity information."""

    @property
    def id(self) -> int:
        """Database identity for the control."""

    @property
    def name(self) -> str:
        """Human-readable name for the control."""

    @property
    def control(self) -> ControlDefinitionLike:
        """Runtime control payload used during evaluation."""


@dataclass
class _EvalTask:
    """Internal container for evaluation task context."""

    item: ControlWithIdentity
    task: asyncio.Task[None] | None = None
    result: EvaluatorResult | None = None
    execution_duration_ms: float | None = None


@dataclass
class _ConditionEvaluation:
    """Internal result for recursive condition evaluation."""

    result: EvaluatorResult
    trace: dict[str, Any]


class ControlEngine:
    """Executes controls against requests with parallel evaluation.

    Controls are evaluated in parallel using asyncio. On the first
    deny match, remaining tasks are cancelled for efficiency.

    Args:
        controls: Sequence of controls to evaluate.
        context: Execution context. 'sdk' runs controls with execution="sdk",
                 'server' runs controls with execution="server".
    """

    def __init__(
        self,
        controls: Sequence[ControlWithIdentity],
        context: Literal["sdk", "server"] = "server",
        *,
        include_raw_selected_data: bool | None = None,
    ):
        self.controls = controls
        self.context = context
        self.include_raw_selected_data = (
            _env_flag("AGENT_CONTROL_INCLUDE_RAW_SELECTED_DATA")
            if include_raw_selected_data is None
            else include_raw_selected_data
        )

    @staticmethod
    def _truncated_message(message: str | None) -> str | None:
        """Truncate long evaluator messages in condition traces."""
        if not message:
            return None
        if len(message) <= 200:
            return message
        return f"{message[:197]}..."

    @staticmethod
    def _format_exception(error: BaseException) -> str:
        """Format exceptions consistently for result.error fields."""
        return f"{type(error).__name__}: {error}"

    @staticmethod
    def _build_error_result(
        error: str,
        *,
        message_prefix: str = "Evaluation failed",
    ) -> EvaluatorResult:
        """Create a failed evaluator result from an internal error string."""
        return EvaluatorResult(
            matched=False,
            confidence=0.0,
            message=f"{message_prefix}: {error}",
            error=error,
        )

    def _skipped_trace(self, node: ConditionNode, reason: str) -> dict[str, Any]:
        """Build an unevaluated trace subtree for short-circuited branches."""
        trace: dict[str, Any] = {
            "type": node.kind(),
            "evaluated": False,
            "matched": None,
            "short_circuit_reason": reason,
        }
        if node.is_leaf():
            leaf_parts = node.leaf_parts()
            if leaf_parts is None:
                raise ValueError("Leaf condition must contain selector and evaluator")
            selector, evaluator = leaf_parts
            trace["selector_path"] = selector.path
            trace["evaluator_name"] = evaluator.name
            trace["confidence"] = None
            trace["error"] = None
            return trace

        trace["children"] = [
            self._skipped_trace(child, reason) for child in node.children_in_order()
        ]
        return trace

    async def _evaluate_leaf(
        self,
        item: ControlWithIdentity,
        node: ConditionNode,
        request: EvaluationRequest,
        semaphore: asyncio.Semaphore,
        extensions: JSONObject | None,
    ) -> _ConditionEvaluation:
        """Evaluate a leaf selector/evaluator pair.

        The shared semaphore limits concurrent leaf evaluator executions across
        the entire engine run. Composite conditions evaluate serially, so a
        single control only holds one semaphore slot at a time, but multi-leaf
        controls may acquire and release that shared slot more than once while
        traversing their tree.
        """
        leaf_parts = node.leaf_parts()
        if leaf_parts is None:
            raise ValueError("Leaf condition must contain selector and evaluator")
        selector, evaluator_spec = leaf_parts

        selector_path = selector.path or "*"
        data = select_data(request.step, selector_path)

        try:
            async with semaphore:
                evaluator = get_evaluator_instance(evaluator_spec)
                timeout = evaluator.get_timeout_seconds()
                if timeout <= 0:
                    timeout = DEFAULT_EVALUATOR_TIMEOUT

                result = await asyncio.wait_for(
                    evaluator.evaluate_with_extensions(data, request.step, extensions),
                    timeout=timeout,
                )
        except TimeoutError:
            error_msg = f"TimeoutError: Evaluator exceeded {timeout}s timeout"
            logger.warning(
                "Evaluator timeout for control '%s' (evaluator: %s): %s",
                item.name,
                evaluator_spec.name,
                error_msg,
                exc_info=True,
            )
            result = self._build_error_result(error_msg)
        except Exception as e:
            error_msg = self._format_exception(e)
            logger.error(
                "Evaluator error for control '%s' (evaluator: %s): %s",
                item.name,
                evaluator_spec.name,
                error_msg,
                exc_info=True,
            )
            result = self._build_error_result(error_msg)

        trace = {
            "type": "leaf",
            "evaluated": True,
            "matched": result.matched,
            "selector_path": selector_path,
            "evaluator_name": evaluator_spec.name,
            "confidence": result.confidence,
            "error": result.error,
            "message": self._truncated_message(result.message),
        }
        metadata = dict(result.metadata or {})
        if self.include_raw_selected_data:
            metadata["engine_selected_data"] = data
        metadata["engine_selected_data_preview"] = _selected_data_preview(data)
        metadata["condition_trace"] = trace
        return _ConditionEvaluation(
            result=result.model_copy(update={"metadata": metadata}),
            trace=trace,
        )

    def _build_composite_result(
        self,
        *,
        matched: bool,
        confidence: float,
        trace: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> EvaluatorResult:
        """Create a composite evaluator result with a condition trace."""
        result_metadata = dict(metadata or {})
        result_metadata["condition_trace"] = trace

        if error is not None:
            return EvaluatorResult(
                matched=False,
                confidence=0.0,
                message=(
                    "Condition evaluation aborted due to a child evaluator error: "
                    f"{error}"
                ),
                metadata=result_metadata,
                error=error,
            )

        message = "Condition tree matched" if matched else "Condition tree did not match"
        return EvaluatorResult(
            matched=matched,
            confidence=confidence,
            message=message,
            metadata=result_metadata,
        )

    @staticmethod
    def _composite_metadata(
        child_evaluations: Sequence[_ConditionEvaluation],
        *,
        matched: bool,
    ) -> dict[str, Any] | None:
        """Select stable child metadata to preserve on composite results.

        The engine_selected_data_preview value in this metadata is not all
        evaluator inputs. It is the bounded selected value preview from the leaf
        metadata the engine preserves for the final composite result:
        - or where one child matches: engine_selected_data_preview comes from the
          matching child.
        - and where one child fails: engine_selected_data_preview comes from the
          failing child.
        - and where all children match: engine_selected_data_preview comes from the
          first matching child, usually the first leaf.
        - or where no children match: engine_selected_data_preview comes from the
          first evaluated child.
        - not: engine_selected_data_preview comes from its child.
        """
        source_result: EvaluatorResult | None = None
        if matched:
            source_result = next(
                (
                    evaluation.result
                    for evaluation in child_evaluations
                    if evaluation.result.matched
                ),
                None,
            )
        if source_result is None and child_evaluations:
            source_result = child_evaluations[0].result
        if source_result is None or source_result.metadata is None:
            return None
        return dict(source_result.metadata)

    async def _evaluate_condition(
        self,
        item: ControlWithIdentity,
        node: ConditionNode,
        request: EvaluationRequest,
        semaphore: asyncio.Semaphore,
        extensions: JSONObject | None,
    ) -> _ConditionEvaluation:
        """Evaluate a recursive condition tree."""
        if node.is_leaf():
            return await self._evaluate_leaf(item, node, request, semaphore, extensions)

        kind = node.kind()
        children = node.children_in_order()
        child_evaluations: list[_ConditionEvaluation] = []

        if kind == "not":
            child_eval = await self._evaluate_condition(
                item, children[0], request, semaphore, extensions
            )
            trace = {
                "type": "not",
                "evaluated": True,
                "matched": None if child_eval.result.error else (not child_eval.result.matched),
                "children": [child_eval.trace],
            }
            if child_eval.result.error:
                return _ConditionEvaluation(
                    result=self._build_composite_result(
                        matched=False,
                        confidence=0.0,
                        trace=trace,
                        metadata=child_eval.result.metadata,
                        error=child_eval.result.error,
                    ),
                    trace=trace,
                )

            result = self._build_composite_result(
                matched=not child_eval.result.matched,
                confidence=child_eval.result.confidence,
                trace=trace,
                metadata=child_eval.result.metadata,
            )
            return _ConditionEvaluation(result=result, trace=trace)

        for index, child in enumerate(children):
            child_eval = await self._evaluate_condition(
                item, child, request, semaphore, extensions
            )
            child_evaluations.append(child_eval)

            if child_eval.result.error:
                remaining = children[index + 1 :]
                trace = {
                    "type": kind,
                    "evaluated": True,
                    "matched": None,
                    "children": [
                        evaluation.trace for evaluation in child_evaluations
                    ]
                    + [self._skipped_trace(rest, "error") for rest in remaining],
                    "short_circuit_reason": "error",
                }
                return _ConditionEvaluation(
                    result=self._build_composite_result(
                        matched=False,
                        confidence=0.0,
                        trace=trace,
                        metadata=child_eval.result.metadata,
                        error=child_eval.result.error,
                    ),
                    trace=trace,
                )

            should_short_circuit = (
                kind == "and" and not child_eval.result.matched
            ) or (kind == "or" and child_eval.result.matched)
            if should_short_circuit:
                remaining = children[index + 1 :]
                matched = child_eval.result.matched if kind == "or" else False
                trace = {
                    "type": kind,
                    "evaluated": True,
                    "matched": matched,
                    "children": [
                        evaluation.trace for evaluation in child_evaluations
                    ]
                    + [
                        self._skipped_trace(
                            rest,
                            "or_matched" if kind == "or" else "and_failed",
                        )
                        for rest in remaining
                    ],
                    "short_circuit_reason": (
                        "or_matched" if kind == "or" else "and_failed"
                    ),
                }
                confidence = min(
                    evaluation.result.confidence for evaluation in child_evaluations
                )
                result = self._build_composite_result(
                    matched=matched,
                    confidence=confidence,
                    trace=trace,
                    metadata=child_eval.result.metadata,
                )
                return _ConditionEvaluation(result=result, trace=trace)

        confidence = min(evaluation.result.confidence for evaluation in child_evaluations)
        matched = all(
            evaluation.result.matched for evaluation in child_evaluations
        ) if kind == "and" else any(
            evaluation.result.matched for evaluation in child_evaluations
        )
        trace = {
            "type": kind,
            "evaluated": True,
            "matched": matched,
            "children": [evaluation.trace for evaluation in child_evaluations],
        }
        result = self._build_composite_result(
            matched=matched,
            confidence=confidence,
            trace=trace,
            metadata=self._composite_metadata(child_evaluations, matched=matched),
        )
        return _ConditionEvaluation(result=result, trace=trace)

    def get_applicable_controls(
        self,
        request: EvaluationRequest,
        selector_errors: list[ControlMatch] | None = None,
    ) -> list[ControlWithIdentity]:
        """Get all controls that apply to the current request."""
        applicable = []
        step = request.step
        step_type = step.type
        step_name = step.name

        for item in self.controls:
            control_def = item.control

            if not control_def.enabled:
                continue

            scope = control_def.scope
            if scope.stages and request.stage not in scope.stages:
                continue
            if scope.step_types and step_type not in scope.step_types:
                continue

            # Filter by locality based on context
            if control_def.execution != self.context:
                continue

            # Optional step name scoping
            if scope.step_names or scope.step_name_regex:
                match = False
                if scope.step_names and step_name in scope.step_names:
                    match = True
                if not match and scope.step_name_regex:
                    try:
                        if _compile_regex(scope.step_name_regex).search(step_name) is not None:
                            match = True
                    except re2.error as e:
                        # Invalid pattern should have been caught at model validation;
                        # skip defensively but surface an error if requested.
                        if selector_errors is not None:
                            selector_errors.append(
                                ControlMatch(
                                    control_id=item.id,
                                    control_name=item.name,
                                    action=control_def.action.decision,
                                    result=EvaluatorResult(
                                        matched=False,
                                        confidence=0.0,
                                        message=(
                                            "Control skipped due to invalid step_name_regex: "
                                            f"'{scope.step_name_regex}'"
                                        ),
                                        error=f"Invalid step_name_regex: {e}",
                                    ),
                                    steering_context=control_def.action.steering_context,
                                )
                            )
                        continue
                if not match:
                    continue

            applicable.append(item)

