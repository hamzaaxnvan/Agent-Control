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
        "name": "Jane Doe",
        "email": "jane.doe@example.com",
        "phone": "617-555-0142",
        "address": "42 Elm Street, Boston MA 02118",
        "region": "Northeast",
        "account_type": "checking",
        "balance": 2841.55,
        "ssn": "123-45-6789",
        "card": "4111 1111 1111 1111",
    },
    {
        "account_id": "NB-1002",
        "name": "Marcus Hale",
        "email": "m.hale@example.com",
        "phone": "617-555-0198",
        "address": "9 Pearl Court, Providence RI 02903",
        "region": "Northeast",
        "account_type": "savings",
        "balance": 15230.00,
        "ssn": "234-56-7890",
        "card": "4111 2222 2222 2222",
    },
    {
        "account_id": "NB-1003",
        "name": "Priya Raman",
        "email": "priya.r@example.com",
        "phone": "212-555-0177",
        "address": "88 Hudson Lane, New York NY 10013",
        "region": "Northeast",
        "account_type": "checking",
        "balance": 640.12,
        "ssn": "345-67-8901",
        "card": "4111 3333 3333 3333",
    },
    {
        "account_id": "NB-2001",
        "name": "Dana Whitfield",
