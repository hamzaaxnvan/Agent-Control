"""
Standardized error models for Agent Control API.

This module implements a unified error response format that combines:
- RFC 7807 (Problem Details for HTTP APIs)
- Kubernetes-style error structure
- GitHub-style validation error arrays
- OPA-style semantic error codes

Example error response:
{
    "type": "https://agent-control.dev/errors/not-found",
    "title": "Resource Not Found",
    "status": 404,
    "detail": "Agent with name 'customer-service-bot' not found",
    "instance": "/api/v1/agents/customer-service-bot",
    "error_code": "AGENT_NOT_FOUND",
    "kind": "Status",
    "api_version": "v1",
    "reason": "NotFound",
    "metadata": {
        "request_id": "req-abc123",
        "timestamp": "2025-01-15T10:30:00Z"
    },
    "errors": [
        {
            "resource": "Agent",
            "field": "agent_name",
            "code": "not_found",
            "message": "Agent with name 'customer-service-bot' does not exist"
        }
    ]
}
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from .base import BaseModel


class ErrorCode(StrEnum):
    """
    Standardized error codes following OPA-style semantic naming.

    Error codes follow the pattern: RESOURCE_ACTION or CATEGORY_DESCRIPTION
    """

    # Authentication & Authorization (1xx pattern in code)
    AUTH_MISSING_KEY = "AUTH_MISSING_KEY"
    AUTH_INVALID_KEY = "AUTH_INVALID_KEY"
    AUTH_INSUFFICIENT_PRIVILEGES = "AUTH_INSUFFICIENT_PRIVILEGES"
    AUTH_MISCONFIGURED = "AUTH_MISCONFIGURED"
    AUTH_UPSTREAM_REJECTED = "AUTH_UPSTREAM_REJECTED"

    # Resource Not Found (2xx pattern)
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"  # Generic fallback
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    CONTROL_NOT_FOUND = "CONTROL_NOT_FOUND"
    CONTROL_VERSION_NOT_FOUND = "CONTROL_VERSION_NOT_FOUND"
    CONTROL_BINDING_NOT_FOUND = "CONTROL_BINDING_NOT_FOUND"
    EVALUATOR_NOT_FOUND = "EVALUATOR_NOT_FOUND"

    # Conflict Errors (3xx pattern)
    AGENT_NAME_CONFLICT = "AGENT_NAME_CONFLICT"
    POLICY_NAME_CONFLICT = "POLICY_NAME_CONFLICT"
    CONTROL_NAME_CONFLICT = "CONTROL_NAME_CONFLICT"
    CONTROL_BINDING_CONFLICT = "CONTROL_BINDING_CONFLICT"
    EVALUATOR_NAME_CONFLICT = "EVALUATOR_NAME_CONFLICT"
    CONTROL_IN_USE = "CONTROL_IN_USE"
    CONTROL_TEMPLATE_CONFLICT = "CONTROL_TEMPLATE_CONFLICT"
    EVALUATOR_IN_USE = "EVALUATOR_IN_USE"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"

    # Validation Errors (4xx pattern)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_CONFIG = "INVALID_CONFIG"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    CORRUPTED_DATA = "CORRUPTED_DATA"
    POLICY_CONTROL_INCOMPATIBLE = "POLICY_CONTROL_INCOMPATIBLE"
    CONTROL_BINDING_INCOMPATIBLE = "CONTROL_BINDING_INCOMPATIBLE"
    TEMPLATE_PARAMETER_INVALID = "TEMPLATE_PARAMETER_INVALID"
    TEMPLATE_RENDER_ERROR = "TEMPLATE_RENDER_ERROR"

    # Server Errors (5xx pattern)
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    EVALUATION_FAILED = "EVALUATION_FAILED"


class ErrorReason(StrEnum):
    """
    Kubernetes-style reason codes for error categorization.

    These provide a machine-readable, stable identifier for the error type.
    """

    # Client errors
    NOT_FOUND = "NotFound"
    ALREADY_EXISTS = "AlreadyExists"
    CONFLICT = "Conflict"
    INVALID = "Invalid"
    FORBIDDEN = "Forbidden"
    UNAUTHORIZED = "Unauthorized"
    BAD_REQUEST = "BadRequest"
    UNPROCESSABLE_ENTITY = "UnprocessableEntity"

    # Server errors
    INTERNAL_ERROR = "InternalError"
    SERVICE_UNAVAILABLE = "ServiceUnavailable"
    UNKNOWN = "Unknown"


class ValidationErrorItem(BaseModel):
    """
    GitHub-style validation error item.

    Represents a single validation error with field-level detail.
    """

    resource: str = Field(
        ...,
        description="The resource type where the error occurred (e.g., 'Agent', 'Control')",
    )
    field: str | None = Field(
        default=None,
        description="The field that caused the error (e.g., 'name', 'config.threshold')",
    )
    code: str = Field(
        ...,
