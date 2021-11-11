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
