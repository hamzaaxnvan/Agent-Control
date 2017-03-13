"""Tests for reconstructed control-execution events in SDK evaluation flows."""

from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_control import evaluation
from agent_control.evaluation import (
    _build_server_control_lookup,
    _ControlAdapter,
    _has_applicable_prefiltered_server_controls,
    _merge_results,
)
from agent_control.evaluation_events import (
    build_control_execution_events,
    enqueue_observability_events,
    map_applies_to,
)
from agent_control.observability import (
    register_control_event_sink,
    unregister_control_event_sink,
)
from agent_control.settings import configure_settings
from agent_control_models import ControlDefinition, ControlExecutionEvent
from agent_control_telemetry import (
    DEFAULT_CONTROL_EVENT_SINK_NAME,
    REGISTERED_CONTROL_EVENT_SINK_NAME,
)
from agent_control_telemetry.sinks import BaseControlEventSink, SinkResult
from agent_control_telemetry.trace_context import (
    clear_trace_context_provider,
    set_trace_context_provider,
)


class RecordingSink(BaseControlEventSink):
    """Test sink that records delivered control events."""

    def __init__(self) -> None:
        self.received_batches: list[list[ControlExecutionEvent]] = []

    def write_events(self, events: Sequence[ControlExecutionEvent]) -> SinkResult:
        self.received_batches.append(list(events))
        return SinkResult(accepted=len(events), dropped=0)


class TestMapAppliesTo:
    def test_maps_tool_to_tool_call(self):
        assert map_applies_to("tool") == "tool_call"

    def test_maps_llm_to_llm_call(self):
        assert map_applies_to("llm") == "llm_call"

    def test_maps_custom_step_type_to_call_type(self):
        assert map_applies_to("retriever") == "retriever_call"
        assert map_applies_to("trace") == "trace_call"
        assert map_applies_to("session") == "session_call"

    def test_custom_step_type_round_trips_in_observability_query(self):
        from agent_control_models import EventQueryRequest

        request = EventQueryRequest(applies_to=["retriever_call", "trace_call"])

        assert request.model_dump(mode="json")["applies_to"] == [
            "retriever_call",
            "trace_call",
        ]


class TestMergeResults:
    def _make_response(self, **kwargs):
        from agent_control_models import EvaluationResponse

        defaults = {
            "is_safe": True,
            "confidence": 1.0,
            "reason": None,
            "matches": None,
            "errors": None,
            "non_matches": None,
        }
        defaults.update(kwargs)
        return EvaluationResponse(**defaults)

    def _make_match(
        self,
        control_id,
        control_name="ctrl",
        action="observe",
        matched=True,
        metadata=None,
    ):
        from agent_control_models import ControlMatch, EvaluatorResult

        return ControlMatch(
            control_id=control_id,
            control_name=control_name,
            action=action,
            result=EvaluatorResult(matched=matched, confidence=0.9, metadata=metadata),
        )

    def test_combines_matches_errors_and_non_matches(self):
        local = self._make_response(
            matches=[self._make_match(1)],
            errors=[self._make_match(2, matched=False)],
        )
        server = self._make_response(non_matches=[self._make_match(3, matched=False)])

        result = _merge_results(local, server)

        assert [match.control_id for match in result.matches or []] == [1]
        assert [match.control_id for match in result.errors or []] == [2]
        assert [match.control_id for match in result.non_matches or []] == [3]


class TestEvaluationHelpers:
    def test_build_server_control_lookup_skips_unparseable_controls(self):
        lookup = _build_server_control_lookup(
            [
                {
                    "id": 1,
                    "name": "ctrl-1",
                    "control": {
                        "condition": {
                            "evaluator": {"name": "regex", "config": {"pattern": "test"}},
                            "selector": {"path": "input"},
                        },
                        "action": {"decision": "observe"},
                        "execution": "server",
                    },
                },
                {
                    "id": 2,
                    "name": "ctrl-2",
                    "control": {
                        "condition": {"selector": {"path": "input"}},
                        "action": {"decision": "observe"},
                        "execution": "server",
                    },
                },
            ]
        )

        assert list(lookup.keys()) == [1]

    def test_has_applicable_prefiltered_server_controls_returns_true_for_malformed_payload(self):
        from agent_control_models import EvaluationRequest

        request = EvaluationRequest(
            agent_name="agent-000000000001",
            step={"type": "llm", "name": "test-step", "input": "hello"},
            stage="pre",
        )

        assert _has_applicable_prefiltered_server_controls(
            [
                {
                    "id": 1,
                    "name": "bad-server-ctrl",
                    "control": {
                        "condition": {"selector": {"path": "input"}},
                        "action": {"decision": "observe"},
                        "execution": "server",
                    },
                }
            ],
            request,
        ) is True






class TestBuildControlExecutionEvents:
    def _make_control(self, id, name, condition):
        return _ControlAdapter(
            id=id,
            name=name,
            control=ControlDefinition(
                execution="sdk",
                condition=condition,
                action={"decision": "observe"},
            ),
        )

    def _make_request(self, step_type="llm"):
        from agent_control_models import EvaluationRequest

        step_input = {"query": "hello"} if step_type == "tool" else "hello"
        return EvaluationRequest(
            agent_name="agent-000000000001",
            step={"type": step_type, "name": "test-step", "input": step_input},
            stage="pre",
        )

    def _make_match(
        self,
        control_id,
        control_name="ctrl",
        action="observe",
        matched=True,
        metadata=None,
    ):
        from agent_control_models import ControlMatch, EvaluatorResult

        return ControlMatch(
            control_id=control_id,
            control_name=control_name,
            action=action,
            result=EvaluatorResult(matched=matched, confidence=0.9, metadata=metadata),
        )

    def _make_response(self, matches=None, errors=None, non_matches=None):
        from agent_control_models import EvaluationResponse

        return EvaluationResponse(
            is_safe=not bool(matches),
            confidence=1.0 if not matches else 0.5,
            matches=matches,
            errors=errors,
            non_matches=non_matches,
        )

    def test_builds_events_with_trace_context(self):
        response = self._make_response(matches=[self._make_match(1, "ctrl-1")])
        request = self._make_request()
        control_lookup = {
            1: self._make_control(
                1,
                "ctrl-1",
                {
                    "evaluator": {"name": "regex", "config": {"pattern": "test"}},
                    "selector": {"path": "input"},
                },
            ).control
        }

        events = build_control_execution_events(
            response,
            request,
            control_lookup,
            "trace123",
            "span456",
            "test-agent",
        )

        assert len(events) == 1
        event = events[0]
        assert event.trace_id == "trace123"
        assert event.span_id == "span456"
        assert event.agent_name == "test-agent"
        assert event.evaluator_name == "regex"
        assert event.selector_path == "input"

    def test_builds_custom_type_event_without_llm_classification(self):
        response = self._make_response(matches=[self._make_match(1, "ctrl-1")])
        request = self._make_request(step_type="retriever")
        control_lookup = {
            1: self._make_control(
                1,
                "ctrl-1",
                {
                    "evaluator": {"name": "regex", "config": {"pattern": "test"}},
                    "selector": {"path": "input"},
                },
            ).control
        }

        events = build_control_execution_events(
            response,
            request,
            control_lookup,
            "trace123",
            "span456",
            "test-agent",
        )

        assert events[0].applies_to == "retriever_call"
        assert events[0].model_dump(mode="json")["applies_to"] == "retriever_call"

    def test_resolves_all_selector_paths_into_event_input(self):
        response = self._make_response(
            matches=[
                self._make_match(
                    1,
                    "ctrl-1",
                    metadata={
                        "selected_data": {"prompt": "raw sensitive input"},
                        "selected_data_preview": {
                            "type": "dict",
                            "value": {"prompt": "raw sensitive input"},
                            "truncated": False,
                        },
                        "engine_selected_data": {"prompt": "raw sensitive input"},
                        "engine_selected_data_preview": {
                            "type": "dict",
                            "value": {"prompt": "raw sensitive input"},
                            "truncated": False,
                        },
                    },
                )
            ]
        )
        request = self._make_request()
        control_lookup = {
            1: self._make_control(
                1,
                "ctrl-1",
                {
                    "evaluator": {"name": "regex", "config": {"pattern": "test"}},
                    "selector": {"path": "input"},
                },
            ).control
        }

        events = build_control_execution_events(
            response,
            request,
            control_lookup,
            "trace123",
            "span456",
            "test-agent",
        )

        assert len(events) == 1
        assert "selected_data" not in events[0].metadata
        assert "selected_data_preview" not in events[0].metadata
        assert "engine_selected_data" not in events[0].metadata
        assert "engine_selected_data_preview" not in events[0].metadata
        # The resolved-from-step value for the control's selector path wins over
        # any stale debug preview captured at evaluation time.
        assert events[0].metadata["input"] == {"input": "hello"}

    def test_falls_back_to_selected_data_preview_when_control_definition_is_missing(self):
        response = self._make_response(
            matches=[
                self._make_match(
                    1,
                    "ctrl-1",
                    metadata={
                        "selected_data_preview": {
                            "type": "dict",
                            "value": {"prompt": "raw sensitive input"},
                            "truncated": False,
                        },
