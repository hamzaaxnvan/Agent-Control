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
