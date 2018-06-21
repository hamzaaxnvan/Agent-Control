"""Google ADK extraction helpers for Agent Control."""

from __future__ import annotations

import json
from typing import Any, cast

try:
    from google.genai import types  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - optional dependency
    raise RuntimeError(
        "Google ADK integration requires google-adk. "
        "Install with: agent-control-sdk[google-adk]."
    ) from exc


def _extract_text_from_parts(parts: Any) -> str:
    """Extract text blocks from an ADK parts collection."""

    if not isinstance(parts, list):
        return ""

    chunks: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if isinstance(text, str) and text:
            chunks.append(text)
            continue

        structured = _extract_structured_part(part)
        if structured is not None:
            chunks.append(structured)
            continue

        if isinstance(part, dict):
            dict_text = part.get("text")
