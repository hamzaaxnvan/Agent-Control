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
