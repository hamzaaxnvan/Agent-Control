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
        """Get parsed admin API keys (cached)."""
        return self._parsed_admin_api_keys

    def is_valid_api_key(self, key: str) -> bool:
        """Check if key is a valid API key (regular or admin). O(1) lookup."""
        return key in self._all_valid_keys

    def is_admin_api_key(self, key: str) -> bool:
        """Check if key is an admin API key. O(1) lookup."""
        return key in self._parsed_admin_api_keys

    @cached_property
    def _resolved_session_secret(self) -> str:
        """Resolve session secret, generating an ephemeral one if not configured."""
        if self.session_secret:
            return self.session_secret
        _config_logger.warning(
            "AGENT_CONTROL_SESSION_SECRET is not set. Using an ephemeral random secret. "
            "Sessions will not survive server restarts or work across multiple instances. "
            "Set AGENT_CONTROL_SESSION_SECRET for production deployments."
        )
        return secrets.token_urlsafe(32)

    def get_session_secret(self) -> str:
        """Get the JWT signing secret (cached)."""
        return self._resolved_session_secret


class AgentControlServerDatabaseConfig(BaseSettings):
    """Database configuration for the server."""

    model_config = SettingsConfigDict(**_COMMON_SETTINGS_CONFIG, env_prefix="AGENT_CONTROL_DB_")

    # Allow direct URL override for SQLite in local dev
    url: str | None = _env_alias_field(None, "AGENT_CONTROL_DB_URL", "DATABASE_URL", "DB_URL")

    # PostgreSQL settings (only used if url is not set)
    host: str = _env_alias_field("localhost", "AGENT_CONTROL_DB_HOST", "DB_HOST")
    port: int = _env_alias_field(5432, "AGENT_CONTROL_DB_PORT", "DB_PORT")
    user: str = _env_alias_field("agent_control", "AGENT_CONTROL_DB_USER", "DB_USER")
    password: str = _env_alias_field(
        "agent_control",
        "AGENT_CONTROL_DB_PASSWORD",
        "DB_PASSWORD",
    )
    database: str = _env_alias_field(
        "agent_control",
        "AGENT_CONTROL_DB_DATABASE",
        "DB_DATABASE",
    )
    driver: str = _env_alias_field("psycopg", "AGENT_CONTROL_DB_DRIVER", "DB_DRIVER")
    pool_size: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("AGENT_CONTROL_DB_POOL_SIZE", "DB_POOL_SIZE"),
    )
    max_overflow: int = Field(
        default=10,
        ge=0,
        validation_alias=AliasChoices("AGENT_CONTROL_DB_MAX_OVERFLOW", "DB_MAX_OVERFLOW"),
    )
    pool_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        validation_alias=AliasChoices(
            "AGENT_CONTROL_DB_POOL_TIMEOUT_SECONDS",
            "DB_POOL_TIMEOUT_SECONDS",
        ),
    )
    connect_timeout_seconds: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices(
            "AGENT_CONTROL_DB_CONNECT_TIMEOUT_SECONDS",
            "DB_CONNECT_TIMEOUT_SECONDS",
        ),
    )
