"""Data selection logic for rule evaluation."""
from typing import Any

from agent_control_models import Step


def select_data(step: Step, path: str) -> Any:
    """
    Select data from the step using a dot-notation path.

    Args:
