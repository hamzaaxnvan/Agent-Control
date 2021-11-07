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
