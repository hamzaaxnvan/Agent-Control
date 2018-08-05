import datetime as dt
import uuid
from copy import deepcopy
from typing import Any

from agent_control_engine import list_evaluators
from agent_control_models import ControlDefinition, TemplateControlInput, UnrenderedTemplateControl
from agent_control_models.errors import ErrorCode, ValidationErrorItem
from agent_control_models.server import (
    AgentRef,
    CloneAndBindControlRequest,
    CloneAndBindControlResponse,
    ControlAttachments,
    ControlSummary,
    ControlVersionSummary,
    CreateControlRequest,
    CreateControlResponse,
    DeleteControlResponse,
    GetControlDataResponse,
    GetControlResponse,
    GetControlSchemaResponse,
    GetControlVersionResponse,
    ListControlsResponse,
    ListControlVersionsResponse,
    PaginationInfo,
    PatchControlRequest,
    PatchControlResponse,
    PolicyRef,
    RenderControlTemplateRequest,
    RenderControlTemplateResponse,
    SetControlDataRequest,
    SetControlDataResponse,
    SlugName,
    TargetAttachmentRef,
    ValidateControlDataRequest,
    ValidateControlDataResponse,
)
from fastapi import APIRouter, Depends, Query, Request
from jsonschema_rs import ValidationError as JSONSchemaValidationError
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_framework import Operation, Principal, get_authorizer, require_operation
from ..db import get_async_db
from ..errors import (
    APIError,
    APIValidationError,
    ConflictError,
    DatabaseError,
    ForbiddenError,
    NotFoundError,
)
from ..logging_utils import get_logger
from ..models import Agent, AgentData
from ..services.condition_traversal import iter_condition_leaves_with_paths
from ..services.control_bindings import ControlBindingsService
from ..services.control_definitions import parse_control_definition_or_api_error
from ..services.control_templates import (
    can_render_template,
    remap_template_api_error,
    render_template_control_input,
    validate_partial_template_values,
    validate_template_structure,
)
from ..services.controls import ControlService
from ..services.evaluator_utils import (
    parse_evaluator_ref_full,
    validate_config_against_schema,
)
from ..services.validation_paths import format_field_path

# Pagination constants
_DEFAULT_PAGINATION_LIMIT = 20
_MAX_PAGINATION_LIMIT = 100
_INVALID_PARAMETERS_MESSAGE = "Invalid config parameters for evaluator."
_CORRUPTED_CONTROL_DATA_MESSAGE = "Stored control data is corrupted and cannot be parsed."
_SCHEMA_VALIDATION_FAILED_MESSAGE = "Config does not satisfy the evaluator schema."

router = APIRouter(prefix="/controls", tags=["controls"])
template_router = APIRouter(prefix="/control-templates", tags=["controls"])

_logger = get_logger(__name__)

_CONTROL_NAME_UNIQUE_CONSTRAINTS = {
    "controls_name_key",
    "idx_controls_name_active",
    "idx_controls_namespace_name_active",
}
_MAX_TARGET_CONTEXT_VALUE_LENGTH = 255
_CLONE_NAME_SUFFIX_HEX_LENGTH = 16
_GENERATED_CLONE_NAME_ATTEMPTS = 5
_TRUE_QUERY_VALUES = {"1", "true", "t", "yes", "y", "on"}
_SLUG_NAME_ADAPTER = TypeAdapter(SlugName)


def _is_target_context_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= _MAX_TARGET_CONTEXT_VALUE_LENGTH
    )


def _ensure_same_namespace_authorization(
    *principals: Principal,
    detail: str = "Authorization resolved to different namespaces.",
    hint: str = "Use credentials that grant the required operations in the same namespace.",
) -> None:
    namespace_keys = {principal.namespace_key for principal in principals}
    if len(namespace_keys) == 1:
        return
    raise ForbiddenError(
        error_code=ErrorCode.AUTH_INSUFFICIENT_PRIVILEGES,
        detail=detail,
        resource="ControlBinding",
        hint=hint,
    )


async def _clone_and_bind_context(request: Request) -> dict[str, Any]:
    """Surface clone target identifiers to the authorization context."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001  malformed JSON falls through to endpoint validation
        return {}
    if not isinstance(body, dict):
        return {}
    target_binding = body.get("target_binding")
    if not isinstance(target_binding, dict):
        return {}
    target_type = target_binding.get("target_type")
    target_id = target_binding.get("target_id")
    if not _is_target_context_value(target_type):
        return {}
    if not _is_target_context_value(target_id):
        return {}
    return {
        "target_type": target_type,
        "target_id": target_id,
    }


def _attachment_target_context(request: Request) -> dict[str, str] | None:
    """Return target context only when both attachment identifiers are valid."""
    target_type = request.query_params.get("attachment_target_type")
    target_id = request.query_params.get("attachment_target_id")
    if (
        target_type is None
        or target_id is None
        or not _is_target_context_value(target_type)
        or not _is_target_context_value(target_id)
    ):
        return None
    return {"target_type": target_type, "target_id": target_id}


async def _optional_attachment_target_principal(request: Request) -> Principal | None:
    include_attachments = request.query_params.get("include_attachments")
    if include_attachments is None:
        return None
    if include_attachments.lower() not in _TRUE_QUERY_VALUES:
        return None
    target_context = _attachment_target_context(request)
    if target_context is None:
        return None
    return await get_authorizer(Operation.CONTROL_BINDINGS_READ).authorize(
        request,
        Operation.CONTROL_BINDINGS_READ,
        target_context,
    )


def _generated_clone_name(source_id: int, source_name: str) -> str:
    """Return a slug-safe default name for a cloned control."""
    suffix = f"-clone-{uuid.uuid4().hex[:_CLONE_NAME_SUFFIX_HEX_LENGTH]}"
    candidate = f"{source_name[: 255 - len(suffix)]}{suffix}"
    try:
        return _SLUG_NAME_ADAPTER.validate_python(candidate)
    except ValidationError:
        return _SLUG_NAME_ADAPTER.validate_python(f"control-{source_id}{suffix}")


async def _resolve_clone_name(
    control_service: ControlService,
    *,
    namespace_key: str,
    source_id: int,
    source_name: str,
    requested_name: str | None,
) -> str:
    if requested_name is not None:
        if await control_service.active_control_name_exists(
            requested_name, namespace_key=namespace_key
        ):
            raise ConflictError(
                error_code=ErrorCode.CONTROL_NAME_CONFLICT,
                detail=f"Control with name '{requested_name}' already exists",
                resource="Control",
                resource_id=requested_name,
                hint="Choose a different clone name.",
            )
        return requested_name

    for _ in range(_GENERATED_CLONE_NAME_ATTEMPTS):
        clone_name = _generated_clone_name(source_id, source_name)
        if not await control_service.active_control_name_exists(
            clone_name, namespace_key=namespace_key
        ):
            return clone_name

    raise ConflictError(
        error_code=ErrorCode.CONTROL_NAME_CONFLICT,
        detail="Could not generate a unique clone name.",
        resource="Control",
        resource_id=source_name,
        hint="Retry the request or provide an explicit clone name.",
    )


def _validate_attachment_filters(
    *,
    include_attachments: bool,
    attachment_target_type: str | None,
    attachment_target_id: str | None,
) -> None:
    if include_attachments:
        if (attachment_target_type is None) != (attachment_target_id is None):
            raise APIValidationError(
                error_code=ErrorCode.VALIDATION_ERROR,
                detail="Attachment target filters must be supplied together.",
                resource="Control",
                hint=(
                    "Set both attachment_target_type and attachment_target_id, "
                    "or remove both filters."
                ),
                errors=[
                    ValidationErrorItem(
                        resource="Control",
                        field=(
                            "attachment_target_type"
                            if attachment_target_type is None
                            else "attachment_target_id"
                        ),
                        code="missing_required_parameter",
                        message=(
                            "Set attachment_target_type and attachment_target_id "
                            "together."
                        ),
                    )
                ],
            )
        return
    if attachment_target_type is None and attachment_target_id is None:
        return
    raise APIValidationError(
        error_code=ErrorCode.VALIDATION_ERROR,
        detail="Attachment target filters require include_attachments=true.",
        resource="Control",
        hint="Set include_attachments=true or remove attachment target filters.",
        errors=[
            ValidationErrorItem(
                resource="Control",
                field="include_attachments",
                code="missing_required_parameter",
                message=(
                    "Set include_attachments=true when using attachment_target_type "
                    "or attachment_target_id."
                ),
            )
        ],
    )


def _serialize_control_data(
    control_data: ControlDefinition | UnrenderedTemplateControl,
) -> dict[str, object]:
    """Serialize control data for JSONB storage."""
    data_json = control_data.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude_unset=True,
    )
    if "scope" in data_json and isinstance(data_json["scope"], dict):
        data_json["scope"] = {
            k: v for k, v in data_json["scope"].items() if v is not None
        }
    # Always persist enabled explicitly so _enabled_from_stored_payload reads
    # the correct value (especially for unrendered templates where enabled=False).
    if "enabled" not in data_json:
        data_json["enabled"] = control_data.enabled
    return data_json


def _is_template_backed_payload(data: object) -> bool:
    """Return whether stored control JSON contains template metadata."""
    return isinstance(data, dict) and data.get("template") is not None


def _is_unrendered_template(data: object) -> bool:
    """Return whether stored control JSON is an unrendered template."""
    return (
        isinstance(data, dict)
        and data.get("template") is not None
        and data.get("condition") is None
    )


def _parse_stored_control_data(
    data: dict[str, object],
    *,
    control_name: str,
    control_id: int,
) -> ControlDefinition | UnrenderedTemplateControl:
    """Parse stored JSONB into the appropriate model type."""
    if _is_unrendered_template(data):
        try:
            return UnrenderedTemplateControl.model_validate(data)
        except ValidationError:
            raise APIValidationError(
                error_code=ErrorCode.CORRUPTED_DATA,
                detail=f"Control '{control_name}' has corrupted unrendered template data",
                resource="Control",
                resource_id=str(control_id),
                hint=f"Update the control data using PUT /api/v1/controls/{control_id}/data.",
                errors=[
                    ValidationErrorItem(
                        resource="Control",
                        field="data",
                        code="corrupted_data",
                        message="Stored unrendered template data is invalid.",
                    )
                ],
            )

    return parse_control_definition_or_api_error(
        data,
        detail=f"Control '{control_name}' has invalid data",
        hint=f"Update the control data using PUT /api/v1/controls/{control_id}/data.",
        field_prefix=None,
    )


def _enabled_from_stored_payload(data: object) -> bool:
    """Return the persisted enabled flag, defaulting to True when absent."""
    if not isinstance(data, dict):
        return True
    raw_enabled = data.get("enabled", True)
    return raw_enabled if type(raw_enabled) is bool else True


def _template_backed_raw_update_conflict(control_id: int) -> ConflictError:
    """Return the v1 conflict raised when raw data updates target template-backed controls."""
    return ConflictError(
        error_code=ErrorCode.CONTROL_TEMPLATE_CONFLICT,
        detail="Template-backed controls cannot be updated with raw control data in v1",
        resource="Control",
        resource_id=str(control_id),
        hint=(
            "Submit template input to update this control, or delete and recreate "
            "it as a raw control."
        ),
        errors=[
            ValidationErrorItem(
                resource="Control",
                field="data",
                code="template_backed_control_conflict",
                message="Template-backed controls must be updated with template input.",
            )
        ],
    )


def _is_control_name_conflict(error: IntegrityError) -> bool:
    """Return whether an IntegrityError came from the active-control name uniqueness guard."""
    diag = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if diag in _CONTROL_NAME_UNIQUE_CONSTRAINTS:
        return True

    error_text = " ".join(
        part for part in (str(error.orig), str(error)) if part and part != "None"
    )
    return any(name in error_text for name in _CONTROL_NAME_UNIQUE_CONSTRAINTS)


async def _render_and_validate_template_input(
    template_input: TemplateControlInput,
    *,
    db: AsyncSession,
    namespace_key: str,
    enabled: bool = True,
) -> ControlDefinition:
    """Render a template-backed input and validate evaluator config."""
    rendered = render_template_control_input(template_input, enabled=enabled)
    try:
        await _validate_control_definition(
            rendered.control,
            db,
            namespace_key=namespace_key,
        )
    except APIValidationError as exc:
        raise remap_template_api_error(
            exc,
            reverse_path_map=rendered.reverse_path_map,
            template=template_input.template,
        ) from exc
    return rendered.control


async def _materialize_control_input(
    control_input: ControlDefinition | TemplateControlInput,
    *,
    db: AsyncSession,
    namespace_key: str,
    current_payload: object | None = None,
    control_id: int | None = None,
) -> ControlDefinition | UnrenderedTemplateControl:
    """Resolve raw or template-backed input into a validated control or unrendered template."""
    if isinstance(control_input, TemplateControlInput):
        if can_render_template(control_input):
            enabled = (
                True if current_payload is None else _enabled_from_stored_payload(current_payload)
            )
            return await _render_and_validate_template_input(
                control_input,
                db=db,
                namespace_key=namespace_key,
                enabled=enabled,
            )

        # Incomplete values - only allowed for new controls or already-unrendered
        # templates.  Updating a rendered control with incomplete values is
        # rejected to prevent silently stripping rendered fields.
        current_is_rendered = (
            current_payload is not None
            and isinstance(current_payload, dict)
            and current_payload.get("condition") is not None
        )
        if current_is_rendered:
            # Force a full render attempt so the caller gets a clear error
            # about which required parameters are missing.
            enabled = _enabled_from_stored_payload(current_payload)
            return await _render_and_validate_template_input(
                control_input,
                db=db,
                namespace_key=namespace_key,
                enabled=enabled,
            )

        validate_template_structure(control_input.template)
        validate_partial_template_values(
            control_input.template, control_input.template_values,
        )
        return UnrenderedTemplateControl(
            template=control_input.template,
            template_values=dict(control_input.template_values),
            enabled=False,
        )

    if current_payload is not None and _is_template_backed_payload(current_payload):
        if control_id is None:
            raise RuntimeError("control_id is required for template-backed raw updates")
        raise _template_backed_raw_update_conflict(control_id)

    await _validate_control_definition(
        control_input,
        db,
        namespace_key=namespace_key,
    )
    return control_input


async def _validate_control_definition(
    control_def: ControlDefinition,
    db: AsyncSession,
    *,
    namespace_key: str,
) -> None:
    """Validate evaluator config for definitions referencing known global evaluators.

    Agent-scoped evaluators must exist on the referenced agent. Builtin and external
    names that are not loaded in this process are accepted without config checks.
    """
    available_evaluators = list_evaluators()
    agent_data_by_name: dict[str, AgentData] = {}
    for field_prefix, leaf in iter_condition_leaves_with_paths(
        control_def.condition,
        path="data.condition",
    ):
        leaf_parts = leaf.leaf_parts()
        if leaf_parts is None:
            continue
        _, evaluator_spec = leaf_parts

        evaluator_ref = evaluator_spec.name
        parsed = parse_evaluator_ref_full(evaluator_ref)

        if parsed.type == "agent":
            agent_namespace = parsed.namespace
            if agent_namespace is None:
                continue

            agent_data = agent_data_by_name.get(agent_namespace)
            if agent_data is None:
                agent_result = await db.execute(
                    select(Agent).where(
                        Agent.name == agent_namespace,
                        Agent.namespace_key == namespace_key,
                    )
                )
                agent = agent_result.scalars().first()
                if agent is None:
                    raise NotFoundError(
                        error_code=ErrorCode.AGENT_NOT_FOUND,
                        detail=f"Agent '{agent_namespace}' not found",
                        resource="Agent",
                        resource_id=agent_namespace,
                        hint=(
                            "Ensure the agent exists before creating controls "
                            "that reference its evaluators."
                        ),
                    )

                try:
                    agent_data = AgentData.model_validate(agent.data)
                except ValidationError as e:
                    raise APIValidationError(
                        error_code=ErrorCode.CORRUPTED_DATA,
                        detail=f"Agent '{parsed.namespace}' has invalid data",
                        resource="Agent",
                        errors=[
                            ValidationErrorItem(
                                resource="Agent",
                                field=format_field_path(err.get("loc", ())),
                                code=err.get("type", "validation_error"),
                                message=err.get("msg", "Validation failed"),
                            )
                            for err in e.errors()
                        ],
                    ) from e
                agent_data_by_name[agent_namespace] = agent_data

            evaluator = next(
                (e for e in (agent_data.evaluators or []) if e.name == parsed.local_name),
                None,
            )
            if evaluator is None:
                available = [e.name for e in (agent_data.evaluators or [])]
                raise APIValidationError(
                    error_code=ErrorCode.EVALUATOR_NOT_FOUND,
                    detail=(
                        f"Evaluator '{parsed.local_name}' is not registered "
                        f"with agent '{agent_namespace}'"
                    ),
                    resource="Evaluator",
