"""Configuration model for the TypeSafe Jev (System One) evaluator.

One control declares a map of questions. Jev evaluates every question in a
single request, so asking several costs about the same latency as asking one.

Each question can carry its own operator and threshold. A question with a
threshold decides: it is an input to ``decide.combine``, which says whether
one deciding question tripping is enough, or whether all of them must trip.
A question without a threshold is asked and recorded only. It is not an input,
so it can neither fire the control nor stop it firing.

``any`` and ``all`` are the only way questions combine here. A rule that needs
more, such as different evaluators or nested logic, composes in the engine's
and/or/not condition trees instead.
"""

from __future__ import annotations

from typing import Literal

from agent_control_evaluators import EvaluatorConfig
from pydantic import BaseModel, ConfigDict, Field, model_validator

JevQuestionType = Literal["noul", "score", "choice"]
JevOperator = Literal["gt", "gte", "lt", "lte", "eq", "ne", "contains"]
JevPayloadField = Literal["input", "output"]

NUMERIC_OPERATORS = frozenset({"gt", "gte", "lt", "lte"})
TEXT_OPERATORS = frozenset({"eq", "ne", "contains"})

DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"


def coerce_number(value: object) -> float | None:
    """Return a float for JSON scalars that compare numerically, else None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


class JevQuestion(BaseModel):
    """One typed question sent to Jev.

    Attributes:
        type: Which TypeSafe primitive to ask.
        instructions: The question text.
        criteria: Meaning of each outcome. A noul takes an optional true/false
            mapping, a choice takes an option-to-description mapping, and a
            score takes an ordered list of rubric levels. The wording matters:
            a bare list of level names scores differently from a described one.
        operator: Comparison applied to this question's answer.
        threshold: Value the operator compares against. Leave it unset to ask
            the question for the record without letting it affect the decision.
    """

    model_config = ConfigDict(extra="forbid")

    type: JevQuestionType = Field(
        default="noul", description="Which TypeSafe primitive to ask: noul, score, or choice."
    )
    instructions: str = Field(min_length=1, description="The question text sent to Jev.")
    criteria: dict[str, str] | list[str] | None = Field(
        default=None,
        description=(
            "Meaning of each outcome. The shape depends on type. "
            'noul: {"true": "...", "false": "..."} and optional. '
            'score: ["level 0", "level 1", ...] and required. '
            'choice: {"option": "description", ...} and required.'
        ),
    )
    operator: JevOperator = Field(
        default="gte", description="Comparison applied to this question's answer."
    )
    threshold: float | int | str | None = Field(
        default=None,
        description=(
            "Value the operator compares against. Unset means the question is "
            "asked and recorded but does not affect the decision."
        ),
    )

    @model_validator(mode="after")
    def validate_question(self) -> JevQuestion:
        """Reject criteria and operator combinations the API or the answer rejects."""
        if self.type == "choice":
            if not isinstance(self.criteria, dict) or len(self.criteria) < 2:
                raise ValueError("a choice question requires criteria with 2 or more options")
            if self.threshold is not None and self.operator not in TEXT_OPERATORS:
                raise ValueError(
                    f"a choice question requires a text operator {sorted(TEXT_OPERATORS)}"
                )
        elif self.type == "score":
