"""Tests for server configuration helpers."""

from agent_control_server.config import (
    AgentControlServerDatabaseConfig,
    LoggingSettings,
    ObservabilitySettings,
    Settings,
)


def test_db_config_prefers_explicit_url() -> None:
    # Given: a database config with an explicit URL set
    explicit_url = "sqlite:///tmp/test.db"
    config = AgentControlServerDatabaseConfig(url=explicit_url)

    # When: getting the database URL
    resolved = config.get_url()

    # Then: the explicit URL is returned
    assert resolved == explicit_url


def test_db_config_reads_agent_control_url_from_env(monkeypatch) -> None:
    # Given: the canonical database URL env var is set
    monkeypatch.setenv("AGENT_CONTROL_DB_URL", "sqlite:///tmp/canonical.db")

    # When: loading DB config from the environment
    config = AgentControlServerDatabaseConfig()

    # Then: the canonical Agent Control env var is used
    assert config.get_url() == "sqlite:///tmp/canonical.db"


def test_db_config_reads_database_url_from_env(monkeypatch) -> None:
    # Given: only the legacy DATABASE_URL env var is set
    monkeypatch.delenv("AGENT_CONTROL_DB_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/legacy.db")

    # When: loading DB config from the environment
    config = AgentControlServerDatabaseConfig()

    # Then: the legacy env var is still supported during migration
    assert config.get_url() == "sqlite:///tmp/legacy.db"


def test_db_config_reads_legacy_db_prefix_from_env(monkeypatch) -> None:
    # Given: only the legacy DB_* env vars are set
    monkeypatch.delenv("AGENT_CONTROL_DB_HOST", raising=False)
    monkeypatch.delenv("AGENT_CONTROL_DB_PORT", raising=False)
    monkeypatch.delenv("AGENT_CONTROL_DB_USER", raising=False)
    monkeypatch.delenv("AGENT_CONTROL_DB_PASSWORD", raising=False)
    monkeypatch.delenv("AGENT_CONTROL_DB_DATABASE", raising=False)
    monkeypatch.delenv("AGENT_CONTROL_DB_DRIVER", raising=False)
    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_PORT", "15432")
    monkeypatch.setenv("DB_USER", "legacy_user")
    monkeypatch.setenv("DB_PASSWORD", "legacy_password")
    monkeypatch.setenv("DB_DATABASE", "legacy_db")
    monkeypatch.setenv("DB_DRIVER", "psycopg")

    # When: loading DB config from the environment
    config = AgentControlServerDatabaseConfig()

    # Then: the legacy env vars remain compatible
    assert config.get_url() == "postgresql+psycopg://legacy_user:legacy_password@db.example:15432/legacy_db"


def test_db_config_prefers_agent_control_env_over_legacy(monkeypatch) -> None:
    # Given: both canonical and legacy database URLs are present
    monkeypatch.setenv("AGENT_CONTROL_DB_URL", "sqlite:///tmp/canonical.db")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/legacy.db")

    # When: loading DB config from the environment
    config = AgentControlServerDatabaseConfig()

    # Then: the canonical env var wins
    assert config.get_url() == "sqlite:///tmp/canonical.db"


def test_db_config_ignores_blank_agent_control_url_and_uses_legacy(monkeypatch) -> None:
    # Given: the canonical URL is blank but a legacy URL is still configured
    monkeypatch.setenv("AGENT_CONTROL_DB_URL", "")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/legacy.db")

    # When: loading DB config from the environment
    config = AgentControlServerDatabaseConfig()

    # Then: the blank canonical env var is ignored
    assert config.get_url() == "sqlite:///tmp/legacy.db"


def test_db_config_reads_pool_settings_from_env(monkeypatch) -> None:
    # Given: database pool settings are configured via environment variables
    monkeypatch.setenv("AGENT_CONTROL_DB_POOL_SIZE", "7")
    monkeypatch.setenv("AGENT_CONTROL_DB_MAX_OVERFLOW", "2")
    monkeypatch.setenv("AGENT_CONTROL_DB_POOL_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("AGENT_CONTROL_DB_CONNECT_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("AGENT_CONTROL_DB_STATEMENT_TIMEOUT_SECONDS", "2.5")

    # When: loading DB config from the environment
    config = AgentControlServerDatabaseConfig()
