"""Main server application entry point."""

import asyncio
import inspect
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from agent_control_engine import discover_evaluators, list_evaluators
from agent_control_models import HealthResponse
from agent_control_telemetry import DEFAULT_CONTROL_EVENT_SINK_NAME, ControlEventSinkSelection
from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette_exporter import PrometheusMiddleware, handle_metrics

from . import __version__ as server_version
from .auth import get_api_key_from_header
from .bootstrap.out_of_box_controls import (
    default_out_of_box_namespace_key,
    seed_out_of_box_controls,
)
from .config import observability_settings, settings
from .db import AsyncSessionLocal, async_engine
from .endpoints.agents import router as agent_router
from .endpoints.auth import router as auth_router
from .endpoints.control_bindings import router as control_binding_router
from .endpoints.controls import router as control_router
from .endpoints.controls import template_router as control_template_router
from .endpoints.evaluation import router as evaluation_router
from .endpoints.evaluators import router as evaluator_router
from .endpoints.observability import router as observability_router
from .endpoints.policies import router as policy_router
from .endpoints.system import router as system_router
from .errors import (
    APIError,
    api_error_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from .logging_utils import (
    access_log_enabled,
    configure_logging,
    get_uvicorn_log_level_name,
    should_configure_logging,
)
from .observability.ingest import DirectEventIngestor
from .observability.sinks import (
    EventStoreControlEventSink,
    ResolvedControlEventBackend,
    resolve_control_event_backend,
)
from .observability.store import PostgresEventStore
from .ui_assets import configure_ui_routes

logger = logging.getLogger(__name__)
_logging_configured = False

METRICS_PATH = "/metrics"
PROMETHEUS_BUCKETS = [
    0.1,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    30.0,
    60.0,
    float("inf"),
]
PROMETHEUS_SKIP_PATHS = [
    METRICS_PATH,
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
]


def _default_log_level() -> str:
    return "DEBUG" if settings.debug else "INFO"


def _configure_logging_once() -> None:
    global _logging_configured

    if _logging_configured or not should_configure_logging():
        return

    configure_logging(default_level=_default_log_level())
    _logging_configured = True


def add_prometheus_metrics(app: FastAPI, metrics_prefix: str) -> None:
    """Configure Prometheus metrics for the FastAPI app."""
    app.add_middleware(
        PrometheusMiddleware,
        app_name="agent-control-server",
        prefix=metrics_prefix,
        group_paths=True,
        filter_unhandled_paths=True,
        buckets=PROMETHEUS_BUCKETS,
        skip_paths=PROMETHEUS_SKIP_PATHS,
    )
    app.add_route(METRICS_PATH, handle_metrics)


async def _shutdown_observability_sink(sink: object) -> None:
    """Flush and close a custom async sink when it exposes lifecycle hooks."""
    flush = getattr(sink, "flush", None)
    if callable(flush):
        try:
            result = flush()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.warning("Observability sink flush failed during shutdown", exc_info=True)

    for method_name in ("close", "shutdown"):
        callback = getattr(sink, method_name, None)
        if not callable(callback):
            continue
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.warning(
                "Observability sink %s failed during shutdown",
                method_name,
                exc_info=True,
            )
        return


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for FastAPI app startup and shutdown."""
    _configure_logging_once()

    # Install the request-auth provider selected by environment variables.
    from .auth_framework.config import configure_auth_from_env

    configure_auth_from_env()

    # Discover evaluators at startup
    discover_evaluators()
    available = list(list_evaluators().keys())
    logger.info(f"Evaluator discovery complete. Available evaluators: {available}")

    try:
        async with asyncio.timeout(settings.out_of_box_bootstrap_timeout_seconds):
            seed_result = await seed_out_of_box_controls(
                session_factory=AsyncSessionLocal,
                namespace_key=default_out_of_box_namespace_key(),
                available_evaluators=set(available),
            )
        if seed_result.created_count or seed_result.skipped_count:
            logger.info(
                "Out-of-box control bootstrap complete: created=%s "
                "skipped_existing=%s skipped_missing_evaluator=%s skipped_conflict=%s",
                seed_result.created_count,
                len(seed_result.skipped_existing),
                len(seed_result.skipped_missing_evaluator),
                len(seed_result.skipped_conflict),
            )
    except TimeoutError:
        logger.warning(
            "Out-of-box control bootstrap timed out after %s seconds; continuing startup",
            settings.out_of_box_bootstrap_timeout_seconds,
        )
    except Exception:
        logger.warning("Out-of-box control bootstrap failed; continuing startup", exc_info=True)

    # Initialize observability components (stored on app.state)
    if observability_settings.enabled:
        logger.info("Initializing observability components...")

        # 1. Resolve the active sink from shared sink-selection config
        sink_selection = ControlEventSinkSelection(
            name=observability_settings.sink_name,
            config=observability_settings.sink_config,
        )
        default_backend: ResolvedControlEventBackend | None = None
        if sink_selection.name == DEFAULT_CONTROL_EVENT_SINK_NAME:
            store = PostgresEventStore(AsyncSessionLocal)
            default_backend = ResolvedControlEventBackend(
                sink=EventStoreControlEventSink(store),
                event_store=store,
            )
            logger.info("PostgresEventStore initialized")

        backend = resolve_control_event_backend(
            sink_selection,
            default_backend=default_backend,
        )
        app.state.event_store = backend.event_store
        app.state.event_sink = backend.sink

        # 2. Create event ingestor
        ingestor = DirectEventIngestor(
            store=backend.sink,
            log_to_stdout=observability_settings.stdout,
        )
        app.state.event_ingestor = ingestor
        logger.info(
            "DirectEventIngestor initialized (stdout=%s, sink=%s)",
            observability_settings.stdout,
            sink_selection.name,
        )

        logger.info("Observability initialization complete")

    yield

    # Shutdown: release auth provider resources (e.g., upstream HTTP clients)
    from .auth_framework.config import teardown_auth

    await teardown_auth()

    # Shutdown: Clean up observability
    if observability_settings.enabled and hasattr(app.state, "event_store"):
        logger.info("Shutting down observability components...")
        sink = getattr(app.state, "event_sink", None)
        if sink is not None:
            await _shutdown_observability_sink(sink)
        if sink is None or sink is not app.state.event_store:
