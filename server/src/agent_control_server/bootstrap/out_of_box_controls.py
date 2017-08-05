"""Startup bootstrap for out-of-box controls.

Phase 1 provides the tooling needed to seed controls safely, but does not
register the static out-of-box control catalog yet. Phase 2 should add those
definitions to ``OUT_OF_BOX_CONTROL_TEMPLATES``.

Namespace rule:
- Standalone Agent Control seeds into ``DEFAULT_NAMESPACE_KEY``.
- Galileo-integrated Agent Control should call the same helper with
  ``namespace_key`` set to the Galileo ``organization_id`` carried by the
  upstream auth bridge.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Self, cast

from agent_control_models import ControlDefinition
from agent_control_models.server import SlugName
from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models import DEFAULT_NAMESPACE_KEY
from ..services.controls import ControlService

_CONTROL_NAME_UNIQUE_CONSTRAINTS = frozenset(
    {
        "controls_name_key",
        "idx_controls_name_active",
        "idx_controls_namespace_name_active",
    }
)
_CONTROL_SEED_UNIQUE_CONSTRAINT = "idx_controls_namespace_seed_source"
_INITIAL_VERSION_NOTE = "Out-of-box control seed"
_SLUG_NAME_ADAPTER = TypeAdapter(SlugName)


@dataclass(frozen=True, slots=True)
class OutOfBoxControlTemplate:
    """Validated control definition plus the evaluator names it needs."""

    source_id: str
    name: str
    control: ControlDefinition
    required_evaluators: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _SLUG_NAME_ADAPTER.validate_python(self.source_id))
        object.__setattr__(self, "name", _SLUG_NAME_ADAPTER.validate_python(self.name))
        condition_evaluators = {
            evaluator.name for _, evaluator in self.control.iter_condition_leaf_parts()
        }
        object.__setattr__(
            self,
            "required_evaluators",
            frozenset(self.required_evaluators).union(condition_evaluators),
        )

    @classmethod
    def from_payload(
        cls,
        *,
        source_id: str,
        name: str,
        data: Mapping[str, object],
        required_evaluators: Collection[str] = frozenset(),
    ) -> Self:
        """Build a template from raw JSON-like data and validate it immediately."""
        return cls(
            source_id=source_id,
            name=name,
            control=ControlDefinition.model_validate(data),
            required_evaluators=frozenset(required_evaluators),
        )


@dataclass(frozen=True, slots=True)
class SkippedOutOfBoxControl:
    """A control skipped because the current pod cannot evaluate it."""

    name: str
    missing_evaluators: tuple[str, ...]

