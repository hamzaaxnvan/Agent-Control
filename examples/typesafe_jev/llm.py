"""A very small LLM client for the chat demo.

Three providers, picked from the environment so the demo runs with whatever
you have. Standard library only, so there is nothing to install.

    LLM_GATEWAY_URL     calls any OpenAI-compatible endpoint, with optional
                        OAuth2 client-credentials auth. Covers corporate
                        gateways and Azure-style deployments.
    OPENAI_API_KEY      calls OpenAI, matching the other examples in this repo
    ANTHROPIC_API_KEY   calls Anthropic
    none of those       a scripted offline model, so the guardrail flow still
                        demos without a key

The offline model deliberately answers one question unsafely, so the
output-side control has something to catch.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, NamedTuple

import customers
import env_file

# These constants read the environment at import time, so the .env has to be
# loaded before them. Doing it here means import order in the callers does not
# matter.
env_file.load()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

# An OpenAI-compatible endpoint. {model} is substituted if the URL contains it,
# which is how Azure-style deployment paths work.
GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "")
GATEWAY_MODEL = os.getenv("LLM_MODEL", "")
# Header carrying the credential. OpenAI uses "Authorization"; many gateways
# use "api-key".
GATEWAY_AUTH_HEADER = os.getenv("LLM_AUTH_HEADER", "api-key")
GATEWAY_AUTH_PREFIX = os.getenv("LLM_AUTH_PREFIX", "")
# Either a static key, or OAuth2 client credentials exchanged for a token.
GATEWAY_API_KEY = os.getenv("LLM_API_KEY", "")
GATEWAY_TOKEN_URL = os.getenv("LLM_TOKEN_URL", "")
GATEWAY_CLIENT_ID = os.getenv("LLM_CLIENT_ID", "")
GATEWAY_CLIENT_SECRET = os.getenv("LLM_CLIENT_SECRET", "")
# Extra JSON merged into the request body, for gateways that require their own
# fields such as an application key.
GATEWAY_EXTRA_BODY = os.getenv("LLM_EXTRA_BODY", "")

# An exchanged token is reused until shortly before it expires.
_gateway_token: tuple[str, float] | None = None
_gateway_lock = threading.Lock()

SYSTEM_PROMPT = (
    "You are a support assistant for Northwind Bank, a consumer bank. Answer "
    "briefly and plainly.\n\n"
    "You can read the bank's customer database with the lookup_customers tool. "
    "Use it whenever you need customer data, and never invent customer data. "
    "The person you are chatting with is "
    f"{customers.CURRENT_CUSTOMER}, account NB-1001.\n\n"
    "Answer the question the user actually asked, using the fields you "
    "retrieved."
)

#: The one tool the assistant has. The bulk-export control screens calls to it,
#: which is only meaningful because the tool will really answer them.
LOOKUP_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "lookup_customers",
        "description": "Read customer records from Northwind Bank's customer database.",
        "parameters": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Fields to return. One or more of: account_id, name, email, "
                        "phone, address, region, account_type, balance, ssn, card."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Return only the customer with this name.",
                },
                "region": {
                    "type": "string",
                    "description": (
                        "Return only customers in this region: Northeast, Southeast, "
                        "Midwest, or West. Use 'all' for every region."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return. Omit for no limit.",
                },
            },
            "required": ["fields"],
        },
    },
}


class ToolCall(NamedTuple):
    """One tool call the model asked for.

    Attributes:
        id: The provider's identifier, needed to return the result.
        name: The tool name.
        arguments: The decoded arguments. This is what a control screens.
    """

    id: str
    name: str
    arguments: dict[str, Any]


class Turn(NamedTuple):
    """One model response: either text, or tool calls, or both.

    Attributes:
        text: The assistant's text. Empty when it only asked for tools.
        tool_calls: The tool calls it asked for. Empty when it answered.
    """

    text: str
    tool_calls: list[ToolCall]


class PlatformRefusedError(Exception):
    """The model platform refused the prompt before the model saw it.

    Hosted models often sit behind their own content filter. A refusal there
    is not an application error: the platform simply will not engage with the
    text. It is reported separately so a guardrail decision is not confused
    with an outage.
    """

    def __init__(self, reason: str, categories: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.categories = categories or {}


def _raise_if_filtered(error: urllib.error.HTTPError) -> None:
    """Convert a platform content-filter rejection into PlatformRefusedError."""
    if error.code != 400:
        return
    try:
        body = json.loads(error.read().decode(errors="replace"))
    except Exception:
        return
    detail = body.get("error") or {}
    if detail.get("code") != "content_filter":
        return
    results = (detail.get("innererror") or {}).get("content_filter_result") or {}
    tripped = {
        name: info.get("severity")
        for name, info in results.items()
        if isinstance(info, dict) and info.get("filtered")
    }
    raise PlatformRefusedError(detail.get("message", "content filtered"), tripped)


def provider() -> str:
    """Return which provider this process will use."""
    if GATEWAY_URL:
        return "gateway"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "offline"
