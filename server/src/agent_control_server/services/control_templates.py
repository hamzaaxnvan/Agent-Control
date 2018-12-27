"""Template rendering and error-mapping helpers for control templates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import re2
from agent_control_models import (
    ControlDefinition,
    EnumTemplateParameter,
    JsonValue,
    TemplateControlInput,
    TemplateDefinition,
    TemplateParameterDefinition,
    TemplateValue,
)
from agent_control_models.errors import ErrorCode, ValidationErrorItem
from pydantic import ValidationError

from ..errors import APIValidationError
from .condition_traversal import iter_condition_leaves_with_paths
from .validation_paths import format_field_path

_TEMPLATE_VALUE_MISSING = object()


def can_render_template(template_input: TemplateControlInput) -> bool:
    """Return whether the template input has enough values to render.

    True when every required parameter (that has no default) has a value in
    ``template_values``.  Used to decide between rendered and unrendered
    persistence.
    """
    template = template_input.template
    for name, param in template.parameters.items():
        if not param.required:
            continue
        has_value = name in template_input.template_values
        has_default = getattr(param, "default", None) is not None
        if not has_value and not has_default:
            return False
    return True


@dataclass(frozen=True)
class RenderedTemplateControl:
    """Rendered template result plus reverse mapping for validation errors."""

    control: ControlDefinition
    reverse_path_map: dict[str, str]


def _parameter_error(
    parameter_name: str,
    parameter_definition: TemplateParameterDefinition,
    message: str,
    *,
    code: str = "template_parameter_invalid",
    value: TemplateValue | None = None,
) -> APIValidationError:
    """Create a parameter-focused validation error."""
    return APIValidationError(
        error_code=ErrorCode.TEMPLATE_PARAMETER_INVALID,
        detail=f"Invalid value for parameter '{parameter_definition.label}'",
        resource="Control",
        hint="Update the template parameter values and try again.",
        errors=[
            ValidationErrorItem(
                resource="Control",
                field=f"template_values.{parameter_name}",
                code=code,
                message=message,
                value=value,
                parameter=parameter_name,
                parameter_label=parameter_definition.label,
            )
        ],
    )


def _render_error(
    detail: str,
    *,
    field: str | None = None,
    code: str = "template_render_error",
    message: str | None = None,
) -> APIValidationError:
    """Create a structural template rendering error."""
    errors = None
    if message is not None:
        errors = [
            ValidationErrorItem(
                resource="Control",
                field=field,
                code=code,
                message=message,
                rendered_field=field,
            )
        ]

    return APIValidationError(
        error_code=ErrorCode.TEMPLATE_RENDER_ERROR,
        detail=detail,
        resource="Control",
        hint="Update the template definition and try again.",
        errors=errors,
    )


def _parameter_default(
    parameter_definition: TemplateParameterDefinition,
) -> TemplateValue | object:
    """Return the explicit default for a parameter, if any."""
    # TemplateValue intentionally excludes None, so None continues to mean
    # "no default provided" for current v1 parameter types.
    default = getattr(parameter_definition, "default", None)
    return _TEMPLATE_VALUE_MISSING if default is None else cast(TemplateValue, default)


def _parameter_invalid_type(
    parameter_name: str,
    parameter_definition: TemplateParameterDefinition,
    *,
    expected: str,
    value: TemplateValue,
) -> APIValidationError:
    """Create a standard invalid-type error for template parameter values."""
    return _parameter_error(
        parameter_name,
        parameter_definition,
        f"Parameter '{parameter_definition.label}' must be {expected}.",
        code="invalid_type",
        value=value,
    )


def _require_string_parameter(
    parameter_name: str,
    parameter_definition: TemplateParameterDefinition,
    value: TemplateValue,
    *,
    expected: str,
) -> str:
    """Return a string parameter value or raise a parameter-focused type error."""
    if not isinstance(value, str):
        raise _parameter_invalid_type(
            parameter_name,
            parameter_definition,
            expected=expected,
            value=value,
        )
    return value


def _coerce_parameter_value(
    parameter_name: str,
    parameter_definition: TemplateParameterDefinition,
    value: TemplateValue,
) -> TemplateValue:
    """Validate a concrete parameter value against its parameter definition."""
    parameter_type = parameter_definition.type
    if parameter_type == "string":
        return _require_string_parameter(
            parameter_name,
            parameter_definition,
            value,
            expected="a string",
        )

    if parameter_type == "string_list":
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise _parameter_invalid_type(
                parameter_name,
                parameter_definition,
                expected="a list of strings",
                value=value,
            )
        return list(value)

    if parameter_type == "enum":
        enum_value = _require_string_parameter(
            parameter_name,
            parameter_definition,
            value,
            expected="a string enum value",
        )
        enum_definition = cast(EnumTemplateParameter, parameter_definition)
        if enum_value not in enum_definition.allowed_values:
            raise _parameter_error(
                parameter_name,
                parameter_definition,
                (
                    f"Parameter '{parameter_definition.label}' must be one of "
                    f"{enum_definition.allowed_values}."
                ),
                code="invalid_enum_value",
                value=enum_value,
            )
        return enum_value

    if parameter_type == "boolean":
        if type(value) is not bool:
            raise _parameter_invalid_type(
                parameter_name,
                parameter_definition,
                expected="a boolean",
                value=value,
            )
        return value

    if parameter_type == "regex_re2":
        pattern = _require_string_parameter(
            parameter_name,
            parameter_definition,
            value,
            expected="a string regex pattern",
        )
        try:
            re2.compile(pattern)
        except re2.error as exc:
            raise _parameter_error(
                parameter_name,
                parameter_definition,
                (
                    f"Invalid value for parameter '{parameter_definition.label}': "
                    f"Invalid regex pattern: {exc}"
                ),
                code="invalid_regex",
                value=pattern,
            ) from exc
        return pattern

    raise _render_error(
        detail=f"Unsupported template parameter type '{parameter_type}'",
        code="unsupported_parameter_type",
        message=f"Unsupported template parameter type '{parameter_type}'.",
    )


def _resolve_template_values(
    template: TemplateDefinition,
    template_values: Mapping[str, TemplateValue],
) -> dict[str, TemplateValue | object]:
    """Resolve provided parameter values with defaults and validation."""
    unknown_keys = sorted(set(template_values) - set(template.parameters))
    if unknown_keys:
        raise APIValidationError(
            error_code=ErrorCode.TEMPLATE_PARAMETER_INVALID,
            detail="Unknown template parameter(s) supplied",
            resource="Control",
            hint="Remove unknown template parameter keys and try again.",
            errors=[
                ValidationErrorItem(
                    resource="Control",
                    field=f"template_values.{name}",
                    code="unknown_parameter",
                    message=f"Unknown template parameter '{name}'.",
                    parameter=name,
                )
                for name in unknown_keys
            ],
        )

    resolved: dict[str, TemplateValue | object] = {}
    for parameter_name, parameter_definition in template.parameters.items():
        if parameter_name in template_values:
            resolved[parameter_name] = _coerce_parameter_value(
                parameter_name,
                parameter_definition,
                template_values[parameter_name],
            )
            continue

        default_value = _parameter_default(parameter_definition)
        if default_value is not _TEMPLATE_VALUE_MISSING:
            resolved[parameter_name] = _coerce_parameter_value(
                parameter_name,
                parameter_definition,
                cast(TemplateValue, default_value),
            )
            continue

        if parameter_definition.required:
            raise _parameter_error(
                parameter_name,
                parameter_definition,
                f"Missing required parameter '{parameter_definition.label}'.",
                code="missing_parameter",
            )

        resolved[parameter_name] = _TEMPLATE_VALUE_MISSING

    return resolved


def _format_rendered_path(path_parts: list[str | int]) -> str | None:
    """Convert recursive path parts into dotted/bracketed field paths."""
    if not path_parts:
        return None

    components: list[str] = []
    for part in path_parts:
        if isinstance(part, int):
            if not components:
                components.append(f"[{part}]")
            else:
                components[-1] = f"{components[-1]}[{part}]"
            continue
        components.append(part)
    return ".".join(components)


def _render_json_value(
    value: JsonValue,
    *,
    resolved_values: Mapping[str, TemplateValue | object],
    path_parts: list[str | int],
    reverse_path_map: dict[str, str],
    referenced_parameters: set[str],
    template: TemplateDefinition,
) -> JsonValue:
    """Render a JSON value by resolving $param binding objects recursively."""
    if isinstance(value, dict):
        if "$param" in value:
            if len(value) != 1 or not isinstance(value["$param"], str):
                raise _render_error(
                    detail="Invalid $param binding object in template definition",
                    field=_format_rendered_path(path_parts),
                    code="invalid_param_binding",
                    message="A $param binding must be exactly {'$param': '<parameter_name>'}.",
                )

            parameter_name = value["$param"]
            if parameter_name not in template.parameters:
                raise _render_error(
                    detail=f"Template references undefined parameter '{parameter_name}'",
                    field=_format_rendered_path(path_parts),
                    code="undefined_parameter_reference",
                    message=f"Template references undefined parameter '{parameter_name}'.",
                )

            parameter_definition = template.parameters[parameter_name]
            if (
                not parameter_definition.required
                and _parameter_default(parameter_definition) is _TEMPLATE_VALUE_MISSING
            ):
                raise _render_error(
                    detail=(
                        f"Template parameter '{parameter_name}' is optional but referenced in "
                        "definition_template without a default value"
                    ),
                    field=f"template.parameters.{parameter_name}",
                    code="optional_referenced_parameter_requires_default",
                    message=(
                        f"Optional template parameter '{parameter_definition.label}' is "
                        "referenced in the template and must define a default value or be "
                        "marked required."
                    ),
                )

            resolved_value = resolved_values[parameter_name]
            if resolved_value is _TEMPLATE_VALUE_MISSING:
                raise _parameter_error(
                    parameter_name,
                    parameter_definition,
                    f"Missing value for parameter '{parameter_definition.label}'.",
                    code="missing_parameter",
                )

            referenced_parameters.add(parameter_name)
            rendered_field = _format_rendered_path(path_parts)
            if rendered_field is not None:
                reverse_path_map[rendered_field] = parameter_name
            return cast(JsonValue, resolved_value)

        return {
            key: _render_json_value(
                nested_value,
                resolved_values=resolved_values,
                path_parts=[*path_parts, key],
                reverse_path_map=reverse_path_map,
                referenced_parameters=referenced_parameters,
                template=template,
            )
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [
            _render_json_value(
                nested_value,
                resolved_values=resolved_values,
                path_parts=[*path_parts, index],
                reverse_path_map=reverse_path_map,
                referenced_parameters=referenced_parameters,
                template=template,
            )
            for index, nested_value in enumerate(value)
        ]

    return value


def _strip_request_prefix(field: str | None) -> str | None:
    """Remove the request-level 'data.' prefix from raw control validation paths."""
    if field is None:
        return None
