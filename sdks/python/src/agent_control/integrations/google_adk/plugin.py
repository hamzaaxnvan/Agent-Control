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

