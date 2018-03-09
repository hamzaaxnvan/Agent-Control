"""Configuration for list evaluator."""

from typing import Literal

from pydantic import Field, field_validator

from agent_control_evaluators._base import EvaluatorConfig


class ListEvaluatorConfig(EvaluatorConfig):
    """Configuration for list evaluator."""

