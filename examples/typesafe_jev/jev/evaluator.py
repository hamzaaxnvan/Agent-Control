"""TypeSafe Jev (System One) evaluator for Agent Control."""

from __future__ import annotations

import json
import logging
import os
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any, NamedTuple

from agent_control_evaluators import (
    Evaluator,
    EvaluatorMetadata,
    register_evaluator,
)
from agent_control_models import EvaluatorResult

from .client import TYPESAFE_HTTPX_AVAILABLE, TypeSafeClient, build_endpoint
from .config import JevQuestion, TypeSafeJevConfig, coerce_number

logger = logging.getLogger(__name__)

# A noul and a score answer with a number, a choice answers with an option name.
AnswerValue = float | str

# Every question's raw answer, keyed by the question id from the config. The
# ids are chosen by whoever writes the control, so this cannot be a TypedDict.
RawAnswers = dict[str, AnswerValue]


class Decision(NamedTuple):
    """How the deciding questions resolved into the one boolean a control needs.

    Attributes:
        matched: Whether the control fires.
        message: Human-readable explanation, surfaced on the control result.
        tripped: Ids of the questions that crossed their own threshold.
        deciding: Ids of every question that carried a threshold, tripped or not.
    """

    matched: bool
    message: str
    tripped: list[str]
    deciding: list[str]


def _resolve_package_version() -> str:
    """Return the installed package version, or a dev fallback during local imports."""
    try:
        return version("agent-control-typesafe-jev-example")
    except PackageNotFoundError:
        return "0.0.0.dev"


_PACKAGE_VERSION = _resolve_package_version()


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


@register_evaluator
class TypeSafeJevEvaluator(Evaluator[TypeSafeJevConfig]):
    """Ask Jev a set of typed questions in one request and decide from the answers.

    Every configured question travels in a single call, because Jev evaluates
    them in parallel and charges only for the extra question tokens. Declaring
    one question is the degenerate case, not a different code path.

    A question with a threshold decides: it is an input to
    ``decide.combine``, which is either ``any`` or ``all``. A question without
    one is recorded only, and is not an input. Rules that ``any`` and ``all``
    cannot express compose in the engine's condition trees instead.
    """

    metadata = EvaluatorMetadata(
        name="typesafe.jev",
        version=_PACKAGE_VERSION,
        description="TypeSafe AI Jev System One typed-question evaluator",
        requires_api_key=True,
        timeout_ms=10000,
    )

    config_model = TypeSafeJevConfig

    def __init__(self, config: TypeSafeJevConfig) -> None:
        """Initialize with validated config.

        The HTTP client is created lazily and then reused. It holds no
        request-scoped state, and httpx.AsyncClient is safe to share across
        concurrent requests, so caching it here keeps the connection alive
        between evaluations instead of paying a TLS handshake per call.
        """
        super().__init__(config)
        self._client: TypeSafeClient | None = None

    @classmethod
    def is_available(cls) -> bool:
        """Report whether httpx is importable."""
        return TYPESAFE_HTTPX_AVAILABLE

    def _build_questions(self) -> dict[str, dict[str, Any]]:
        """Render every configured question into the API's wire shape."""
        questions: dict[str, dict[str, Any]] = {}
        for question_id, question in self.config.questions.items():
            payload: dict[str, Any] = {
                "type": question.type,
                "instructions": question.instructions,
            }
            if question.criteria is not None:
                payload["criteria"] = question.criteria
            questions[question_id] = payload
        return questions

    def _prepare_state(self, data: Any) -> Any:
        """Return the state to send.

        A mapping that carries both sides is narrowed to ``payload_field``.
        Anything else is passed through, because the API accepts a string, an
        object, or an array.
        """
        if isinstance(data, dict) and ("input" in data or "output" in data):
            selected = data.get(self.config.payload_field)
            if selected is not None:
                return selected
        return data

    def _get_client(self) -> TypeSafeClient:
        if self._client is None:
            api_key = os.getenv(self.config.api_key_env)
            if not api_key:
                raise RuntimeError(
                    f"Missing TypeSafe API key in env '{self.config.api_key_env}'. "
                    "Set it on the server."
                )
            self._client = TypeSafeClient(
                api_key=api_key,
                endpoint_url=build_endpoint(self.config.base_url),
                timeout_s=self.get_timeout_seconds(),
            )
        return self._client

    def _raw_answers(self, response: dict[str, Any]) -> RawAnswers:
        """Pull the raw value out of every answer.

        Each answer object carries its value under a key named after the
        question type: a noul under "noul", a score under "score", a choice
        under "choice".

        Args:
            response: The decoded body of one system_one call.

        Returns:
            Every configured question id mapped to its raw answer. A noul and a
            score give a float, a choice gives the chosen option name.

        Raises:
            RuntimeError: The response is missing an answer, or an answer is
                missing the value for its type.
        """
        answers = response.get("answers")
        if not isinstance(answers, dict):
            raise RuntimeError("TypeSafe response has no answers object")

        raw: RawAnswers = {}
        for question_id, question in self.config.questions.items():
            answer = answers.get(question_id)
            if not isinstance(answer, dict):
                raise RuntimeError(f"TypeSafe response has no answer for question {question_id!r}")
            if question.type not in answer:
                raise RuntimeError(
                    f"TypeSafe answer for {question_id!r} has no {question.type!r} field"
                )
            raw[question_id] = answer[question.type]
        return raw

    def _question_matches(self, question: JevQuestion, value: AnswerValue) -> bool:
        """Report whether one answer crosses the line its question was configured with.

        The comparison runs here rather than at the API, so a threshold can be
        retuned without asking the model again.

        Args:
            question: The configured question, carrying its operator and threshold.
            value: That question's raw answer.

        Returns:
