"""Tests for JSON validation evaluator."""

import pytest
from agent_control_evaluators.json import JSONEvaluator, JSONEvaluatorConfig


class TestJSONParsing:
    """Test JSON parsing with various input types."""

    @pytest.mark.asyncio
    async def test_dict_input(self):
        """Test that dict input is accepted as-is."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(required_fields=["id"]))
        result = await evaluator.evaluate({"id": 123})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_json_string_input(self):
        """Test that JSON string input is parsed correctly."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(required_fields=["id"]))
        result = await evaluator.evaluate('{"id": 123}')
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_invalid_json_blocked_by_default(self):
        """Test that invalid JSON is blocked by default."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(required_fields=["id"]))
        result = await evaluator.evaluate("{invalid json")
        assert result.matched is True  # Blocked by default
        assert "Invalid JSON blocked" in result.message

    @pytest.mark.asyncio
    async def test_invalid_json_allowed_when_configured(self):
        """Test that invalid JSON is allowed when allow_invalid_json=True."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(required_fields=["id"], allow_invalid_json=True)
        )
        result = await evaluator.evaluate("{invalid json")
        assert result.matched is False
        assert "Invalid JSON allowed" in result.message

    @pytest.mark.asyncio
    async def test_none_input(self):
        """Test that None input is handled gracefully."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(required_fields=["id"]))
        result = await evaluator.evaluate(None)
        assert result.matched is True
        assert "None" in result.message


class TestSchemaValidation:
    """Test JSON Schema validation mode."""

    @pytest.mark.asyncio
    async def test_valid_schema(self):
        """Test that valid data passes schema validation."""
        schema = {
            "type": "object",
            "required": ["id", "name"],
            "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        }
        evaluator = JSONEvaluator(JSONEvaluatorConfig(json_schema=schema))
        result = await evaluator.evaluate({"id": 1, "name": "test"})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_invalid_schema_missing_required(self):
        """Test that missing required fields fail schema validation."""
        schema = {"type": "object", "required": ["id", "name"]}
        evaluator = JSONEvaluator(JSONEvaluatorConfig(json_schema=schema))
        result = await evaluator.evaluate({"id": 1})
        assert result.matched is True  # Failed
        assert "Schema validation failed" in result.message
        assert "'name' is a required property" in result.message

    @pytest.mark.asyncio
    async def test_invalid_schema_wrong_type(self):
        """Test that wrong type fails schema validation."""
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
        evaluator = JSONEvaluator(JSONEvaluatorConfig(json_schema=schema))
        result = await evaluator.evaluate({"id": "not-an-int"})
        assert result.matched is True  # Failed
        assert "Schema validation failed" in result.message

    @pytest.mark.asyncio
    async def test_nested_object_validation(self):
        """Test schema validation on nested objects."""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer"}},
                }
            },
        }
        evaluator = JSONEvaluator(JSONEvaluatorConfig(json_schema=schema))
        result = await evaluator.evaluate({"user": {"id": 123}})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_array_validation(self):
        """Test schema validation on arrays."""
        schema = {"type": "array", "items": {"type": "integer"}}
        evaluator = JSONEvaluator(JSONEvaluatorConfig(json_schema=schema))
        result = await evaluator.evaluate([1, 2, 3])
        assert result.matched is False  # Validation passed

        result = await evaluator.evaluate([1, "not-int", 3])
        assert result.matched is True  # Failed


class TestRequiredFieldsValidation:
    """Test required fields validation mode."""

    @pytest.mark.asyncio
    async def test_all_present(self):
        """Test that all required fields present passes validation."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(required_fields=["id", "name", "email"]))
        result = await evaluator.evaluate({"id": 1, "name": "test", "email": "test@example.com"})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_missing_field(self):
        """Test that missing required field fails validation."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(required_fields=["id", "name"]))
        result = await evaluator.evaluate({"id": 1})
        assert result.matched is True  # Failed
        assert "Missing required fields: name" in result.message

    @pytest.mark.asyncio
    async def test_null_allowed(self):
        """Test that null values are allowed when configured."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(required_fields=["id"], allow_null_required=True)
        )
        result = await evaluator.evaluate({"id": None})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_null_disallowed(self):
        """Test that null values fail when disallowed."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(required_fields=["id"], allow_null_required=False)
        )
        result = await evaluator.evaluate({"id": None})
        assert result.matched is True  # Failed
        assert "null not allowed" in result.message

    @pytest.mark.asyncio
    async def test_nested_required_fields(self):
        """Test required fields validation on nested paths."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(required_fields=["user.id", "user.email"]))
        result = await evaluator.evaluate({"user": {"id": 123, "email": "test@example.com"}})
        assert result.matched is False  # Validation passed
