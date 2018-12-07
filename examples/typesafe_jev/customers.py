"""A synthetic customer table for the demo bank, and the lookup tool over it.

Every row is invented. Do not put real customer data here, and do not point
this at a real database. The table exists so the assistant has a capability
worth guarding: without it, a control that blocks a bulk export blocks
something the agent could never have done.

The table is deliberately small. It only has to make the tool real.
"""

from __future__ import annotations

from typing import Any

#: The fields a row can carry. The identifying ones are what the bulk-export
#: control cares about; the rest are ordinary reporting columns.
FIELDS: tuple[str, ...] = (
    "account_id",
    "name",
    "email",
    "phone",
    "address",
    "region",
    "account_type",
    "balance",
    "ssn",
    "card",
)

#: The customer the chat window is talking to. The assistant is told who this
#: is, so a support question about "my account" resolves without a search.
CURRENT_CUSTOMER = "Jane Doe"

CUSTOMERS: tuple[dict[str, Any], ...] = (
    {
        "account_id": "NB-1001",
