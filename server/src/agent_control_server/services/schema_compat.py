"""JSON Schema compatibility checking for evaluator schemas.

Determines if a new schema is backward-compatible with an existing schema.
Used during initAgent to reject breaking changes.

Compatibility Rules:
- Adding new optional properties -> compatible
- Adding new required properties -> incompatible
- Removing properties -> incompatible
- Changing property types -> incompatible
- Changing required to optional -> compatible
- Changing optional to required -> incompatible
- Nested object changes checked recursively
"""

from typing import Any


def check_schema_compatibility(
    old_schema: dict[str, Any],
    new_schema: dict[str, Any],
    path: str = "",
) -> tuple[bool, list[str]]:
    """Check if new_schema is backward-compatible with old_schema.

    Args:
        old_schema: Existing JSON Schema
        new_schema: New JSON Schema to compare
        path: Property path for error messages (used in recursion)

    Returns:
        Tuple of (is_compatible, list of error messages)
    """
    # Short-circuit for identical schemas
    if old_schema == new_schema:
        return True, []

    errors: list[str] = []

    # Empty schemas are always compatible
    if not old_schema:
        return True, []

    # Get properties from both schemas
    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})
    old_required = set(old_schema.get("required", []))
    new_required = set(new_schema.get("required", []))

    def _prop_path(name: str) -> str:
        return f"{path}.{name}" if path else name

    # Check for removed properties
    removed = set(old_props.keys()) - set(new_props.keys())
    for prop in sorted(removed):
        errors.append(f"Removed property: '{_prop_path(prop)}'")

    # Check for type changes and nested compatibility on existing properties
    for prop_name in old_props:
        if prop_name not in new_props:
            continue  # Already reported as removed

        old_prop = old_props[prop_name]
        new_prop = new_props[prop_name]
        prop_path = _prop_path(prop_name)

        old_type = _get_type(old_prop)
