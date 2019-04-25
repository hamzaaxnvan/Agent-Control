"""
Agent Control - Unified agent control, monitoring, and SDK client.

This package provides a complete interface for controlling your agents with
automatic registration, rule enforcement, and server communication.

Usage:
    import agent_control

    # Initialize at the base of your agent file
    agent_control.init(
        agent_name="my-customer-service-bot"
    )

    # Apply server-defined controls using the decorator
    # Control configuration is on server - update rules without code changes!
    @agent_control.control()
    async def chat(message: str) -> str:
        return await assistant.respond(message)

    # Apply all controls for this agent
    @agent_control.control(policy="safety-policy")
    async def process(input: str) -> str:
        return await pipeline.run(input)

    # Use custom step name for control matching
    @agent_control.control(step_name="user_query_handler")
    async def handle_input(user_message: str) -> str:
        return await process_query(user_message)

    # Or use the client directly for server-side checks
    async with agent_control.AgentControlClient() as client:
        result = await agent_control.evaluation.check_evaluation(
            client,
            agent_name,
            step={"type": "llm", "name": "chat", "input": "Hello"},
            stage="pre",
        )
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agent-control-sdk")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

import asyncio
import os
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, TypeVar

import httpx
from agent_control_models import (
    Agent,
    ControlAction,
    ControlDefinition,
    ControlMatch,
    ControlScope,
    ControlSelector,
    EvaluationRequest,
    EvaluationResult,
    EvaluatorResult,
    EvaluatorSpec,
    JSONObject,
    Step,
    StepSchema,
    TemplateControlInput,
    TemplateDefinition,
    TemplateValue,
    UnrenderedTemplateControl,
)
from agent_control_telemetry.trace_context import (
    clear_trace_context_provider,
    get_trace_context_from_provider,
    set_trace_context_provider,
)

from . import agents, control_bindings, controls, evaluation, evaluators, policies
from ._control_registry import (
    StepSchemaDict,
    get_registered_steps,
    merge_explicit_and_auto_steps,
)
from ._control_registry import (
    clear as clear_step_registry,
)
from .client import AgentControlClient
from .control_decorators import ControlSteerError, ControlViolationError, control
from .evaluation import check_evaluation_with_local, evaluate_controls, evaluate_step
from .observability import (
    LogConfig,
    add_event,
    configure_logging,
    get_event_batcher,
    get_event_sink,
    get_log_config,
    get_logger,
    get_registered_control_event_sink_factory_names,
    get_registered_control_event_sinks,
    init_observability,
    is_observability_enabled,
    log_control_evaluation,
    register_control_event_sink,
    register_control_event_sink_factory,
    shutdown_observability,
    sync_shutdown_observability,
    unregister_control_event_sink,
    unregister_control_event_sink_factory,
    write_events,
)
from .otel_sink import control_event_to_otel_span
from .runtime_auth import validate_http_field_name
from .step_recorder import StepRecorder, record_step
from .tracing import (
    get_current_span_id,
    get_current_trace_id,
    get_trace_and_span_ids,
    is_otel_available,
    with_trace,
)
from .validation import ensure_agent_name

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

# Module logger
logger = get_logger(__name__)


# ============================================================================
# Global State
# ============================================================================

# Import state container to avoid circular imports
from ._state import state  # noqa: E402

F = TypeVar("F", bound=Callable[..., Any])

# Policy refresh loop state
_refresh_lock = threading.Lock()
_policy_refresh_interval_seconds: int | None = None
_refresh_thread: threading.Thread | None = None
_refresh_stop_event: threading.Event | None = None

# Session lifecycle state used to discard stale manual refresh results.
_session_lock = threading.Lock()
_session_generation = 0


@dataclass(frozen=True)
class _RefreshContext:
    """Connection/session snapshot for a single refresh request.

    The session-level target context, when set, is captured here so the
    refresh worker forwards it on each ``GET /agents/{name}/controls``
    call. The server returns the merged effective set, which is what
    ``state.server_controls`` is published from.
    """

    session_generation: int
    agent_name: str
    server_url: str
    api_key: str | None
    api_key_header: str | None
    target_type: str | None
    target_id: str | None


def get_server_controls() -> list[dict[str, Any]] | None:
    """Get the cached server controls.

    Returns the controls that were fetched during init() or the last
    refresh_controls() call. Returns None if no controls are cached.

    Returns:
        List of control dicts or None if not initialized.

    Example:
        controls = agent_control.get_server_controls()
        if controls:
            print(f"Loaded {len(controls)} controls")
            for c in controls:
                print(f"  - {c['name']} (execution: {c['control'].get('execution', 'server')})")
    """
    return state.server_controls


def to_template_control_input(
    data: dict[str, Any] | ControlDefinition,
) -> TemplateControlInput:
    """Convert stored control data into template authoring input."""
    return controls.to_template_control_input(data)


def _publish_server_controls(
    controls: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Publish controls using swap-only snapshot semantics."""
    if controls is None:
        state.server_controls = None
        return None

    # Snapshot copy: publish a new list reference and avoid in-place mutation.
    state.server_controls = list(controls)
    return state.server_controls


def _run_coro_in_new_loop[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on a dedicated event loop in the current thread."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _ad_hoc_client(
    *,
    server_url: str,
    api_key: str | None,
    api_key_header: str | None,
) -> AgentControlClient:
    return AgentControlClient(
        base_url=server_url,
        api_key=api_key,
        api_key_header=api_key_header if api_key_header is not None else state.api_key_header,
    )


def _snapshot_refresh_context() -> _RefreshContext:
    """Capture a consistent session snapshot for a refresh request."""
    with _session_lock:
        session_generation = _session_generation
        agent = state.current_agent
        server_url = state.server_url
        api_key = state.api_key
        api_key_header = state.api_key_header
        target_type = state.target_type
        target_id = state.target_id

    if agent is None:
        raise RuntimeError("Agent not initialized. Call agent_control.init() first.")
    if server_url is None:
        raise RuntimeError("Server URL not set. Call agent_control.init() first.")

    return _RefreshContext(
        session_generation=session_generation,
        agent_name=agent.agent_name,
        server_url=server_url,
        api_key=api_key,
        api_key_header=api_key_header,
        target_type=target_type,
        target_id=target_id,
    )


async def _fetch_controls_for_context_async(context: _RefreshContext) -> list[dict[str, Any]]:
    """Fetch controls for a previously snapshotted session context."""
    async with AgentControlClient(
        base_url=context.server_url,
        api_key=context.api_key,
        api_key_header=context.api_key_header,
    ) as client:
        response = await agents.list_agent_controls(
            client,
            context.agent_name,
            rendered_state="rendered",
            enabled_state="enabled",
            target_type=context.target_type,
            target_id=context.target_id,
        )
        controls: list[dict[str, Any]] = response.get("controls", [])
        return controls


async def _fetch_controls_async() -> list[dict[str, Any]]:
    """Fetch controls from the server without publishing.

    Snapshots connection state into locals before any I/O so the result
    is safe to discard if shutdown fires mid-flight.

    Returns:
        Raw list of control dicts from the server.

    Raises:
        RuntimeError: If the SDK is not initialized.
        Exception: On network / server errors (caller decides policy).
    """
    context = _snapshot_refresh_context()
    return await _fetch_controls_for_context_async(context)


def _policy_refresh_worker(stop_event: threading.Event, interval_seconds: int) -> None:
    """Background worker that periodically refreshes controls."""
    while not stop_event.wait(interval_seconds):
        if stop_event.is_set():
            break
        try:
            controls = _run_coro_in_new_loop(_fetch_controls_async())
        except Exception as exc:
            logger.error(
                "Background policy refresh loop iteration failed: %s",
                exc,
                exc_info=True,
            )
            continue
        # Do not publish if shutdown was requested during the fetch.
        if stop_event.is_set():
            break
        _publish_server_controls(controls)
        logger.info("Refreshed %d control(s) from server", len(controls))


def _stop_policy_refresh_loop() -> None:
    """Stop the background policy refresh loop if running."""
    global _policy_refresh_interval_seconds, _refresh_thread, _refresh_stop_event

    with _refresh_lock:
        stop_event = _refresh_stop_event
        refresh_thread = _refresh_thread
        _policy_refresh_interval_seconds = None
        _refresh_stop_event = None
        _refresh_thread = None

    if stop_event is not None:
        stop_event.set()

    if refresh_thread is not None and refresh_thread.is_alive():
        refresh_thread.join(timeout=2)
        if refresh_thread.is_alive():
            logger.warning("Timed out while stopping policy refresh loop thread")


def _start_policy_refresh_loop(interval_seconds: int) -> None:
    """Start a background loop that refreshes controls on a fixed interval."""
    global _policy_refresh_interval_seconds, _refresh_thread, _refresh_stop_event

    if interval_seconds <= 0:
        return

    stop_event = threading.Event()
    refresh_thread = threading.Thread(
        target=_policy_refresh_worker,
        args=(stop_event, interval_seconds),
        name="agent-control-policy-refresh",
        daemon=True,
    )
    with _refresh_lock:
        _policy_refresh_interval_seconds = interval_seconds
        _refresh_stop_event = stop_event
        _refresh_thread = refresh_thread

    refresh_thread.start()
    logger.info("Started policy refresh loop (interval=%ss)", interval_seconds)


async def refresh_controls_async() -> list[dict[str, Any]] | None:
    """Refresh controls from the server asynchronously.

    Fetches the latest controls from the server and updates the cache.
    Use this when you've made changes to controls in the UI or API
    and want the SDK to pick them up without restarting.

    Returns:
        List of control dicts or None if fetch failed.

    Example:
        # After updating a control in the UI
        controls = await agent_control.refresh_controls_async()
        print(f"Refreshed {len(controls)} controls")
    """
    context = _snapshot_refresh_context()
    try:
        controls = await _fetch_controls_for_context_async(context)
    except Exception as exc:
        logger.error(
            "Failed to refresh controls; keeping previous cache (%d control(s)): %s",
            len(state.server_controls or []),
            exc,
            exc_info=True,
        )
        return state.server_controls

    with _session_lock:
        if context.session_generation != _session_generation:
            logger.info(
                "Discarding stale control refresh result for superseded SDK session"
            )
            return state.server_controls

        refreshed_controls = _publish_server_controls(controls)

    if refreshed_controls is not None:
        logger.info("Refreshed %d control(s) from server", len(refreshed_controls or []))
    else:
        logger.info("Refreshed 0 control(s) from server")
    return refreshed_controls


def refresh_controls() -> list[dict[str, Any]] | None:
    """Refresh controls from the server synchronously.

    Fetches the latest controls from the server and updates the cache.
    Use this when you've made changes to controls in the UI or API
    and want the SDK to pick them up without restarting.

    Returns:
        List of control dicts or None if fetch failed.

    Example:
