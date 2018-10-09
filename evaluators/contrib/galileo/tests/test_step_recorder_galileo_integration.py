"""Cross-package check: StepRecorder trees feed the Galileo record factory."""

from __future__ import annotations

from agent_control import record_step
from agent_control_evaluator_galileo.records.factory import record_from_step as _record_from_step


def test_recorder_built_trace_matches_demo_shape():
    """A trace with one llm/tool/retriever child each builds a 3-span Trace."""

    def policy_search(query: str) -> dict:
        return {"docs": ["policy-1"]}

