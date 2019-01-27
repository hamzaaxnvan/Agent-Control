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
            if isinstance(dict_text, str) and dict_text:
                chunks.append(dict_text)
                continue
            json_value = part.get("json")
            if json_value is not None:
                chunks.append(_json_dumps(json_value))

    return "\n".join(chunks).strip()


def _extract_structured_part(part: Any) -> str | None:
    """Serialize non-text ADK part payloads that controls may still need to inspect."""

    structured_fields = (
        "function_call",
        "function_response",
        "executable_code",
        "code_execution_result",
    )
    for field_name in structured_fields:
        value = part.get(field_name) if isinstance(part, dict) else getattr(part, field_name, None)
        if value is not None:
            return _json_dumps(_to_jsonable(value))

    return None


def _to_jsonable(value: Any) -> Any:
    """Convert ADK/genai payload objects into JSON-serializable structures."""

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")

    if isinstance(value, dict | list | str | int | float | bool) or value is None:
        return value

    value_dict = getattr(value, "__dict__", None)
    if isinstance(value_dict, dict):
        return value_dict

    return str(value)


def _json_dumps(value: Any) -> str:
    """Serialize structured content deterministically for evaluator input."""

    return json.dumps(value, sort_keys=True)


def extract_request_text(llm_request: Any) -> str:
    """Extract the most recent text payload from an ADK LLM request."""

    contents = getattr(llm_request, "contents", None)
    if not isinstance(contents, list) or not contents:
        return ""
    last_content = contents[-1]
    return _extract_text_from_parts(getattr(last_content, "parts", None))


def extract_response_text(llm_response: Any) -> str:
    """Extract text from an ADK LLM response."""

    content = getattr(llm_response, "content", None)
    if content is None:
        return ""
    return _extract_text_from_parts(getattr(content, "parts", None))


def resolve_agent_name(callback_context: Any) -> str:
    """Resolve the currently executing ADK agent name."""

    callback_agent = getattr(callback_context, "agent", None)
