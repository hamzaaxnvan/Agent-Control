"""Agent Control plugin integration for Google ADK."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import weakref
from collections.abc import Callable, Iterable
from typing import Any, Literal, cast
from uuid import uuid4

from agent_control_models.server import GetAgentResponse

import agent_control
from agent_control import AgentControlClient, agents
from agent_control._control_registry import StepSchemaDict
from agent_control._schema_derivation import derive_schemas
from agent_control._state import state
from agent_control.integrations._core import _evaluate_and_enforce
from agent_control.integrations._tools import normalized_tool_definition
from agent_control.validation import ensure_agent_name

try:
    from google.adk.agents.callback_context import (  # type: ignore[import-not-found,import-untyped]
        CallbackContext,
    )
    from google.adk.models import (  # type: ignore[import-not-found,import-untyped]
        LlmRequest,
        LlmResponse,
    )
    from google.adk.plugins import BasePlugin  # type: ignore[import-not-found,import-untyped]
    from google.adk.tools import BaseTool  # type: ignore[import-not-found,import-untyped]
    from google.adk.tools.tool_context import (  # type: ignore[import-not-found,import-untyped]
        ToolContext,
    )
except Exception as exc:  # pragma: no cover - optional dependency
    raise RuntimeError(
        "Google ADK integration requires google-adk. "
        "Install with: agent-control-sdk[google-adk]."
    ) from exc

from ._extractors import (
    build_blocked_llm_response,
    build_blocked_tool_response,
    extract_request_text,
    extract_response_text,
    resolve_agent_name,
    resolve_tool_agent_name,
    resolve_tool_name,
)

logger = logging.getLogger(__name__)

_ALL_HOOKS = {"before_model", "after_model", "before_tool", "after_tool"}
_SYNC_TIMEOUT_SECONDS = 30


class AgentControlPlugin(BasePlugin):
    """Google ADK plugin that enforces Agent Control across model and tool hooks.

    Google ADK lifecycle callbacks expose model and tool operations only, so
    this adapter intentionally uses the built-in ``llm`` and ``tool`` step
    types. Custom step types remain available through the core SDK APIs.
    """

    name = "agent-control-google-adk"

    def __init__(
        self,
        agent_name: str,
        *,
        enabled_hooks: set[str] | None = None,
        blocked_message_template: str | None = None,
        step_name_overrides: dict[str, str] | None = None,
        step_name_resolver: Callable[..., str | None] | None = None,
        context_extractor: Callable[..., dict[str, Any] | None] | None = None,
        on_violation_callback: Callable[[dict[str, Any], Any], None] | None = None,
        enable_logging: bool = True,
    ) -> None:
        try:
            # Galileo's local ADK plugin code uses BasePlugin(name=...), but keep
            # a fallback for older/mock BasePlugin implementations that only
            # accept a no-arg constructor.
            super().__init__(name=self.name)
        except TypeError:
            super().__init__()

        normalized_name = ensure_agent_name(agent_name)
        current = state.current_agent
        if current is not None and current.agent_name != normalized_name:
            raise ValueError(
                "AgentControlPlugin agent_name must match the currently initialized "
                "agent_control agent."
            )

        self.agent_name = normalized_name
        self.enabled_hooks = set(enabled_hooks or _ALL_HOOKS)
        self.blocked_message_template = blocked_message_template
        self.step_name_overrides = dict(step_name_overrides or {})
        self.step_name_resolver = step_name_resolver
        self.context_extractor = context_extractor
        self.on_violation_callback = on_violation_callback
        self.enable_logging = enable_logging
        self._generated_invocation_ids: weakref.WeakKeyDictionary[object, str] = (
            weakref.WeakKeyDictionary()
        )
        self._generated_invocation_ids_by_context_id: dict[int, str] = {}
        self._generated_context_ids_by_invocation_id: dict[str, int] = {}
        self._request_text_by_call_key: dict[tuple[str, str], str] = {}
        self._request_tools_by_call_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._request_object_ids_by_call_key: dict[tuple[str, str], int] = {}
        self._current_llm_call_ids: dict[str, list[str]] = {}
        self._stored_llm_call_ids: dict[int, str] = {}
        self._known_steps: dict[tuple[str, str], StepSchemaDict] = {}
        self._synced_step_keys: set[tuple[str, str]] = set()
        self._step_sync_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._available_tools_by_step: dict[str, list[dict[str, Any]]] = {}

    def bind(self, agent: Any) -> None:
        """Pre-register known ADK steps before the runner starts."""

        steps = self._discover_steps(agent)
        self._remember_available_tools(agent)
        self._remember_steps(steps)
        self._sync_steps_blocking(steps, raise_on_error=True)

    async def close(self) -> None:
        """Release per-run state and cancel any outstanding step-sync tasks."""

        pending_tasks = list(self._step_sync_tasks.values())
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        self._step_sync_tasks.clear()
        self._generated_invocation_ids.clear()
        self._generated_invocation_ids_by_context_id.clear()
        self._generated_context_ids_by_invocation_id.clear()
        self._request_text_by_call_key.clear()
        self._request_tools_by_call_key.clear()
        self._request_object_ids_by_call_key.clear()
        self._current_llm_call_ids.clear()
        self._stored_llm_call_ids.clear()

        base_close = getattr(super(), "close", None)
        if callable(base_close):
            result = base_close()
            if inspect.isawaitable(result):
                await result

    async def before_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        """Evaluate controls before an ADK model call."""

        if "before_model" not in self.enabled_hooks:
            return None

        step_name = self._resolve_llm_step_name(callback_context)
        request_text = extract_request_text(llm_request)
        available_tools = self._invocation_tools(llm_request, step_name=step_name)
        invocation_id: str | None = None
        call_id: str | None = None
        if "after_model" in self.enabled_hooks:
            invocation_id = self._resolve_invocation_id(callback_context)
            call_id = self._register_llm_request(
                invocation_id,
                llm_request,
                request_text,
                available_tools,
            )
        self._ensure_step_known(
            self._build_llm_step_schema(step_name, callback_context=callback_context),
        )

        context = self._safe_context(
            step_type="llm",
            stage="pre",
            callback_context=callback_context,
            llm_request=llm_request,
        )

        try:
            await _evaluate_and_enforce(
                self.agent_name,
                step_name,
                input=request_text,
                context=context,
                tools=available_tools,
                step_type="llm",
                stage="pre",
            )
        except Exception as exc:
            response = self._handle_llm_exception(
                exc,
                callback_context=callback_context,
                llm_request=llm_request,
                step_name=step_name,
                stage="pre",
            )
            if response is not None and invocation_id is not None and call_id is not None:
                self._clear_pending_llm_state(invocation_id, call_id, llm_request=llm_request)
            return response
        return None

    async def after_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        """Evaluate controls after an ADK model call."""

        if "after_model" not in self.enabled_hooks:
            return None

        step_name = self._resolve_llm_step_name(callback_context)
        invocation_id = self._resolve_invocation_id(callback_context)
        call_id = self._resolve_llm_call_id(llm_response, invocation_id)
        call_key = (invocation_id, call_id)
        input_text = self._request_text_by_call_key.pop(call_key, "")
        available_tools = self._request_tools_by_call_key.pop(
            call_key,
            self._available_tools_by_step.get(step_name, []),
        )
        self._clear_pending_llm_state(invocation_id, call_id, llm_response=llm_response)
        output_text = extract_response_text(llm_response)
        self._ensure_step_known(
            self._build_llm_step_schema(step_name, callback_context=callback_context),
        )

        context = self._safe_context(
            step_type="llm",
            stage="post",
            callback_context=callback_context,
            llm_response=llm_response,
        )

        try:
            await _evaluate_and_enforce(
                self.agent_name,
                step_name,
                input=input_text,
                output=output_text,
                context=context,
                tools=available_tools,
                step_type="llm",
                stage="post",
            )
        except Exception as exc:
            return self._handle_llm_exception(
                exc,
                callback_context=callback_context,
                llm_response=llm_response,
                step_name=step_name,
                stage="post",
            )
        return None

    async def on_model_error_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
        error: Exception,
    ) -> LlmResponse | None:
        """Clean up request correlation when ADK reports a model error."""

        _ = error
        invocation_id = self._resolve_invocation_id(callback_context)
        call_id = self._resolve_llm_call_id(llm_request, invocation_id)
        self._clear_pending_llm_state(invocation_id, call_id, llm_request=llm_request)
        return None

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        """Evaluate controls before an ADK tool call."""

        if "before_tool" not in self.enabled_hooks:
            return None

        step_name = self._resolve_tool_step_name(tool, tool_context=tool_context)
        self._ensure_step_known(self._build_tool_step_schema(tool, step_name))
        context = self._safe_context(
            step_type="tool",
            stage="pre",
            tool=tool,
            tool_args=tool_args,
            tool_context=tool_context,
        )

        try:
            await _evaluate_and_enforce(
                self.agent_name,
                step_name,
                input=tool_args,
                context=context,
                step_type="tool",
                stage="pre",
            )
        except Exception as exc:
            return self._handle_tool_exception(
                exc,
                tool=tool,
                tool_args=tool_args,
                tool_context=tool_context,
                step_name=step_name,
                stage="pre",
            )
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Evaluate controls after an ADK tool call."""

        if "after_tool" not in self.enabled_hooks:
            return None

        step_name = self._resolve_tool_step_name(tool, tool_context=tool_context)
        self._ensure_step_known(self._build_tool_step_schema(tool, step_name))
        context = self._safe_context(
            step_type="tool",
            stage="post",
            tool=tool,
            tool_args=tool_args,
            tool_context=tool_context,
            result=result,
        )

        try:
            await _evaluate_and_enforce(
                self.agent_name,
                step_name,
                input=tool_args,
                output=result,
                context=context,
                step_type="tool",
                stage="post",
            )
        except Exception as exc:
            return self._handle_tool_exception(
                exc,
                tool=tool,
                tool_args=tool_args,
                tool_context=tool_context,
                step_name=step_name,
                stage="post",
            )
        return None

    def _resolve_llm_step_name(self, callback_context: CallbackContext) -> str:
        raw_name = resolve_agent_name(callback_context)
        return self._resolve_step_name(
            raw_name,
            step_type="llm",
            callback_context=callback_context,
        )

    def _resolve_tool_step_name(
        self,
        tool: BaseTool,
        *,
        tool_context: ToolContext | None = None,
        agent_step_name: str | None = None,
    ) -> str:
        raw_name = resolve_tool_name(tool)
        resolved_agent_step_name = agent_step_name
        if resolved_agent_step_name is None:
            resolved_agent_step_name = self._resolve_tool_agent_step_name(tool_context)
        default_name = (
            f"{resolved_agent_step_name}.{raw_name}" if resolved_agent_step_name else raw_name
        )
        return self._resolve_step_name(
            default_name,
            step_type="tool",
            override_keys=(raw_name,),
            tool=tool,
            tool_context=tool_context,
            raw_name=raw_name,
            agent_step_name=resolved_agent_step_name,
        )

    def _resolve_step_name(
        self,
        default_name: str,
        *,
        step_type: Literal["llm", "tool"],
        override_keys: Iterable[str] = (),
        **kwargs: Any,
    ) -> str:
        candidate_names = [default_name, *override_keys]
        for candidate_name in candidate_names:
            override = self.step_name_overrides.get(candidate_name)
            if override:
                return override

        if self.step_name_resolver is not None:
            resolved = self.step_name_resolver(
                step_type=step_type,
                default_name=default_name,
                override_keys=tuple(candidate_names),
                **kwargs,
            )
            if isinstance(resolved, str) and resolved:
                return resolved

        return default_name

    def _resolve_tool_agent_step_name(self, tool_context: ToolContext | None) -> str | None:
        if tool_context is None:
            return None

        callback_context = getattr(tool_context, "callback_context", None)
        if callback_context is not None:
            return self._resolve_llm_step_name(callback_context)

        raw_agent_name = resolve_tool_agent_name(tool_context)
        if raw_agent_name is None:
            return None

        return self._resolve_step_name(
            raw_agent_name,
            step_type="llm",
            agent_name=raw_agent_name,
            tool_context=tool_context,
        )

    def _safe_context(
        self,
        *,
        step_type: Literal["llm", "tool"],
        stage: Literal["pre", "post"],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        if self.context_extractor is None:
            return None
        try:
            return self.context_extractor(step_type=step_type, stage=stage, **kwargs)
        except Exception:
            logger.warning("Google ADK context_extractor failed", exc_info=True)
            return None

    def _format_message(self, reason: str) -> str:
        if not self.blocked_message_template:
            return reason
        try:
            return self.blocked_message_template.format(reason=reason)
        except Exception:
            logger.warning("Invalid blocked_message_template; using raw reason", exc_info=True)
            return reason

    def _handle_llm_exception(
        self,
        exc: Exception,
        *,
        callback_context: CallbackContext,
        step_name: str,
        stage: Literal["pre", "post"],
        llm_request: LlmRequest | None = None,
        llm_response: LlmResponse | None = None,
    ) -> LlmResponse | None:
        self._invoke_callback(step_name, "llm", stage, exc)

        if (
            isinstance(exc, agent_control.ControlSteerError)
            and stage == "pre"
            and llm_request is not None
        ):
            if self._inject_steering_guidance(llm_request, exc.steering_context):
                return None

        if isinstance(exc, agent_control.ControlSteerError):
            message = exc.steering_context or exc.message
        elif isinstance(exc, agent_control.ControlViolationError):
            message = exc.message
        else:
            logger.error("Google ADK model control evaluation failed", exc_info=True)
            message = f"Agent Control could not evaluate the request safely: {exc}"

        return build_blocked_llm_response(self._format_message(message))

    def _handle_tool_exception(
        self,
        exc: Exception,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        step_name: str,
        stage: Literal["pre", "post"],
    ) -> dict[str, Any]:
        self._invoke_callback(step_name, "tool", stage, exc)

        if isinstance(exc, agent_control.ControlSteerError):
            message = exc.steering_context or exc.message
        elif isinstance(exc, agent_control.ControlViolationError):
            message = exc.message
        else:
            logger.error("Google ADK tool control evaluation failed", exc_info=True)
            message = f"Agent Control could not evaluate the request safely: {exc}"

        return build_blocked_tool_response(self._format_message(message))

    def _invoke_callback(
        self,
        step_name: str,
        step_type: Literal["llm", "tool"],
        stage: Literal["pre", "post"],
        exc: Exception,
    ) -> None:
        if self.on_violation_callback is None:
            return
        if not isinstance(
            exc,
            (agent_control.ControlViolationError, agent_control.ControlSteerError),
        ):
            return

        result_like = {
            "action": "steer" if isinstance(exc, agent_control.ControlSteerError) else "deny",
            "message": exc.message,
            "steering_context": (
                exc.steering_context if isinstance(exc, agent_control.ControlSteerError) else None
            ),
        }
        try:
            self.on_violation_callback(
                {
                    "agent": self.agent_name,
                    "step_name": step_name,
                    "step_type": step_type,
                    "stage": stage,
                },
                result_like,
            )
        except Exception:
            logger.warning("Google ADK on_violation_callback failed", exc_info=True)

    def _inject_steering_guidance(self, llm_request: LlmRequest, guidance: str | None) -> bool:
        if not guidance:
            return False

        config = getattr(llm_request, "config", None)
        if config is None:
            return False

        current_instruction = getattr(config, "system_instruction", None)
        if isinstance(current_instruction, str) and current_instruction:
            new_instruction = f"{current_instruction}\n\nAgent Control guidance: {guidance}"
        else:
            new_instruction = f"Agent Control guidance: {guidance}"

        try:
            setattr(config, "system_instruction", new_instruction)
        except Exception:
            logger.debug("Could not inject steering guidance into ADK request", exc_info=True)
            return False
        return True

    def _build_llm_step_schema(
        self,
        step_name: str,
        *,
        callback_context: CallbackContext | None = None,
    ) -> StepSchemaDict:
        description = None
        if callback_context is not None:
            callback_agent = getattr(callback_context, "agent", None)
            description = getattr(callback_agent, "description", None)
        step: StepSchemaDict = {
            "type": "llm",
            "name": step_name,
            "input_schema": {"text": {"type": "string"}},
            "output_schema": {"text": {"type": "string"}},
            "metadata": {"framework": "google_adk"},
        }
        if isinstance(description, str) and description:
            step["description"] = description
        return step

    def _build_tool_step_schema(self, tool: Any, step_name: str) -> StepSchemaDict:
        description = getattr(tool, "description", None)
        schema_source = self._resolve_schema_source(tool)
        if schema_source is not None:
            schemas = derive_schemas(schema_source)
            input_schema = schemas.input_schema
            output_schema = schemas.output_schema
        else:
            input_schema = {"type": "object", "additionalProperties": True}
            output_schema = {}

        step: StepSchemaDict = {
            "type": "tool",
            "name": step_name,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "metadata": {"framework": "google_adk"},
        }
        if isinstance(description, str) and description:
            step["description"] = description
        return step

    def _resolve_schema_source(self, tool: Any) -> Callable[..., Any] | None:
        if callable(tool):
            return cast(Callable[..., Any], tool)

        for attr_name in ("run_async", "run", "func", "callback"):
            candidate = getattr(tool, attr_name, None)
            if callable(candidate):
                return cast(Callable[..., Any], candidate)
        return None

    def _discover_steps(self, agent: Any) -> list[StepSchemaDict]:
        steps: list[StepSchemaDict] = []
        for current_agent in self._iter_agents(agent):
            resolved_agent_name: str | None = None
            agent_name = getattr(current_agent, "name", None)
            if isinstance(agent_name, str) and agent_name:
                resolved_agent_name = self._resolve_step_name(
                    agent_name,
                    step_type="llm",
                    callback_context=None,
                    agent=current_agent,
                )
                steps.append(
                    self._build_llm_step_schema(resolved_agent_name),
                )

            for tool in self._iter_tools(current_agent):
                tool_name = self._resolve_tool_step_name(
                    tool,
                    agent_step_name=resolved_agent_name,
                )
                steps.append(self._build_tool_step_schema(tool, tool_name))

        deduped: dict[tuple[str, str], StepSchemaDict] = {}
        for step in steps:
            deduped[(step["type"], step["name"])] = step
        return list(deduped.values())

    def _iter_agents(self, root_agent: Any) -> Iterable[Any]:
        seen: set[int] = set()
        stack = [root_agent]
        while stack:
            current = stack.pop()
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            yield current

            # ADK composite agents are not guaranteed to expose one uniform
            # child-agent attribute, so traverse a small set of observed names.
