"""
Centralized configuration for Agent Control SDK.

This module provides typed configuration via pydantic-settings, supporting:
- Environment variables with AGENT_CONTROL_ prefix
- Type coercion and validation
- Programmatic overrides

Usage:
    from agent_control.settings import settings

    # Access settings
    if settings.observability_enabled:
        send_events()

    # Settings are read from environment variables:
    # AGENT_CONTROL_URL, AGENT_CONTROL_OBSERVABILITY_ENABLED, etc.
"""

from typing import Any

from agent_control_models import JSONObject
from agent_control_telemetry import DEFAULT_CONTROL_EVENT_SINK_NAME
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SDKSettings(BaseSettings):
    """
    Configuration for Agent Control SDK.

    Includes settings for:
    - Server connection (url, api_key)
    - Observability/event batching
    - Logging verbosity

    All settings can be configured via environment variables with the
    AGENT_CONTROL_ prefix. For example:
        AGENT_CONTROL_URL=http://localhost:8000
        AGENT_CONTROL_OBSERVABILITY_ENABLED=true

    Settings can also be overridden programmatically via configure_settings().
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_CONTROL_",
        extra="ignore",
