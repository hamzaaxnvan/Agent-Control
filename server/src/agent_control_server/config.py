"""Server configuration settings."""

import logging
import secrets
from functools import cached_property
from typing import Any

from agent_control_models import JSONObject
from agent_control_telemetry import DEFAULT_CONTROL_EVENT_SINK_NAME
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_config_logger = logging.getLogger(__name__)

_COMMON_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    env_ignore_empty=True,
    extra="ignore",
    populate_by_name=True,
)


def _env_alias_field(default: Any, *env_names: str) -> Any:
    """Create a field that accepts multiple environment variable names."""
    return Field(default=default, validation_alias=AliasChoices(*env_names))


class AuthSettings(BaseSettings):
    """Authentication configuration for API key validation."""

    model_config = SettingsConfigDict(**_COMMON_SETTINGS_CONFIG, env_prefix="AGENT_CONTROL_")

    # Master toggle for authentication (disabled by default for local development)
    # Enable in production: AGENT_CONTROL_API_KEY_ENABLED=true
    api_key_enabled: bool = False

    # API keys (comma-separated list supports multiple keys for rotation)
    # Env: AGENT_CONTROL_API_KEYS="key1,key2,key3"
    api_keys: str = ""

    # Admin API keys (subset with elevated privileges)
    # Env: AGENT_CONTROL_ADMIN_API_KEYS="admin-key1,admin-key2"
    admin_api_keys: str = ""

    # Secret for signing session JWTs.
    # Env: AGENT_CONTROL_SESSION_SECRET="<random-string>"
    # If unset, a random secret is generated at startup (sessions won't survive
    # restarts or work across multiple server instances).
    session_secret: str = ""

    @cached_property
    def _parsed_api_keys(self) -> set[str]:
        """Parse and cache API keys from comma-separated string."""
        if not self.api_keys:
            return set()
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @cached_property
    def _parsed_admin_api_keys(self) -> set[str]:
        """Parse and cache admin API keys from comma-separated string."""
        if not self.admin_api_keys:
            return set()
        return {k.strip() for k in self.admin_api_keys.split(",") if k.strip()}

    @cached_property
    def _all_valid_keys(self) -> set[str]:
        """Cache the union of all valid keys for fast lookup."""
        return self._parsed_api_keys | self._parsed_admin_api_keys

    def get_api_keys(self) -> set[str]:
        """Get parsed API keys (cached)."""
        return self._parsed_api_keys

    def get_admin_api_keys(self) -> set[str]:
