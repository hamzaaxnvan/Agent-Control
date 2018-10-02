"""Typed configuration for the DefenseClaw OPA-policy evaluator."""

from __future__ import annotations

from typing import Literal

from agent_control_evaluators import EvaluatorConfig
from pydantic import BaseModel

from ..common import STRICT_PROVIDER_CONFIG, Severity


class OpaPolicy(BaseModel):
    """DefenseClaw OPA policy settings supported by the v1 contract.

    See https://cisco-ai-defense.github.io/docs/defenseclaw/policy for the policy contract.
    """

    model_config = STRICT_PROVIDER_CONFIG

    domain: Literal["guardrail"] = "guardrail"
    block_at: Severity = "HIGH"
    alert_at: Severity = "MEDIUM"
    cisco_trust_level: Literal["full"] = "full"

