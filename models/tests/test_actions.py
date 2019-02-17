"""Tests for shared control-action types, validation, and normalization."""

from __future__ import annotations

import pytest
from agent_control_models import (
    ControlAction,
    ControlExecutionEvent,
    ControlMatch,
    EventQueryRequest,
    EvaluatorResult,
    expand_action_filter,
)
from agent_control_models.actions import normalize_action, validate_action
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# validate_action (strict, for API boundaries)
# ---------------------------------------------------------------------------


class TestValidateAction:
    """Tests for the strict validate_action used on public API boundaries."""

    @pytest.mark.parametrize("action", ["deny", "steer", "observe"])
    def test_accepts_canonical_actions(self, action: str) -> None:
        # Given: a canonical action name
        # When: validating the action
        result = validate_action(action)

        # Then: the same canonical value is returned
        assert result == action

    @pytest.mark.parametrize("legacy", ["allow", "warn", "log"])
    def test_rejects_legacy_actions(self, legacy: str) -> None:
        # Given: a legacy action name that is no longer accepted at API boundaries
        # When / Then: validation raises ValueError
        with pytest.raises(ValueError, match="Invalid action"):
            validate_action(legacy)

    def test_rejects_unknown_action(self) -> None:
        # Given: a completely unknown action name
        # When / Then: validation raises ValueError
        with pytest.raises(ValueError, match="Invalid action"):
            validate_action("block")


# ---------------------------------------------------------------------------
# normalize_action (lenient, for internal read paths)
# ---------------------------------------------------------------------------


class TestNormalizeAction:
    """Tests for the lenient normalize_action used on read paths."""

    @pytest.mark.parametrize("action", ["deny", "steer", "observe"])
    def test_passes_canonical_actions(self, action: str) -> None:
        # Given: a canonical action name
        # When: normalizing
        result = normalize_action(action)

        # Then: the same value is returned unchanged
        assert result == action

    @pytest.mark.parametrize("legacy", ["allow", "warn", "log"])
    def test_normalizes_legacy_to_observe(self, legacy: str) -> None:
        # Given: a legacy advisory action stored in a historical DB row
        # When: normalizing on the read path
        result = normalize_action(legacy)

        # Then: it maps to the canonical "observe" action
        assert result == "observe"

    def test_rejects_unknown_action(self) -> None:
        # Given: a completely unknown action name
        # When / Then: normalization raises ValueError even on the lenient path
        with pytest.raises(ValueError, match="Invalid action"):
            normalize_action("block")


# ---------------------------------------------------------------------------
# ControlAction (API input boundary — strict)
# ---------------------------------------------------------------------------


class TestControlActionValidation:
    """ControlAction.decision uses strict validation (rejects legacy values)."""

    @pytest.mark.parametrize("action", ["deny", "steer", "observe"])
    def test_accepts_canonical_actions(self, action: str) -> None:
        # Given: a control action payload with a canonical decision
        # When: validating via Pydantic
        ca = ControlAction.model_validate({"decision": action})

        # Then: the decision is accepted as-is
        assert ca.decision == action

    @pytest.mark.parametrize("legacy", ["allow", "warn", "log"])
    def test_rejects_legacy_actions(self, legacy: str) -> None:
        # Given: a control action payload using a legacy decision value
        # When / Then: Pydantic validation rejects it at the API boundary
        with pytest.raises(ValidationError, match="Invalid action"):
            ControlAction.model_validate({"decision": legacy})

    def test_rejects_unknown_action(self) -> None:
        # Given: a control action payload with an unknown decision
        # When / Then: Pydantic validation rejects it
        with pytest.raises(ValidationError, match="Invalid action"):
            ControlAction.model_validate({"decision": "block"})


# ---------------------------------------------------------------------------
# EventQueryRequest.actions (API input boundary — strict)
# ---------------------------------------------------------------------------


class TestEventQueryRequestValidation:
    """EventQueryRequest.actions uses strict validation."""

    def test_accepts_canonical_actions(self) -> None:
        # Given: a query filter with all three canonical action values
        # When: constructing the query request
        query = EventQueryRequest(actions=["deny", "steer", "observe"])

