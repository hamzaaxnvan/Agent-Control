"""Tests for the shared Agent Control to Galileo record factory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

import pytest
from agent_control_evaluator_galileo.records import (
    GalileoRecordNormalizer,
    RecordFactoryError,
    UnsupportedStepTypeError,
    build_galileo_record,
    build_record,
    record_from_step,
)
from agent_control_models import Step
from galileo_core.schemas.logging.llm import Message
from galileo_core.schemas.logging.session import Session
from galileo_core.schemas.logging.span import LlmSpan, RetrieverSpan, ToolSpan
from galileo_core.schemas.logging.step import BaseStep
from galileo_core.schemas.logging.trace import Trace
from galileo_core.schemas.shared.content_parts import FileContentPart, TextContentPart
from galileo_core.schemas.shared.document import Document
from galileo_core.schemas.shared.records import BaseRecord, RecordTypeAdapter
from pydantic import BaseModel, Field


def test_required_galileo_core_public_exports_are_importable() -> None:
    assert all((LlmSpan, ToolSpan, RetrieverSpan, Trace, Session, Document, Message))


def test_factory_records_are_serializable_concrete_base_steps() -> None:
    # Given: one record of each type accepted by the Galileo factory
    records = [
        record_from_step(Step(type="llm", name="answer", input="question", output="answer")),
        record_from_step(Step(type="tool", name="search", input={"query": "q"}, output="result")),
        record_from_step(
            Step(type="retriever", name="retrieve", input="question", output=["document"])
        ),
        record_from_step(
            Step(
                type="trace",
                name="request",
                input="question",
                output="answer",
                children=[Step(type="llm", name="answer", input="question")],
            )
        ),
        record_from_step(
            Step(
                type="session",
                name="conversation",
                input="question",
                children=[
                    Step(
                        type="trace",
                        name="request",
                        input="question",
                        children=[Step(type="llm", name="answer", input="question")],
                    )
                ],
            )
        ),
    ]

    # When: each concrete Galileo step is serialized and parsed back through its own schema
    rebuilt = [
        type(record).model_validate(record.model_dump(mode="json", exclude_none=True))
        for record in records
    ]

    # Then: every concrete class remains a BaseStep and keeps its discriminator and children
    assert all(isinstance(record, BaseStep) for record in records)
    assert all(isinstance(record, BaseStep) for record in rebuilt)
    assert [record.type.value for record in rebuilt] == [
        "llm",
        "tool",
        "retriever",
        "trace",
        "session",
    ]
    assert isinstance(rebuilt[3], Trace)
    assert isinstance(rebuilt[4], Session)
    assert isinstance(rebuilt[3].spans[0], LlmSpan)
    assert isinstance(rebuilt[4].traces[0].spans[0], LlmSpan)


def test_factory_steps_convert_to_core_records_after_execution_ids_are_added() -> None:
    # Given: each root subtype emitted by the factory, plus caller-supplied IDs
    steps = [
        record_from_step(Step(type="llm", name="answer", input="question", output="answer")),
        record_from_step(Step(type="tool", name="search", input={"query": "q"}, output="result")),
        record_from_step(
            Step(type="retriever", name="retrieve", input="question", output=["document"])
        ),
        record_from_step(
            Step(type="trace", name="request", input="question", children=[])
        ),
        record_from_step(
            Step(type="session", name="conversation", input="question", children=[])
        ),
    ]
    project_id = uuid4()
    run_id = uuid4()
    session_id = uuid4()
    trace_id = uuid4()
    rebuilt_records: list[BaseRecord] = []

    # When: add execution IDs and relationships, then apply Galileo Core's record discriminator
    for step in steps:
        step_id = uuid4()
        values = step.model_dump(
            mode="python",
            exclude={
                "id",
                "project_id",
                "run_id",
                "session_id",
                "trace_id",
                "parent_id",
                "spans",
                "traces",
            },
        )
        values.update(id=step_id, project_id=project_id, run_id=run_id, type=step.type)
        if isinstance(step, Session):
            values["session_id"] = step_id
        elif isinstance(step, Trace):
            values.update(session_id=session_id, trace_id=step_id)
        else:
            values.update(session_id=session_id, trace_id=trace_id, parent_id=trace_id)
        rebuilt_records.append(RecordTypeAdapter.validate_python(values))

    # Then: the concrete step payloads satisfy Galileo Core's stored-record schemas
    assert all(isinstance(record, BaseRecord) for record in rebuilt_records)
    assert [record.type.value for record in rebuilt_records] == [
        "llm",
        "tool",
        "retriever",
        "trace",
        "session",
    ]


def test_llm_messages_use_public_canonical_validation() -> None:
    record = record_from_step(
        Step(
            type="llm",
            name="answer",
            input=[{"role": "user", "content": "question"}],
            output={"role": "assistant", "content": "answer"},
            ground_truth={"expected": "answer"},
        )
    )

    assert isinstance(record, LlmSpan)
    assert record.input[0].role.value == "user"
    assert record.output.role.value == "assistant"
    assert record.dataset_output == json.dumps({"expected": "answer"})


@pytest.mark.parametrize(
    ("source", "expected_messages"),
    [
        ("A plain prompt", None),
        (
            '[{"role": "user", "content": "question"}]',
            [{"role": "user", "content": "question"}],
        ),
        (
            "{'messages': [{'role': 'user', 'content': 'question'}]}",
            [{"role": "user", "content": "question"}],
        ),
        ("{'messages': [", None),
        ('{"content": "document without a role"}', None),
        ('[{"content": "document without a role"}]', None),
    ],
)
def test_llm_string_input_only_parses_role_bearing_message_shapes(
    source: str,
    expected_messages: list[dict[str, str]] | None,
) -> None:
    record = record_from_step(Step(type="llm", name="answer", input=source))

    assert isinstance(record, LlmSpan)
    if expected_messages is None:
        assert len(record.input) == 1
        assert record.input[0].content == source
    else:
        assert [
            {"role": message.role.value, "content": message.content}
            for message in record.input
        ] == expected_messages

    restored = LlmSpan.model_validate(record.model_dump(mode="json", exclude_none=True))
    assert [message.content for message in restored.input] == [
        message.content for message in record.input
    ]


def test_llm_mapping_with_messages_key_becomes_public_message_models() -> None:
    record = record_from_step(
        Step(
            type="llm",
            name="answer",
            input={"messages": [{"role": "user", "content": "question"}]},
        )
    )

    assert isinstance(record, LlmSpan)
    assert [message.role.value for message in record.input] == ["user"]
    restored = LlmSpan.model_validate(record.model_dump(mode="json", exclude_none=True))
    assert [message.content for message in restored.input] == ["question"]


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("answer", "answer"),
        ({"role": "assistant", "content": "answer"}, "answer"),
    ],
)
def test_llm_scalar_and_dictionary_outputs_match_sdk(
    output: object,
    expected: str,
) -> None:
    record = record_from_step(Step(type="llm", name="answer", input="question", output=output))

    assert isinstance(record, LlmSpan)
    assert record.output.content == expected


@pytest.mark.parametrize(
    "output",
    [
        [{"role": "assistant", "content": "first"}],
        [
            {"role": "assistant", "content": "first"},
            {"role": "assistant", "content": "second"},
        ],
    ],
)
def test_llm_sequence_outputs_are_one_json_string_without_dropping_values(
    output: list[dict[str, str]],
) -> None:
    record = record_from_step(Step(type="llm", name="answer", input="question", output=output))

    assert isinstance(record, LlmSpan)
    assert record.output.role.value == "assistant"
    assert json.loads(record.output.content) == output


def test_llm_tuple_output_uses_the_same_sdk_serializer() -> None:
    output = ({"role": "assistant", "content": "first"}, {"role": "assistant", "content": "second"})

    record = record_from_step(Step(type="llm", name="answer", input="question", output=output))

    assert isinstance(record, LlmSpan)
    assert record.output.content == json.dumps(list(output))
    assert json.loads(record.output.content) == list(output)


def test_selected_mapping_and_output_payload_are_preserved() -> None:
    step = Step(type="llm", name="answer", input="base input", output="base output")

    selected_record = build_record(
        {"input": "selected input", "output": "selected output"}, step
    )
    output_record = build_record("selected output", step, payload_field="output")

    assert isinstance(selected_record, LlmSpan)
    assert isinstance(output_record, LlmSpan)
    assert selected_record.input[0].content == "selected input"
    assert selected_record.output.content == "selected output"
    assert output_record.output.content == "selected output"


def test_tool_values_are_json_strings_and_missing_output_stays_missing() -> None:
    record = record_from_step(
        Step(type="tool", name="search", input={"query": "q"}, output={"hits": [1, 2]})
    )
    missing_output = record_from_step(Step(type="tool", name="search", input={"query": "q"}))

    assert isinstance(record, ToolSpan)
    assert json.loads(record.input) == {"query": "q"}
    assert json.loads(record.output or "") == {"hits": [1, 2]}
    assert missing_output.output is None

