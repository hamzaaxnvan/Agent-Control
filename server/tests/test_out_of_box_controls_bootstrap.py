from __future__ import annotations

import datetime as dt
import uuid
from copy import deepcopy
from types import SimpleNamespace
from typing import cast

import pytest
from agent_control_server.bootstrap import out_of_box_controls as bootstrap_module
from agent_control_server.bootstrap.out_of_box_controls import (
    OutOfBoxControlTemplate,
    OutOfBoxSeedResult,
    default_out_of_box_namespace_key,
    missing_required_evaluators,
    seed_out_of_box_controls,
)
from agent_control_server.models import (
    DEFAULT_NAMESPACE_KEY,
    Control,
    ControlBinding,
    ControlVersion,
    agent_controls,
    policy_controls,
)
from agent_control_server.services.controls import ControlService
from pydantic import ValidationError
from sqlalchemy import Table, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .conftest import AsyncSessionTest, engine


def _control_payload(*, evaluator_name: str = "regex") -> dict[str, object]:
    return {
        "description": "Synthetic out-of-box control",
        "enabled": True,
        "execution": "server",
        "scope": {"step_types": ["llm"], "stages": ["post"]},
        "condition": {
            "selector": {"path": "output"},
            "evaluator": {
                "name": evaluator_name,
                "config": {"pattern": r"\bsecret\b"},
            },
        },
        "action": {"decision": "deny"},
        "tags": ["out-of-box"],
    }


def _template(
    *,
    name: str | None = None,
    source_id: str | None = None,
    evaluator_name: str = "regex",
) -> OutOfBoxControlTemplate:
    template_name = name or f"oob-test-{uuid.uuid4().hex}"
    return OutOfBoxControlTemplate.from_payload(
        source_id=source_id or template_name,
        name=template_name,
        data=_control_payload(evaluator_name=evaluator_name),
    )


def _fetch_controls() -> list[Control]:
    with Session(engine) as session:
        return list(session.scalars(select(Control).order_by(Control.id)).all())


def _fetch_versions() -> list[ControlVersion]:
    with Session(engine) as session:
        return list(session.scalars(select(ControlVersion).order_by(ControlVersion.id)).all())


def _count_table_rows(table: Table) -> int:
    with Session(engine) as session:
        return cast(int, session.scalar(select(func.count()).select_from(table)))


def test_default_namespace_key_uses_standalone_namespace() -> None:
    assert default_out_of_box_namespace_key() == DEFAULT_NAMESPACE_KEY


def test_missing_required_evaluators_returns_sorted_names() -> None:
    missing = missing_required_evaluators(
        {"galileo.luna", "regex", "json"},
        {"json"},
    )

    assert missing == ("galileo.luna", "regex")


def test_seed_result_reports_created_and_skipped_counts() -> None:
    # Given: a result containing every skip category
    result = OutOfBoxSeedResult(
        created=("created-one", "created-two"),
        skipped_existing=("existing",),
        skipped_missing_evaluator=(
            bootstrap_module.SkippedOutOfBoxControl(
                name="missing",
                missing_evaluators=("regex",),
            ),
        ),
        skipped_conflict=("conflict",),
    )

    # When/Then: its summary counts include the corresponding entries
    assert result.created_count == 2
    assert result.skipped_count == 3


def test_template_from_payload_validates_control_definition() -> None:
    payload = deepcopy(_control_payload())
    payload["condition"] = {
        "selector": {"path": "invalid_root.value"},
        "evaluator": {"name": "regex", "config": {"pattern": "x"}},
    }

    with pytest.raises(ValidationError):
        OutOfBoxControlTemplate.from_payload(
            source_id="invalid-oob-control",
            name="invalid-oob-control",
            data=payload,
        )


@pytest.mark.asyncio
async def test_seed_empty_catalog_returns_without_opening_session() -> None:
    # Given: an empty catalog and a session factory that must not be used
    def unexpected_session_factory() -> None:
        raise AssertionError("empty catalog should not open a database session")

    # When: bootstrap runs with no templates
    result = await seed_out_of_box_controls(
        session_factory=unexpected_session_factory,  # type: ignore[arg-type]
        namespace_key=DEFAULT_NAMESPACE_KEY,
        available_evaluators={"regex"},
        templates=(),
    )

    # Then: it returns an empty result without touching the database
    assert result == OutOfBoxSeedResult()


@pytest.mark.asyncio
async def test_seed_skips_template_when_required_evaluator_is_missing() -> None:
