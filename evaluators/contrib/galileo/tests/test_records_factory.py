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

    expected = ToolSpan(
        name="search",
        input=json.dumps({"query": "q"}),
        output=json.dumps({"hits": [1, 2]}),
    )
    assert type(record) is type(expected)
    assert record.input == expected.input
    assert record.output == expected.output


@pytest.mark.parametrize(
    "output",
    [None, "text", {"content": "document"}, {"invalid": True}, 42, ["one", "two"]],
)
def test_retriever_matches_sdk_document_coercion(output: object) -> None:
    record = record_from_step(
        Step(type="retriever", name="retrieve", input="question", output=output)
    )
    assert isinstance(record, RetrieverSpan)
    if output is None or isinstance(output, int):
        assert [document.content for document in record.output] == [""]
    elif isinstance(output, str):
        assert [document.content for document in record.output] == [output]
    elif isinstance(output, dict) and "content" in output:
        assert [document.content for document in record.output] == [output["content"]]
    elif output == ["one", "two"]:
        assert [document.content for document in record.output] == output
    else:
        assert record.output[0].content == json.dumps(output)


def test_retriever_rejects_mixed_lists_like_the_sdk_helper() -> None:
    output = ["one", {"content": "two"}]

    with pytest.raises(ValueError, match="Invalid document output"):
        record_from_step(Step(type="retriever", name="retrieve", input="question", output=output))


def test_retriever_results_become_documents_with_scalar_metadata_only() -> None:
    record = record_from_step(
        Step(
            type="retriever",
            name="retrieve",
            input="question",
            output=[
                {
                    "content": "context",
                    "metadata": {"score": 0.9, "source": "kb", "nested": {"bad": True}},
                }
            ],
        )
    )

    assert isinstance(record, RetrieverSpan)
    assert record.output[0].content == "context"
    assert record.output[0].metadata == {"score": 0.9, "source": "kb"}


def test_retriever_accepts_the_public_galileo_core_document_model() -> None:
    document = Document(content="context", metadata={"source": "kb"})
    record = RetrieverSpan.model_validate(
        {"name": "retrieve", "input": "question", "output": [document]}
    )

    assert isinstance(record, RetrieverSpan)
    assert record.output[0].content == "context"
    assert record.output[0].metadata == {"source": "kb"}


def test_public_document_metadata_variants_are_supported() -> None:
    document_without_metadata = Document(content="plain")
    document_with_model_metadata = Document.model_validate(
        {"content": "model metadata", "metadata": {"source": "kb"}}
    )

    record = RetrieverSpan.model_validate(
        {
            "input": "question",
            "output": [document_without_metadata, document_with_model_metadata],
        }
    )

    assert isinstance(record, RetrieverSpan)
    assert [document.model_dump() for document in record.output] == [
        {"content": "plain", "metadata": {}},
        {"content": "model metadata", "metadata": {"source": "kb"}},
    ]


def test_nested_trace_and_session_records_are_preserved() -> None:
    trace = record_from_step(
        Step(
            type="trace",
            name="request",
            input="question",
            children=[
                Step(
                    type="tool",
                    name="search",
                    input={"q": "x"},
                    children=[Step(type="tool", name="nested", input={"q": "y"})],
                ),
                Step(type="retriever", name="retrieve", input="x", output=[]),
            ],
        )
    )
    session = record_from_step(
        Step(
            type="session",
            name="conversation",
            input="question",
            children=[Step(type="trace", name="request", input="question", children=[
                Step(type="tool", name="search", input={"q": "x"}, children=[
                    Step(type="tool", name="nested", input={"q": "y"})
                ]),
                Step(type="retriever", name="retrieve", input="x", output=[]),
            ])],
        )
    )

    assert isinstance(trace, Trace)
    assert [type(span) for span in trace.spans] == [ToolSpan, RetrieverSpan]
    assert trace.spans[0].spans[0].name == "nested"
    assert isinstance(session, Session)
    assert len(session.traces) == 1
    assert session.traces[0].spans[0].name == "search"


def test_public_model_dump_preserves_canonical_fields() -> None:
    created_at = datetime(2024, 1, 1, tzinfo=UTC)
    llm_source = LlmSpan(
        input=[{"role": "user", "content": "question"}],
        output="answer",
        redacted_input=[{"role": "user", "content": "redacted question"}],
        redacted_output={"role": "assistant", "content": "redacted answer"},
        created_at=created_at,
        metrics={"duration_ns": 3},
        events=[{"type": "reasoning"}],
        model="model",
        temperature=0.2,
        finish_reason="stop",
    )
    tool_source = ToolSpan(
        input="input",
        output="output",
        redacted_input="redacted input",
        redacted_output="redacted output",
        created_at=created_at,
        metrics={"duration_ns": 4},
        tool_call_id="call-1",
    )
    retriever_source = RetrieverSpan(
        input="query",
        output=[{"content": "document"}],
        redacted_input="redacted query",
        redacted_output=[{"content": "redacted document"}],
        created_at=created_at,
        metrics={"duration_ns": 5},
    )
    trace_source = Trace(
        input="input",
        output="output",
        redacted_input="redacted input",
        redacted_output="redacted output",
        created_at=created_at,
        metrics={"duration_ns": 6},
        spans=[],
    )
    session_source = Session(
        input=[{"role": "user", "content": "input"}],
        output=[{"content": "output"}],
        redacted_input=[{"role": "user", "content": "redacted input"}],
        redacted_output=[{"content": "redacted output"}],
        created_at=created_at,
        metrics={"duration_ns": 7},
        traces=[],
    )

    rebuilt_llm = LlmSpan.model_validate(llm_source.model_dump(mode="json", exclude_none=True))
    rebuilt_tool = ToolSpan.model_validate(tool_source.model_dump(mode="json", exclude_none=True))
    rebuilt_retriever = RetrieverSpan.model_validate(
        retriever_source.model_dump(mode="json", exclude_none=True)
    )
    rebuilt_trace = Trace.model_validate(trace_source.model_dump(mode="json", exclude_none=True))
    rebuilt_session = Session.model_validate(
        session_source.model_dump(mode="json", exclude_none=True)
    )

    assert isinstance(rebuilt_llm, LlmSpan)
    assert rebuilt_llm.redacted_input[0].content == "redacted question"
    assert rebuilt_llm.redacted_output.content == "redacted answer"
    assert rebuilt_llm.created_at == created_at
    assert rebuilt_llm.metrics.duration_ns == 3
    assert rebuilt_llm.events == llm_source.events
    assert rebuilt_llm.model == "model"
    assert rebuilt_llm.temperature == 0.2
    assert rebuilt_llm.finish_reason == "stop"
    assert isinstance(rebuilt_tool, ToolSpan)
    assert rebuilt_tool.redacted_input == "redacted input"
    assert rebuilt_tool.redacted_output == "redacted output"
    assert rebuilt_tool.metrics.duration_ns == 4
    assert rebuilt_tool.tool_call_id == "call-1"
    assert isinstance(rebuilt_retriever, RetrieverSpan)
    assert rebuilt_retriever.redacted_input == "redacted query"
    assert rebuilt_retriever.redacted_output[0].content == "redacted document"
    assert rebuilt_retriever.metrics.duration_ns == 5
    assert isinstance(rebuilt_trace, Trace)
    assert rebuilt_trace.redacted_input == "redacted input"
    assert rebuilt_trace.redacted_output == "redacted output"
    assert rebuilt_trace.metrics.duration_ns == 6
    assert isinstance(rebuilt_session, Session)
    assert rebuilt_session.redacted_input[0].content == "redacted input"
    assert rebuilt_session.redacted_output[0].content == "redacted output"
    assert rebuilt_session.metrics.duration_ns == 7


def test_trace_public_content_parts_are_not_reserialized() -> None:
    source = Trace(
        input=[{"type": "text", "text": "input"}],
        output=[{"type": "text", "text": "output"}],
        redacted_input=[{"type": "text", "text": "redacted input"}],
        redacted_output=[{"type": "text", "text": "redacted output"}],
        spans=[],
    )

    rebuilt = Trace.model_validate(source.model_dump(mode="json", exclude_none=True))

    assert isinstance(rebuilt, Trace)
    assert rebuilt.model_dump(mode="json", exclude_none=True) == source.model_dump(
        mode="json", exclude_none=True
    )

    file_source = Trace(
        input=[{"type": "file", "file_id": str(uuid4())}],
        output=[{"type": "file", "file_id": str(uuid4())}],
        spans=[],
    )
    file_rebuilt = Trace.model_validate(file_source.model_dump(mode="json", exclude_none=True))
    assert isinstance(file_rebuilt, Trace)
    assert file_rebuilt.model_dump(mode="json", exclude_none=True) == file_source.model_dump(
        mode="json", exclude_none=True
    )


def test_malformed_trace_content_parts_follow_sdk_serialization() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Trace.model_validate({"input": "input", "output": [1], "spans": []})
    with pytest.raises(ValidationError):
        Trace.model_validate(
            {
                "input": "input",
                "output": [{"type": "file", "file_id": "not-a-uuid"}],
                "spans": [],
            }
        )


def test_context_hierarchy_fields_are_rejected_and_metadata_remains_supported() -> None:
    for hierarchy_field in ("children", "spans", "traces"):
        with pytest.raises(RecordFactoryError, match="Step.context cannot define.*Step.children"):
            record_from_step(
                Step(
                    type="tool",
                    name="tool",
                    input={"q": "input"},
                    context={hierarchy_field: []},
                )
            )
    metadata_record = record_from_step(
        Step(
            type="tool",
            name="tool",
            input={"q": "input"},
            context={"metadata": {"provider": "test"}, "request_id": "abc"},
        )
    )
    assert isinstance(metadata_record, ToolSpan)
    assert metadata_record.user_metadata == {"provider": "test"}


def test_trace_structured_values_are_normalized_without_losing_messages() -> None:
    trace_input = {"question": "hello"}
    trace_output = [{"role": "assistant", "content": "answer"}]
    record = record_from_step(
        Step(
            type="trace",
            name="request",
            input=trace_input,
            output=trace_output,
            children=[],
        )
