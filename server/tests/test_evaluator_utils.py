"""Unit tests for evaluator_utils module."""

import pytest

from agent_control_server.services.evaluator_utils import (
    is_agent_scoped,
    parse_evaluator_ref_full,
    validate_config_against_schema,
)


class TestParseEvaluatorRefFull:
    """Tests for parse_evaluator_ref_full function (full three-way parsing)."""

    def test_builtin_evaluator(self) -> None:
        """Given a built-in evaluator, when parsing full, then type is builtin."""
        # When
        result = parse_evaluator_ref_full("regex")

        # Then
        assert result.type == "builtin"
        assert result.name == "regex"
        assert result.namespace is None
        assert result.local_name == "regex"

    def test_external_evaluator(self) -> None:
        """Given an external evaluator, when parsing full, then type is external."""
        # When
        result = parse_evaluator_ref_full("galileo.luna")

        # Then
        assert result.type == "external"
        assert result.name == "galileo.luna"
