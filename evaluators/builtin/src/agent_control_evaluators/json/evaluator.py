"""JSON validation evaluator with schema, type, required field, constraint, and pattern checks."""

import asyncio
import json
from typing import Any

import re2
from agent_control_models import EvaluatorResult
from jsonschema import Draft7Validator

from agent_control_evaluators._base import Evaluator, EvaluatorMetadata
from agent_control_evaluators._registry import register_evaluator
from agent_control_evaluators.json.config import JSONEvaluatorConfig


@register_evaluator
class JSONEvaluator(Evaluator[JSONEvaluatorConfig]):
    """Comprehensive JSON validation evaluator.

    Validates JSON data in this order (fail-fast, simple to complex):
    1. JSON syntax/validity - Parse and validate JSON structure
    2. JSON Schema validation (if configured) - Comprehensive structure check
    3. Required fields (if configured) - Ensure critical fields exist
    4. Type checking (if configured) - Validate field types
    5. Field constraints (if configured) - Validate ranges, enums, string length
    6. Pattern matching (if configured) - Validate field value patterns

    Example configs:
        # JSON Schema validation
        {"json_schema": {"type": "object", "required": ["id", "name"]}}

        # Type checking
        {"field_types": {"user.id": "string", "user.age": "integer"}}

        # Required fields
        {"required_fields": ["id", "email", "created_at"]}

        # Field constraints - numeric ranges
        {"field_constraints": {"score": {"min": 0.0, "max": 1.0}}}

        # Pattern matching
        {"field_patterns": {"email": "^[a-z0-9._%+-]+@[a-z0-9.-]+\\\\.[a-z]+$"}}
    """

    metadata = EvaluatorMetadata(
        name="json",
        version="1.0.0",
        description=(
            "Comprehensive JSON validation: schema, types, required fields, "
            "constraints, and patterns"
        ),
        timeout_ms=15000,  # Longer timeout for schema validation
    )
    config_model = JSONEvaluatorConfig

    # Instance variables (typed to support None when feature not configured)
    _schema_validator: Draft7Validator | None
    _compiled_patterns: dict[str, Any] | None

    def __init__(self, config: JSONEvaluatorConfig) -> None:
        super().__init__(config)

        # Pre-compile schema validator (thread-safe, immutable)
        if config.json_schema:
            self._schema_validator = Draft7Validator(config.json_schema)
        else:
            self._schema_validator = None

        # Pre-compile regex patterns (thread-safe, immutable)
        if config.field_patterns:
            self._compiled_patterns = {}
            for path, pattern_config in config.field_patterns.items():
                # Support both string and dict formats
                if isinstance(pattern_config, str):
                    pattern = pattern_config
                    flags = None
                else:
                    pattern = pattern_config["pattern"]
                    flags = pattern_config.get("flags")

                # Compile with flags
                if flags and "IGNORECASE" in flags:
                    opts = re2.Options()
                    opts.case_sensitive = False
                    compiled = re2.compile(pattern, opts)
                else:
                    compiled = re2.compile(pattern)

                self._compiled_patterns[path] = compiled
        else:
            self._compiled_patterns = None

    async def evaluate(self, data: Any) -> EvaluatorResult:
        """Evaluate JSON data against all configured validation checks.

        Note: Validation is offloaded to a thread executor to avoid blocking
        the event loop for large payloads, since all validation logic is synchronous.
        """
        # Offload synchronous validation to thread to avoid blocking event loop
        return await asyncio.to_thread(self._evaluate_sync, data)

    def _evaluate_sync(self, data: Any) -> EvaluatorResult:
        """Synchronous validation logic (called via thread executor)."""

        # 1. JSON Syntax/Validity Check
        parsed_data, parse_error = self._parse_json(data)
        if parse_error:
            return self._handle_parse_error(parse_error)

        # Type narrowing: if no parse error, parsed_data is guaranteed to be valid
        assert parsed_data is not None

        # 2. JSON Schema Validation (comprehensive structure check)
        if self._schema_validator:
            schema_result = self._check_schema(parsed_data)
            if schema_result:
                return schema_result

        # 3. Required Fields Check (fail fast on missing critical fields)
        if self.config.required_fields:
            required_result = self._check_required(parsed_data)
            if required_result:
                return required_result

        # 4. Type Checking (validate data types)
        if self.config.field_types:
            type_result = self._check_types(parsed_data)
            if type_result:
                return type_result

        # 5. Field Constraints (validate ranges, enums, string length)
        if self.config.field_constraints:
            constraints_result = self._check_constraints(parsed_data)
            if constraints_result:
                return constraints_result

        # 6. Pattern Matching (validate field value patterns)
        if self._compiled_patterns:
            pattern_result = self._check_patterns(parsed_data)
            if pattern_result:
                return pattern_result

        # All checks passed
        return EvaluatorResult(
            matched=False,
            confidence=1.0,
            message="JSON validation passed all checks",
        )

    def _parse_json(self, data: Any) -> tuple[dict | list | None, str | None]:
        """Parse input to JSON. Returns (parsed_data, error_message)."""
        if data is None:
            return None, "Input data is None"

        # Already parsed
        if isinstance(data, (dict, list)):
            return data, None

        # Parse JSON string
        if isinstance(data, str):
            try:
                return json.loads(data), None
            except json.JSONDecodeError as e:
                return None, f"Invalid JSON: {e}"

        # Unsupported type
        return None, f"Unsupported data type: {type(data).__name__}"

    def _handle_parse_error(self, error: str) -> EvaluatorResult:
        """Handle JSON parse errors based on allow_invalid_json config."""
        if self.config.allow_invalid_json:
            # Allow invalid JSON through as non-match
            return EvaluatorResult(
                matched=False,
                confidence=0.0,
                message=f"Invalid JSON allowed: {error}",
            )
        else:
            # Block invalid JSON
            return EvaluatorResult(
                matched=True,
                confidence=1.0,
                message=f"Invalid JSON blocked: {error}",
            )

    def _check_schema(self, data: dict | list) -> EvaluatorResult | None:
        """Validate against JSON Schema. Returns error result or None."""
        if not self._schema_validator:
            return None

        errors = list(self._schema_validator.iter_errors(data))

        if not errors:
            return None  # Validation passed

        # Build error message
        error_messages = []
        for error in errors[:3]:
            path = ".".join(str(p) for p in error.path) if error.path else "root"
            error_messages.append(f"{path}: {error.message}")

        message = f"Schema validation failed: {'; '.join(error_messages)}"
        if len(errors) > 3:
            message += f" (+{len(errors) - 3} more errors)"

        return EvaluatorResult(
            matched=True,
            confidence=1.0,
            message=message,
            metadata={"error_count": len(errors), "errors": error_messages},
        )

    def _check_types(self, data: dict | list) -> EvaluatorResult | None:
        """Validate field types. Returns error result or None."""
        if not self.config.field_types:
            return None

        if not isinstance(data, dict):
            return EvaluatorResult(
                matched=True,
                confidence=1.0,
                message="Type checking requires a JSON object, got array/primitive",
            )

        errors = []

        for field_path, expected_type in self.config.field_types.items():
            value, found = self._get_nested_value(data, field_path)

            if not found:
                errors.append(f"{field_path}: field not found")
                continue

            actual_type = self._get_json_type(value)
            if actual_type != expected_type:
                errors.append(
                    f"{field_path}: expected {expected_type}, got {actual_type}"
                )

        # Check for extra fields if not allowed
        if not self.config.allow_extra_fields:
            # Get only leaf paths to avoid flagging parent containers
            actual_paths = self._get_all_paths(data, leaves_only=True)

            # Include all explicitly referenced fields as allowed paths
            specified_paths = set(self.config.field_types.keys())
            if self.config.required_fields:
                specified_paths.update(self.config.required_fields)
            if self.config.field_constraints:
                specified_paths.update(self.config.field_constraints.keys())
            if self.config.field_patterns:
