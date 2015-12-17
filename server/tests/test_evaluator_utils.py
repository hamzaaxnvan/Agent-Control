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
        assert result.namespace == "galileo"
        assert result.local_name == "luna"

    def test_agent_scoped_evaluator(self) -> None:
        """Given an agent-scoped evaluator, when parsing full, then type is agent."""
        # When
        result = parse_evaluator_ref_full("my-agent:pii-detector")

        # Then
        assert result.type == "agent"
        assert result.name == "my-agent:pii-detector"
        assert result.namespace == "my-agent"
        assert result.local_name == "pii-detector"

    def test_external_with_nested_path(self) -> None:
        """Given an external evaluator with nested path, when parsing, splits on first dot."""
        # When
        result = parse_evaluator_ref_full("acme.safety.toxicity")

        # Then
        assert result.type == "external"
        assert result.namespace == "acme"
        assert result.local_name == "safety.toxicity"

    def test_agent_scoped_with_dot_in_name(self) -> None:
        """Given agent-scoped with dot in name, when parsing, then colon takes precedence."""
        # When - colon should be detected before dot
        result = parse_evaluator_ref_full("my-agent:vendor.eval")

        # Then
        assert result.type == "agent"
        assert result.namespace == "my-agent"
        assert result.local_name == "vendor.eval"
