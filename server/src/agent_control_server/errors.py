"""
Standardized error handling for Agent Control Server.

This module provides exception classes and utilities for generating
RFC 7807 / Kubernetes / GitHub-style error responses.

Usage:
    from .errors import NotFoundError, ConflictError, ValidationError

    # Raise a not found error
    raise NotFoundError(
        error_code=ErrorCode.AGENT_NOT_FOUND,
        detail=f"Agent with name '{agent_name}' not found",
        resource="Agent",
        resource_id=agent_name,
    )

    # Raise a validation error with field-level details
    raise APIValidationError(
        error_code=ErrorCode.VALIDATION_ERROR,
        detail="Request validation failed",
        errors=[
            ValidationErrorItem(
                resource="Control",
                field="data.evaluator.config",
                code="invalid_format",
                message="Config must be an object",
            )
        ],
    )
"""

import logging
import uuid
from typing import Any

from agent_control_models.errors import (
    ERROR_TITLES,
    ErrorCode,
    ErrorDetails,
    ErrorMetadata,
    ErrorReason,
    ProblemDetail,
    ValidationErrorItem,
    make_error_type,
)
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .services.validation_paths import format_field_path

_logger = logging.getLogger(__name__)

_MAX_PUBLIC_TEXT_LENGTH = 500
_REDACTED_VALUE = "[REDACTED]"
_GENERIC_INTERNAL_DETAIL = "An unexpected error occurred. Please try again or contact support."
_GENERIC_DATABASE_DETAIL = "A database error occurred while processing the request."
_GENERIC_AUTH_MISCONFIGURED_DETAIL = (
    "Server authentication is misconfigured. Contact administrator."
)
_GENERIC_BAD_REQUEST_DETAIL = "Request validation failed."
_GENERIC_UNAUTHORIZED_DETAIL = "Authentication failed."
_GENERIC_FORBIDDEN_DETAIL = "Permission denied."
_GENERIC_NOT_FOUND_DETAIL = "Requested resource was not found."
_GENERIC_CONFLICT_DETAIL = "Request conflicts with existing state."
_DEFAULT_5XX_DETAIL_BY_CODE: dict[ErrorCode, str] = {
    ErrorCode.INTERNAL_ERROR: _GENERIC_INTERNAL_DETAIL,
    ErrorCode.DATABASE_ERROR: _GENERIC_DATABASE_DETAIL,
    ErrorCode.AUTH_MISCONFIGURED: _GENERIC_AUTH_MISCONFIGURED_DETAIL,
}
_DEFAULT_4XX_DETAIL_BY_STATUS: dict[int, str] = {
    400: _GENERIC_BAD_REQUEST_DETAIL,
    401: _GENERIC_UNAUTHORIZED_DETAIL,
    403: _GENERIC_FORBIDDEN_DETAIL,
    404: _GENERIC_NOT_FOUND_DETAIL,
    409: _GENERIC_CONFLICT_DETAIL,
    422: _GENERIC_BAD_REQUEST_DETAIL,
}


def _normalize_public_text(text: str) -> str:
    """Collapse repeated whitespace and trim to keep response payloads concise."""
    normalized = " ".join(text.split())
    if len(normalized) > _MAX_PUBLIC_TEXT_LENGTH:
        return normalized[: _MAX_PUBLIC_TEXT_LENGTH - 3] + "..."
    return normalized


def _default_public_detail(status_code: int, error_code: ErrorCode | None) -> str:
    """Return the default public-safe detail template for this status/code."""
    if status_code >= 500:
        if error_code is not None and error_code in _DEFAULT_5XX_DETAIL_BY_CODE:
            return _DEFAULT_5XX_DETAIL_BY_CODE[error_code]
        return _GENERIC_INTERNAL_DETAIL
    return _DEFAULT_4XX_DETAIL_BY_STATUS.get(status_code, _GENERIC_BAD_REQUEST_DETAIL)


def _public_detail(status_code: int, error_code: ErrorCode | None, detail: str) -> str:
    """
    Return safe client-facing detail text.

    For 5xx statuses, this always returns a fixed safe template.
    For 4xx statuses, this keeps caller-provided text after normalization.
    """
    safe_fallback = _default_public_detail(status_code, error_code)
    if status_code >= 500:
        return safe_fallback

    normalized = _normalize_public_text(detail)
    if not normalized:
        return safe_fallback
    return normalized


def _sanitize_validation_error_value(value: Any) -> bool | int | float | str | None:
    """
    Redact potentially sensitive invalid values before returning them to clients.

    Preserve primitive scalar values when safe.
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _REDACTED_VALUE
    return _REDACTED_VALUE


def _sanitize_validation_errors(
    items: list[ValidationErrorItem] | None,
) -> list[ValidationErrorItem] | None:
    """Sanitize validation error arrays for safe client output."""
    if items is None:
        return None

    return [
        item.model_copy(
            update={
                "value": _sanitize_validation_error_value(item.value),
            }
        )
        for item in items
    ]


def _sanitize_problem_detail(problem: ProblemDetail) -> ProblemDetail:
    """Apply public-safe sanitization rules to a ProblemDetail payload."""
    problem.detail = _public_detail(problem.status, problem.error_code, problem.detail)

    if problem.status >= 500:
        problem.hint = None
        problem.errors = None
        if problem.details is not None:
            problem.details.causes = None
        return problem

    if problem.hint is not None:
        normalized_hint = _normalize_public_text(problem.hint)
        problem.hint = normalized_hint if normalized_hint else None

    problem.errors = _sanitize_validation_errors(problem.errors)

    if problem.details is not None and problem.details.causes is not None:
        problem.details.causes = _sanitize_validation_errors(problem.details.causes)

    return problem


class APIError(HTTPException):
    """
    Base exception for all API errors.

    Generates RFC 7807 / Kubernetes / GitHub-style error responses.
    Subclass this for specific error types.
    """

    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        reason: ErrorReason,
        detail: str,
        *,
        errors: list[ValidationErrorItem] | None = None,
        hint: str | None = None,
        resource: str | None = None,
        resource_id: str | None = None,
        request_id: str | None = None,
        documentation_url: str | None = None,
        extra_details: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize an API error.

        Args:
            status_code: HTTP status code
            error_code: OPA-style semantic error code
            reason: Kubernetes-style reason code
            detail: Human-readable error message
            errors: GitHub-style validation error array
            hint: Actionable suggestion for resolution
            resource: Resource type (for error details)
            resource_id: Resource identifier (for error details)
            request_id: Request ID for tracing
            documentation_url: Link to relevant documentation
            extra_details: Additional context to include
        """
        self.error_code = error_code
        self.reason = reason
        self.errors = errors
        self.hint = hint
        self.resource = resource
        self.resource_id = resource_id
        self.request_id = request_id
        self.documentation_url = documentation_url
        self.extra_details = extra_details

        # Build the problem detail model
        super().__init__(status_code=status_code, detail=detail)

    def to_problem_detail(self, instance: str | None = None) -> ProblemDetail:
        """Convert this exception to a ProblemDetail response model."""
        # Build error details if we have resource info
        details: ErrorDetails | None = None
        if self.resource or self.errors:
            causes = self.errors if self.errors else None
            details = ErrorDetails(
                name=self.resource_id,
                kind=self.resource,
                causes=causes,
            )

        return ProblemDetail(
            type=make_error_type(self.error_code),
            title=ERROR_TITLES.get(self.error_code, "Error"),
            status=self.status_code,
            detail=self.detail,
            instance=instance,
            error_code=self.error_code,
            reason=self.reason,
            metadata=ErrorMetadata(request_id=self.request_id),
            errors=self.errors,
            details=details,
            hint=self.hint,
            documentation_url=self.documentation_url,
        )


# =============================================================================
# Specific Error Classes (4xx Client Errors)
# =============================================================================


class NotFoundError(APIError):
    """Resource not found error (404)."""

    def __init__(
        self,
        error_code: ErrorCode,
        detail: str,
        *,
        resource: str | None = None,
        resource_id: str | None = None,
        hint: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            status_code=404,
            error_code=error_code,
            reason=ErrorReason.NOT_FOUND,
            detail=detail,
            resource=resource,
            resource_id=resource_id,
            hint=hint,
            **kwargs,
        )


class ConflictError(APIError):
    """Resource conflict error (409)."""

    def __init__(
        self,
        error_code: ErrorCode,
        detail: str,
        *,
        resource: str | None = None,
        resource_id: str | None = None,
        hint: str | None = None,
        errors: list[ValidationErrorItem] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            status_code=409,
            error_code=error_code,
            reason=ErrorReason.CONFLICT,
            detail=detail,
            resource=resource,
            resource_id=resource_id,
            hint=hint,
            errors=errors,
            **kwargs,
        )


class APIValidationError(APIError):
    """Validation error (422)."""

    def __init__(
        self,
        error_code: ErrorCode,
        detail: str,
        *,
