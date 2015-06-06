"""Agent Control steering integration for Strands."""

from __future__ import annotations

import logging
from typing import Any

from agent_control_models.controls import ControlMatch

import agent_control
from agent_control import ControlViolationError

try:
    from strands.experimental.steering import (  # type: ignore[import-not-found]
        Guide,
        Proceed,
        SteeringHandler,
    )
except Exception as exc:  # pragma: no cover - optional dependency
    raise RuntimeError(
        "Strands integration requires strands-agents. "
        "Install with: agent-control-sdk[strands-agents]."
    ) from exc

logger = logging.getLogger(__name__)


class AgentControlSteeringHandler(SteeringHandler):
    """Agent Control steering integration.

    Converts Agent Control steer matches into Strands Guide() actions.
    Deny matches raise ControlViolationError.
    """

    name = "agent-control-steering"

    def __init__(self, agent_name: str, enable_logging: bool = True) -> None:
        super().__init__()
        self.agent_name = agent_name
        self.enable_logging = enable_logging
        self.steers_applied = 0
        self.last_steer_info: dict[str, Any] | None = None

    async def steer_after_model(
        self, *, agent: Any, message: Any, stop_reason: Any, **kwargs: Any
    ) -> Guide | Proceed:
        if self.enable_logging:
            logger.debug("agent=<%s> | steering evaluation started", self.agent_name)

        input_text = self._extract_input(kwargs)
        context = self._extract_context(kwargs)
        output_text = self._extract_output(message)

        if self.enable_logging:
            logger.debug(
                "agent=<%s>, output_len=<%d> | checking output",
                self.agent_name,
                len(output_text),
            )

        try:
            result = await agent_control.evaluate_controls(
                step_name="check_after_model",
                input=input_text,
                output=output_text,
                context=context,
                step_type="llm",
                stage="post",
                agent_name=self.agent_name,
            )

            if result.errors:
                error_names = ", ".join(
                    e.control_name for e in result.errors if getattr(e, "control_name", None)
                )
                logger.error(
                    "agent=<%s> | steering evaluation failed; blocking execution",
                    self.agent_name,
                )
                raise RuntimeError(
                    "Steering evaluation failed; execution blocked for safety. "
