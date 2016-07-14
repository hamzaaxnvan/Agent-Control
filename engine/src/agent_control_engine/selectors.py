"""Data selection logic for rule evaluation."""
from typing import Any

from agent_control_models import Step


def select_data(step: Step, path: str) -> Any:
    """
    Select data from the step using a dot-notation path.

    Args:
        step: The Step payload
        path: Dot-notation path (e.g., 'input', 'input.query', 'context.user_id')

    Returns:
        The selected value, or None if the path doesn't exist.
    """
    if not path or path == "*":
        return step.model_dump(mode="json")

    parts = path.split(".")
    current: Any = step
