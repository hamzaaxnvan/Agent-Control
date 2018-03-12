"""normalize legacy control condition payloads

Revision ID: 9f2f5a4e6c1b
Revises: 4b8c7d4a1f31
Create Date: 2026-03-17 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import context, op

# revision identifiers, used by Alembic.
revision = "9f2f5a4e6c1b"
down_revision = "4b8c7d4a1f31"
branch_labels = None
depends_on = None

_SAMPLE_LIMIT = 5
_JSON_OBJECT = "jsonb_typeof(data) = 'object'"
_JSON_NON_OBJECT = "jsonb_typeof(data) <> 'object'"
_HAS_CONDITION = "data ? 'condition'"
_HAS_SELECTOR = "data ? 'selector'"
_HAS_EVALUATOR = "data ? 'evaluator'"
_EMPTY_OBJECT = "data = '{}'::jsonb"
_LEGACY_VALID_PREDICATE = (
    f"{_JSON_OBJECT} AND NOT {_HAS_CONDITION} AND {_HAS_SELECTOR} AND {_HAS_EVALUATOR}"
)
_INVALID_BUCKET_PREDICATES: dict[str, str] = {
    "mixed_invalid": (
        f"{_JSON_OBJECT} AND {_HAS_CONDITION} AND ({_HAS_SELECTOR} OR {_HAS_EVALUATOR})"
    ),
    "partial_invalid": (
        f"{_JSON_OBJECT} AND NOT {_HAS_CONDITION} AND "
        f"(({_HAS_SELECTOR} AND NOT {_HAS_EVALUATOR}) OR "
        f"({_HAS_EVALUATOR} AND NOT {_HAS_SELECTOR}))"
    ),
    "missing_condition_invalid": (
        f"{_JSON_OBJECT} AND NOT {_EMPTY_OBJECT} AND NOT {_HAS_CONDITION} "
        f"AND NOT {_HAS_SELECTOR} AND NOT {_HAS_EVALUATOR}"
    ),
    "non_object_invalid": _JSON_NON_OBJECT,
}


def _count_rows(bind: sa.engine.Connection, predicate: str) -> int:
    return int(
        bind.execute(
            sa.text(f"SELECT COUNT(*) FROM controls WHERE {predicate}")
        ).scalar_one()
    )


def _sample_rows(bind: sa.engine.Connection, predicate: str) -> list[str]:
    rows = (
        bind.execute(
            sa.text(
                f"""
                SELECT id, name
                FROM controls
