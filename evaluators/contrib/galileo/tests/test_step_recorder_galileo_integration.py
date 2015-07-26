"""Cross-package check: StepRecorder trees feed the Galileo record factory."""

from __future__ import annotations

from agent_control import record_step
from agent_control_evaluator_galileo.records.factory import record_from_step as _record_from_step


def test_recorder_built_trace_matches_demo_shape():
    """A trace with one llm/tool/retriever child each builds a 3-span Trace."""

    def policy_search(query: str) -> dict:
        return {"docs": ["policy-1"]}

    def account_lookup(account_id: str) -> dict:
        return {"balance": 500}

    def banking_llm(prompt: str) -> str:
        return f"response: {prompt}"

    with record_step("trace", "banking_trace", input={"request": "r1"}) as trace:
        trace.call(
            policy_search, query="refund policy", step_type="retriever", step_name="policy_search"
        )
        trace.call(
            account_lookup, account_id="acct-1", step_type="tool", step_name="account_lookup"
        )
        trace.call(banking_llm, "draft a reply", step_type="llm", step_name="banking_llm")
        trace.output = {"status": "done"}
