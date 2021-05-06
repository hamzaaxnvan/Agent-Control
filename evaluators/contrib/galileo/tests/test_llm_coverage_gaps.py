"""Targeted tests filling coverage gaps in llm/evaluator.py and llm/client.py.

These tests cover the small utility functions and rare branches that the
integration-style tests in ``test_llm_evaluator.py`` skip past.
"""

from __future__ import annotations

import json
import os
from base64 import urlsafe_b64decode
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

LLM_ENV = {
    "GALILEO_API_SECRET_KEY": "test-secret",
    "GALILEO_LUNA_INVOKE_URL": "http://luna-invoke:8090",
    "GALILEO_FEATURE_FLAG_LLM_EVALUATOR": "enabled",
}

_EXTENSIONS = {
    "namespace_key": "org-1",
    "caller_id": "user-1",
    "target_type": "log_stream",
    "target_id": "run-1",
    "metadata": {},
}


def _make_invoke_kwargs() -> dict[str, object]:
    """Minimal required kwargs for GalileoLLMClient.invoke()."""
    from agent_control_models import Step

    from agent_control_evaluator_galileo.llm.client import GalileoExecutionContext

    return {
        "scorer_version_id": "ver-1",
        "step": Step(type="llm", name="test", input="prompt"),
        "execution_context": GalileoExecutionContext(organization_id="org-1"),
    }


def _decode_jwt_payload(token: str) -> dict[str, object]:
    payload_segment = token.split(".")[1]
    padded = payload_segment + ("=" * (-len(payload_segment) % 4))
    return json.loads(urlsafe_b64decode(padded.encode()).decode())


# =============================================================================
# llm/evaluator.py: utility helpers
# =============================================================================


class TestCoercePayloadText:
    """``_coerce_payload_text`` normalises arbitrary values to strings."""

    def test_none_returns_none(self):
        from agent_control_evaluator_galileo.llm.evaluator import _coerce_payload_text

        assert _coerce_payload_text(None) is None

    def test_string_passed_through(self):
        from agent_control_evaluator_galileo.llm.evaluator import _coerce_payload_text

        assert _coerce_payload_text("hello") == "hello"

    @pytest.mark.parametrize("value", [42, 3.14, True])
    def test_scalars_stringified(self, value):
        from agent_control_evaluator_galileo.llm.evaluator import _coerce_payload_text

        assert _coerce_payload_text(value) == str(value)

    def test_dict_is_json_serialized(self):
        from agent_control_evaluator_galileo.llm.evaluator import _coerce_payload_text

        result = _coerce_payload_text({"a": 1, "b": 2})

        assert json.loads(result) == {"a": 1, "b": 2}

    def test_unserialisable_falls_back_to_str(self):
        from agent_control_evaluator_galileo.llm.evaluator import _coerce_payload_text

        class CannotJson:
            def __repr__(self):
                return "<CannotJson>"

        cannot = CannotJson()
        result = _coerce_payload_text({"obj": cannot})

        # default=str converts the inner object, so we still get a JSON string.
        assert isinstance(result, str)


class TestExtractDictText:
    """``_extract_dict_text`` returns ``None`` for missing keys."""

    def test_missing_key_returns_none(self):
        from agent_control_evaluator_galileo.llm.evaluator import _extract_dict_text

        assert _extract_dict_text({}, "absent") is None

    def test_present_key_coerced(self):
        from agent_control_evaluator_galileo.llm.evaluator import _extract_dict_text

        assert _extract_dict_text({"x": 7}, "x") == "7"


class TestContains:
    """``_contains`` supports str/list and dict values against a threshold."""

    def test_none_threshold_is_no_match(self):
        from agent_control_evaluator_galileo.llm.evaluator import _contains

        assert _contains("anything", None) is False

    def test_string_contains_substring(self):
        from agent_control_evaluator_galileo.llm.evaluator import _contains

        assert _contains("hello world", "world") is True
        assert _contains("hello world", "absent") is False

    def test_list_contains_value(self):
        from agent_control_evaluator_galileo.llm.evaluator import _contains

        assert _contains(["a", "b", "c"], "b") is True
        assert _contains(["a", "b", "c"], "z") is False

    def test_dict_threshold_does_not_match_key(self):
        from agent_control_evaluator_galileo.llm.evaluator import _contains

        assert _contains({"toxicity": 0.9}, "toxicity") is False

    def test_dict_threshold_matches_value(self):
        from agent_control_evaluator_galileo.llm.evaluator import _contains

        assert _contains({"label": "flagged"}, "flagged") is True

    def test_other_types_return_false(self):
        from agent_control_evaluator_galileo.llm.evaluator import _contains

        assert _contains(42, 42) is False


class TestConfidenceFromScore:
    """``_confidence_from_score`` maps a raw score to [0, 1]."""

    def test_true_bool_maps_to_one(self):
        from agent_control_evaluator_galileo.llm.evaluator import _confidence_from_score

        assert _confidence_from_score(True) == 1.0

    def test_false_bool_maps_to_zero(self):
        from agent_control_evaluator_galileo.llm.evaluator import _confidence_from_score

        assert _confidence_from_score(False) == 0.0

    def test_in_range_number_returned_as_is(self):
        from agent_control_evaluator_galileo.llm.evaluator import _confidence_from_score

        assert _confidence_from_score(0.42) == 0.42

    def test_out_of_range_falls_back_to_one(self):
        from agent_control_evaluator_galileo.llm.evaluator import _confidence_from_score

        assert _confidence_from_score(7.2) == 1.0

    def test_non_numeric_falls_back_to_one(self):
        from agent_control_evaluator_galileo.llm.evaluator import _confidence_from_score

        assert _confidence_from_score("not-a-number") == 1.0


# =============================================================================
# llm/evaluator.py: _score_matches operator branches
# =============================================================================


@pytest.fixture
def llm_evaluator(monkeypatch):
    """A ready-to-use LlmEvaluator instance with auth env wired up."""
    for key, value in LLM_ENV.items():
        monkeypatch.setenv(key, value)
    from agent_control_evaluator_galileo.llm import LlmEvaluator

    return LlmEvaluator.from_dict(
        {"scorer_id": "scorer-123", "scorer_version_id": "ver-1", "threshold": 0.5, "operator": "gte"}
    )


class TestScoreMatchesOperators:
    """Every operator branch in ``_score_matches`` should evaluate."""

    def _make(self, operator, threshold, monkeypatch):
        for key, value in LLM_ENV.items():
            monkeypatch.setenv(key, value)
        from agent_control_evaluator_galileo.llm import LlmEvaluator

        return LlmEvaluator.from_dict(
            {"scorer_id": "scorer-123", "scorer_version_id": "ver-1", "threshold": threshold, "operator": operator}
        )

    def test_any_truthy_score_matches(self, monkeypatch):
        evaluator = self._make("any", 0.5, monkeypatch)
        assert evaluator._score_matches(1) is True
        assert evaluator._score_matches(0) is False

    def test_eq_matches_threshold(self, monkeypatch):
        evaluator = self._make("eq", "flagged", monkeypatch)
        assert evaluator._score_matches("flagged") is True
        assert evaluator._score_matches("safe") is False

    def test_ne_matches_when_different(self, monkeypatch):
        evaluator = self._make("ne", "flagged", monkeypatch)
        assert evaluator._score_matches("safe") is True
        assert evaluator._score_matches("flagged") is False

    def test_contains_matches_substring(self, monkeypatch):
        evaluator = self._make("contains", "flag", monkeypatch)
        assert evaluator._score_matches("flagged") is True
