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


class TestTypesValidation:
    """Test type checking validation mode."""

    @pytest.mark.asyncio
    async def test_all_types_match(self):
        """Test that all types matching passes validation."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                field_types={
                    "id": "string",
                    "age": "integer",
                    "score": "number",
                    "active": "boolean",
                    "tags": "array",
                    "meta": "object",
                    "empty": "null",
                }
            )
        )
        result = await evaluator.evaluate(
            {
                "id": "123",
                "age": 25,
                "score": 0.95,
                "active": True,
                "tags": ["a", "b"],
                "meta": {"key": "value"},
                "empty": None,
            }
        )
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_type_mismatch(self):
        """Test that type mismatch fails validation."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(field_types={"id": "string"}))
        result = await evaluator.evaluate({"id": 123})
        assert result.matched is True  # Failed
        assert "expected string, got integer" in result.message

    @pytest.mark.asyncio
    async def test_missing_field(self):
        """Test that missing field fails type validation."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(field_types={"id": "string"}))
        result = await evaluator.evaluate({"name": "test"})
        assert result.matched is True  # Failed
        assert "field not found" in result.message

    @pytest.mark.asyncio
    async def test_nested_field_types(self):
        """Test type checking on nested fields."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_types={"user.id": "integer", "user.name": "string"})
        )
        result = await evaluator.evaluate({"user": {"id": 123, "name": "test"}})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_extra_fields_allowed(self):
        """Test that extra fields are allowed by default."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_types={"id": "string"}, allow_extra_fields=True)
        )
        result = await evaluator.evaluate({"id": "123", "extra": "field"})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_extra_fields_denied(self):
        """Test that extra fields can be denied."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_types={"id": "string"}, allow_extra_fields=False)
        )
        result = await evaluator.evaluate({"id": "123", "extra": "field"})
        assert result.matched is True  # Failed
        assert "Extra fields not allowed" in result.message

    @pytest.mark.asyncio
    async def test_array_input_fails_type_check(self):
        """Test that array input fails type checking gracefully."""
        evaluator = JSONEvaluator(JSONEvaluatorConfig(field_types={"id": "string"}))
        result = await evaluator.evaluate([1, 2, 3])
        assert result.matched is True  # Failed
        assert "requires a JSON object, got array" in result.message

    @pytest.mark.asyncio
    async def test_nested_fields_with_strict_mode_no_extra_fields(self):
        """Test P1 fix: Nested fields with allow_extra_fields=False should not flag parent containers."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                field_types={"user.id": "string"},
                allow_extra_fields=False,
            )
        )
        # Should pass: "user" is a container, "user.id" is the typed leaf field
        result = await evaluator.evaluate({"user": {"id": "123"}})
        assert result.matched is False  # Validation passed
        assert "Extra fields" not in result.message

    @pytest.mark.asyncio
    async def test_nested_fields_strict_mode_detects_actual_extra_leaf_fields(self):
        """Test that strict mode still catches actual extra leaf fields in nested objects."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                field_types={"user.id": "string"},
                allow_extra_fields=False,
            )
        )
        # Should fail: "user.name" is an extra leaf field not in field_types
        result = await evaluator.evaluate({"user": {"id": "123", "name": "test"}})
        assert result.matched is True  # Failed
        assert "Extra fields not allowed" in result.message
        assert "user.name" in result.message

    @pytest.mark.asyncio
    async def test_multiple_nested_levels_strict_mode(self):
        """Test strict mode with multiple levels of nesting."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                field_types={"user.profile.email": "string"},
                allow_extra_fields=False,
            )
        )
        # Should pass: "user" and "user.profile" are containers
        result = await evaluator.evaluate({"user": {"profile": {"email": "test@example.com"}}})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_nested_fields_with_required_and_strict_mode(self):
        """Test nested fields with both required_fields and strict mode."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                required_fields=["user.id", "user.email"],
                field_types={"user.id": "string"},
                allow_extra_fields=False,
            )
        )
        # Should pass: both user.id and user.email are allowed (one typed, one required)
        result = await evaluator.evaluate({"user": {"id": "123", "email": "test@example.com"}})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_strict_mode_top_level_extra_field_still_detected(self):
        """Test that top-level extra fields are still detected in strict mode."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                field_types={"id": "string"},
                allow_extra_fields=False,
            )
        )
        # Should fail: "extra" is a top-level extra field
        result = await evaluator.evaluate({"id": "123", "extra": "field"})
        assert result.matched is True  # Failed
        assert "Extra fields not allowed" in result.message

    @pytest.mark.asyncio
    async def test_strict_mode_allows_field_constraints_fields(self):
        """Test that fields in field_constraints are not flagged as extra.

        Regression test: field_constraints fields should be in the allow-list
        when allow_extra_fields=False.
        """
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                field_types={"id": "string"},
                field_constraints={"score": {"min": 0.0, "max": 1.0}},
                allow_extra_fields=False,
            )
        )
        # Should pass: "score" is referenced in field_constraints
        result = await evaluator.evaluate({"id": "123", "score": 0.5})
        assert result.matched is False  # Validation passed
        assert "passed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_strict_mode_allows_field_patterns_fields(self):
        """Test that fields in field_patterns are not flagged as extra.

        Regression test: field_patterns fields should be in the allow-list
        when allow_extra_fields=False.
        """
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                field_types={"id": "string"},
                field_patterns={"email": r"^.+@.+$"},
                allow_extra_fields=False,
            )
        )
        # Should pass: "email" is referenced in field_patterns
        result = await evaluator.evaluate({"id": "123", "email": "test@example.com"})
        assert result.matched is False  # Validation passed
        assert "passed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_strict_mode_with_all_field_references(self):
        """Test strict mode with fields from all config options.

        Ensures that required_fields, field_types, field_constraints, and
        field_patterns are all included in the allow-list.
        """
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(
                required_fields=["name"],
                field_types={"id": "string"},
                field_constraints={"score": {"min": 0.0, "max": 1.0}},
                field_patterns={"email": r"^.+@.+$"},
                allow_extra_fields=False,
            )
        )
        # Should pass: all fields are referenced in some config option
        result = await evaluator.evaluate({
            "id": "123",
            "name": "Test",
            "score": 0.75,
            "email": "test@example.com",
        })
        assert result.matched is False  # Validation passed

        # Should fail: "extra" is not referenced anywhere
        result = await evaluator.evaluate({
            "id": "123",
            "name": "Test",
            "score": 0.75,
            "email": "test@example.com",
            "extra": "not allowed",
        })
        assert result.matched is True  # Failed
        assert "Extra fields not allowed" in result.message


class TestConstraintsValidation:
    """Test field constraints validation mode."""

    @pytest.mark.asyncio
    async def test_numeric_range_within_bounds(self):
        """Test that numeric value within range passes validation."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_constraints={"score": {"min": 0.0, "max": 1.0}})
        )
        result = await evaluator.evaluate({"score": 0.75})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_numeric_range_below_min(self):
        """Test that value below minimum fails validation."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_constraints={"score": {"min": 0.0, "max": 1.0}})
        )
        result = await evaluator.evaluate({"score": -0.5})
        assert result.matched is True  # Failed
        assert "below minimum" in result.message

    @pytest.mark.asyncio
    async def test_numeric_range_above_max(self):
        """Test that value above maximum fails validation."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_constraints={"score": {"min": 0.0, "max": 1.0}})
        )
        result = await evaluator.evaluate({"score": 1.5})
        assert result.matched is True  # Failed
        assert "above maximum" in result.message

    @pytest.mark.asyncio
    async def test_integer_range(self):
        """Test integer range constraints."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_constraints={"count": {"min": -10, "max": 5}})
        )
        result = await evaluator.evaluate({"count": 3})
        assert result.matched is False  # Validation passed

        result = await evaluator.evaluate({"count": 10})
        assert result.matched is True  # Failed

    @pytest.mark.asyncio
    async def test_enum_valid_value(self):
        """Test that valid enum value passes validation."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_constraints={"status": {"enum": ["pending", "approved", "rejected"]}})
        )
        result = await evaluator.evaluate({"status": "approved"})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_enum_invalid_value(self):
        """Test that invalid enum value fails validation."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_constraints={"status": {"enum": ["pending", "approved", "rejected"]}})
        )
        result = await evaluator.evaluate({"status": "invalid"})
        assert result.matched is True  # Failed
        assert "not in allowed values" in result.message

    @pytest.mark.asyncio
    async def test_string_length_within_range(self):
        """Test that string length within range passes validation."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_constraints={"username": {"min_length": 3, "max_length": 20}})
        )
        result = await evaluator.evaluate({"username": "test_user"})
        assert result.matched is False  # Validation passed

    @pytest.mark.asyncio
    async def test_string_length_too_short(self):
        """Test that string shorter than minimum fails validation."""
        evaluator = JSONEvaluator(
            JSONEvaluatorConfig(field_constraints={"username": {"min_length": 3, "max_length": 20}})
        )
        result = await evaluator.evaluate({"username": "ab"})
        assert result.matched is True  # Failed
        assert "below minimum" in result.message
