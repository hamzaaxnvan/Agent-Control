import json
import logging

from .config import LoggingSettings

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}
_UVICORN_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE"}
_UPSTREAM_DIAGNOSTIC_FIELDS = (
    "operation",
    "status_code",
    "target_context",
    "upstream_validation",
    "upstream_validation_total",
    "upstream_validation_status",
)


class _JsonLogFormatter(logging.Formatter):
    """Render log messages and approved upstream diagnostics as valid JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        for field in _UPSTREAM_DIAGNOSTIC_FIELDS:
            if field in record.__dict__:
                payload[field] = record.__dict__[field]
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str)


def _normalize_level_name(level: str | None) -> str | None:
    if level is None:
        return None
    normalized = level.upper()
    if normalized in _LEVELS:
        return normalized
    return None


def _configured_level_name() -> str | None:
    return _normalize_level_name(LoggingSettings().level)


def _parse_level(level: str | int | None) -> int:
    if isinstance(level, int):
        return level
    normalized = _normalize_level_name(level)
    if normalized is not None:
        return _LEVELS[normalized]
    configured_level = _configured_level_name()
    if configured_level is not None:
        return _LEVELS[configured_level]
    return logging.INFO


def get_log_level_name(default_level: str = "INFO") -> str:
    """Resolve the configured log level name, falling back to the provided default."""
    configured_level = _configured_level_name()
    if configured_level is not None:
        return configured_level
    normalized_default = _normalize_level_name(default_level)
    if normalized_default is not None:
        return normalized_default
    return "INFO"


def get_uvicorn_log_level_name(default_level: str = "INFO") -> str:
    """Resolve a uvicorn-compatible log level name."""
    normalized_level = get_log_level_name(default_level)
    if normalized_level in _UVICORN_LEVELS:
        return normalized_level
    normalized_default = _normalize_level_name(default_level)
    if normalized_default in _UVICORN_LEVELS:
        return normalized_default
    return "INFO"


def _parse_json(json_flag: bool | None) -> bool:
    if isinstance(json_flag, bool):
        return json_flag
    return LoggingSettings().json_logs


