"""Base models and utilities for Agent Control."""

from typing import Any

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict


class BaseModel(PydanticBaseModel):
    """
    Base model for all Agent Control models.

    Provides common configuration and utilities for JSON serialization
    and Pydantic compatibility.
    """

    model_config = ConfigDict(
        # Allow both snake_case and camelCase in JSON
        populate_by_name=True,
        # Use enum values in JSON output
        use_enum_values=True,
        # Validate on assignment
        validate_assignment=True,
