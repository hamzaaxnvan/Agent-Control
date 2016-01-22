"""Normalize Agent Control values for canonical Galileo record fields."""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from galileo_core.schemas.logging.llm import Message
from galileo_core.schemas.shared.content_parts import ContentPart, FileContentPart, TextContentPart
from galileo_core.schemas.shared.document import Document
from pydantic import BaseModel, TypeAdapter, ValidationError

_CONTENT_PART_ADAPTER: TypeAdapter[ContentPart] = TypeAdapter(ContentPart)
_MAX_SAFE_INTEGER = 2**53 - 1


class _GalileoJSONEncoder(json.JSONEncoder):
    """Serialize values using the stable subset of Splunk AO's JSON behavior."""

    def default(self, value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(
                mode="json",
                exclude_none=True,
                exclude_unset=True,
                exclude_defaults=True,
            )
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.astimezone()
            serialized = value.isoformat()
            if value.tzinfo is not None and value.tzinfo.tzname(None) == UTC.tzname(None):
                return serialized.replace("+00:00", "Z")
            return serialized
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, UUID | Path):
            return str(value)
        if isinstance(value, Enum):
            return _sdk_json_value(value.value)
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return "<not serializable bytes>"
        if is_dataclass(value) and not isinstance(value, type):
            return asdict(value)
        if isinstance(value, set | frozenset):
            return list(value)
        return f"<{type(value).__name__}>"


def _sdk_json_value(value: Any, *, active: set[int] | None = None) -> Any:
    """Apply SDK-compatible conversion recursively, including mapping keys."""
    if value is None or isinstance(value, str | bool | float):
        return value
    if isinstance(value, int):
        return value if -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER else str(value)
    if isinstance(value, UUID | Path):
        return str(value)
    if isinstance(value, datetime):
        return _GalileoJSONEncoder().default(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _sdk_json_value(value.value, active=active)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return "<not serializable bytes>"

    seen = active if active is not None else set()
    value_id = id(value)
    if value_id in seen:
        return type(value).__name__
    seen.add(value_id)
    try:
        if isinstance(value, BaseModel):
            return _sdk_json_value(
                value.model_dump(
                    mode="json",
                    exclude_none=True,
                    exclude_unset=True,
                    exclude_defaults=True,
                ),
                active=seen,
            )
        if is_dataclass(value) and not isinstance(value, type):
            return _sdk_json_value(asdict(value), active=seen)
        if isinstance(value, Mapping):
            return {
                _sdk_json_value(key, active=seen): _sdk_json_value(item, active=seen)
                for key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            return [_sdk_json_value(item, active=seen) for item in value]
        if isinstance(value, set | frozenset):
            return [_sdk_json_value(item, active=seen) for item in value]
        if hasattr(value, "__slots__") and value.__slots__:
            return _sdk_json_value(
                {slot: getattr(value, slot, None) for slot in value.__slots__}, active=seen
            )
        if hasattr(value, "__dict__"):
            return _sdk_json_value(
                {key: item for key, item in vars(value).items() if not key.startswith("_")},
                active=seen,
            )
        return f"<{type(value).__name__}>"
    finally:
        seen.discard(value_id)


def _json_text(value: Any) -> str:
    """Return the Galileo text representation of a structured value."""
    if isinstance(value, str):
        return value
    return json.dumps(_sdk_json_value(value))


def _json_compatible(value: Any) -> Any:
    """Convert models and containers into values accepted by Galileo Pydantic models."""
    if isinstance(value, BaseModel):
        return _json_compatible(value.model_dump(mode="python", exclude_none=True))
    if isinstance(value, Mapping):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_compatible(item) for item in value]
    if isinstance(value, set | frozenset):
        return [_json_compatible(item) for item in value]
    if isinstance(value, UUID | datetime | date | Enum | Path | bytes):
        return _GalileoJSONEncoder().default(value)
    return value


def _content_part(value: Any) -> dict[str, Any] | None:
    """Validate and serialize a public Galileo text or file content part."""
    if isinstance(value, (TextContentPart, FileContentPart)):
        return value.model_dump(mode="json", exclude_none=True)
    if not isinstance(value, Mapping):
        return None
    try:
        part = _CONTENT_PART_ADAPTER.validate_python(dict(value))
    except ValidationError:
        return None
    return part.model_dump(mode="json", exclude_none=True)


def _message_content(value: Any) -> Any:
    if isinstance(value, Message):
        return value.content
    if isinstance(value, Mapping) and "role" in value:
        return value.get("content", "")
    return None


def _normalize_content_items(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return None
    normalized: list[dict[str, Any]] = []
    for item in value:
        block = _content_part(item)
        if block is None:
            return None
        normalized.append(block)
    return normalized


def _message_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray) and all(
        isinstance(item, Message)
        or (isinstance(item, Mapping) and "role" in item)
        for item in value
    )


def _llm_message_sequence(value: Any) -> Sequence[Any] | None:
    """Extract a role-bearing LLM message list from structured or string input."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (RecursionError, ValueError):
            try:
                parsed = ast.literal_eval(value)
            except (SyntaxError, ValueError, TypeError, RecursionError):
                return None
        if isinstance(parsed, Mapping):
            candidates = parsed.get("messages")
            if not isinstance(candidates, list):
                return None
        elif isinstance(parsed, list):
            candidates = parsed
        else:
            return None
