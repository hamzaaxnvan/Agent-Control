"""Tests for the budget evaluator (contrib).

Given/When/Then comment style per reviewer request.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import threading
from typing import Any

import pytest
from pydantic import ValidationError

import agent_control_evaluator_budget.budget.evaluator as budget_evaluator_module
from agent_control_evaluator_budget.budget.config import (
    WINDOW_DAILY,
    WINDOW_MONTHLY,
    WINDOW_WEEKLY,
    BudgetEvaluatorConfig,
    BudgetLimitRule,
    ModelPricing,
)
from agent_control_evaluator_budget.budget.evaluator import (
    BudgetEvaluator,
    _extract_tokens,
    clear_budget_stores,
    get_or_create_store,
)
from agent_control_evaluator_budget.budget.memory_store import (
    InMemoryBudgetStore,
    _build_scope_key,
    _compute_utilization,
    _derive_period_key,
)


@pytest.fixture(autouse=True)
def _clean_store_registry() -> None:
    """Clear the module-level store registry before each test."""
    clear_budget_stores()


def test_metadata_version_matches_distribution_version() -> None:
    assert BudgetEvaluator.metadata.version == version("agent-control-evaluator-budget")


def test_metadata_version_falls_back_without_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_not_found(_: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(budget_evaluator_module, "version", _raise_not_found)

    assert budget_evaluator_module._resolve_package_version() == "0.0.0.dev"


# ---------------------------------------------------------------------------
# InMemoryBudgetStore
# ---------------------------------------------------------------------------


class TestInMemoryBudgetStore:
    @pytest.mark.asyncio
    async def test_single_record_under_limit(self) -> None:
        # Given: store with a $10 daily limit (1000 cents)
        rules = [BudgetLimitRule(limit=1000, window_seconds=WINDOW_DAILY)]
        store = InMemoryBudgetStore(clock=lambda: 1700000000.0)

        # When: record 300 cents of usage
        results = await store.record_and_check(
            rules=rules, scope={}, input_tokens=100, output_tokens=50, cost=300.0
        )

        # Then: not breached, ratio ~0.3
        assert len(results) == 1
        assert not results[0].exceeded
        assert results[0].utilization == pytest.approx(0.3, abs=0.01)

    @pytest.mark.asyncio
    async def test_accumulation_triggers_breach(self) -> None:
        # Given: store with 1000-cent limit
        rules = [BudgetLimitRule(limit=1000)]
        store = InMemoryBudgetStore(clock=lambda: 1700000000.0)

        # When: record 600 + 500 = 1100 cents
        await store.record_and_check(
            rules=rules, scope={}, input_tokens=100, output_tokens=50, cost=600.0
        )
        results = await store.record_and_check(
            rules=rules, scope={}, input_tokens=100, output_tokens=50, cost=500.0
        )

        # Then: exceeded
        assert results[0].exceeded is True
        assert results[0].spent == 1100

    @pytest.mark.asyncio
    async def test_scope_isolation(self) -> None:
        # Given: per-agent limits
        rules = [
            BudgetLimitRule(scope={"agent": "a"}, limit=1000),
            BudgetLimitRule(scope={"agent": "b"}, limit=1000),
        ]
        store = InMemoryBudgetStore(clock=lambda: 1700000000.0)

        # When: agent-a records 900, agent-b records 100
        results_a = await store.record_and_check(
            rules=rules, scope={"agent": "a"}, input_tokens=0, output_tokens=0, cost=900.0
        )
        results_b = await store.record_and_check(
            rules=rules, scope={"agent": "b"}, input_tokens=0, output_tokens=0, cost=100.0
        )

        # Then: agent-a near limit, agent-b well under
        assert results_a[0].spent == 900
        assert results_b[0].spent == 100
        assert not results_b[0].exceeded

    @pytest.mark.asyncio
    async def test_period_isolation(self) -> None:
        # Given: daily limit, clock at two different days
        rules = [BudgetLimitRule(limit=1000, window_seconds=WINDOW_DAILY)]
        day1 = 1700000000.0
        day2 = day1 + WINDOW_DAILY

        # When: record on day 1, then day 2
        store = InMemoryBudgetStore(clock=lambda: day1)
        await store.record_and_check(
            rules=rules, scope={}, input_tokens=0, output_tokens=0, cost=800.0
        )

        store._clock = lambda: day2
        results = await store.record_and_check(
            rules=rules, scope={}, input_tokens=0, output_tokens=0, cost=300.0
        )

        # Then: day 2 is a fresh period
        assert results[0].spent == 300
        assert not results[0].exceeded

    @pytest.mark.asyncio
    async def test_exceeded_exact_limit(self) -> None:
        # Given: 1000-cent limit
        rules = [BudgetLimitRule(limit=1000)]
        store = InMemoryBudgetStore(clock=lambda: 0.0)

        # When: spend exactly 1000
        results = await store.record_and_check(
            rules=rules, scope={}, input_tokens=0, output_tokens=0, cost=1000.0
        )

        # Then: exceeded (>= not >)
        assert results[0].exceeded is True

    @pytest.mark.asyncio
    async def test_token_only_limit(self) -> None:
        # Given: 1000-token limit, no cost limit
        rules = [BudgetLimitRule(limit=1000, limit_unit="tokens")]
        store = InMemoryBudgetStore(clock=lambda: 0.0)

        # When: consume 600+500 = 1100 tokens
        results = await store.record_and_check(
            rules=rules, scope={}, input_tokens=600, output_tokens=500, cost=0.0
        )

        # Then: exceeded
        assert results[0].exceeded is True
        assert results[0].spent_tokens == 1100

    @pytest.mark.asyncio
    async def test_no_matching_rules(self) -> None:
        # Given: rule for agent=summarizer only
        rules = [BudgetLimitRule(scope={"agent": "summarizer"}, limit=1000)]
        store = InMemoryBudgetStore(clock=lambda: 0.0)

        # When: step from agent=other
        results = await store.record_and_check(
            rules=rules, scope={"agent": "other"}, input_tokens=100, output_tokens=50, cost=999.0
        )

        # Then: no snapshots (rule didn't match)
        assert results == []

    @pytest.mark.asyncio
    async def test_group_by_user(self) -> None:
        # Given: global rule with group_by=user_id
        rules = [BudgetLimitRule(group_by="user_id", limit=500)]
        store = InMemoryBudgetStore(clock=lambda: 0.0)

        # When: two users each spend
        await store.record_and_check(
            rules=rules, scope={"user_id": "u1"}, input_tokens=0, output_tokens=0, cost=400.0
        )
        results_u1 = await store.record_and_check(
            rules=rules, scope={"user_id": "u1"}, input_tokens=0, output_tokens=0, cost=200.0
        )
        results_u2 = await store.record_and_check(
            rules=rules, scope={"user_id": "u2"}, input_tokens=0, output_tokens=0, cost=300.0
        )

        # Then: u1 exceeded, u2 not
        assert results_u1[0].exceeded is True
        assert results_u2[0].exceeded is False

    def test_thread_safety(self) -> None:
        # Given: high-limit rule and 10 concurrent threads
        # Each thread calls asyncio.run(store.record_and_check(rules=rules, ...)) -- the async
        # method wraps a sync critical section, so threading.Lock prevents races.
        rules = [BudgetLimitRule(limit=1_000_000)]
        store = InMemoryBudgetStore(clock=lambda: 0.0)
        errors: list[str] = []

        import asyncio

        def record_many() -> None:
            try:
                for _ in range(100):
                    asyncio.run(
                        store.record_and_check(
                            rules=rules, scope={}, input_tokens=1, output_tokens=1, cost=1.0
                        )
                    )
            except Exception as exc:
                errors.append(str(exc))

        # When: 10 threads x 100 calls
        threads = [threading.Thread(target=record_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Then: no errors, totals correct
        assert errors == []
        snap = store.get_snapshot("__global__", _derive_period_key(None, 0.0), limit=1_000_000)
        assert snap.spent_tokens == 2000
        assert snap.spent == 1000

    @pytest.mark.asyncio
    async def test_max_buckets_fail_closed(self) -> None:
        # Given: store limited to 3 buckets with group_by=user_id
        rules = [BudgetLimitRule(group_by="user_id", limit=100_000)]
        store = InMemoryBudgetStore(clock=lambda: 0.0, max_buckets=3)

        # When: 5 different users try to record
        exceeded_count = 0
        for i in range(5):
            results = await store.record_and_check(
                rules=rules, scope={"user_id": f"u{i}"}, input_tokens=1, output_tokens=1, cost=1.0
            )
            if results and results[0].exceeded:
                exceeded_count += 1

        # Then: first 3 succeed, last 2 fail-closed
        assert exceeded_count == 2

    @pytest.mark.asyncio
    async def test_reset_all(self) -> None:
        # Given: store with recorded usage
        rules = [BudgetLimitRule(limit=1000)]
        store = InMemoryBudgetStore(clock=lambda: 0.0)
        await store.record_and_check(
            rules=rules, scope={}, input_tokens=10, output_tokens=10, cost=100.0
        )

        # When: reset all
        store.reset()

        # Then: empty
        snap = store.get_snapshot("__global__", "", limit=1000)
        assert snap.spent == 0

    @pytest.mark.asyncio
    async def test_float_accumulation_precision(self) -> None:
        # Given: store with 1-cent limit
        rules = [BudgetLimitRule(limit=1)]
        store = InMemoryBudgetStore(clock=lambda: 0.0)

        # When: 100 calls each costing 0.003 cents (total = 0.3 cents)
        for _ in range(100):
            await store.record_and_check(
                rules=rules, scope={}, input_tokens=0, output_tokens=0, cost=0.003
            )

        # Then: not exceeded (0.3 < 1), no ceil-per-call overcount
        snap = store.get_snapshot("__global__", "", limit=1)
        assert not snap.exceeded
        assert snap.spent == 0  # round(0.3) = 0

    @pytest.mark.asyncio
    async def test_float_accumulation_eventual_breach(self) -> None:
        # Given: store with 1-cent limit
        rules = [BudgetLimitRule(limit=1)]
        store = InMemoryBudgetStore(clock=lambda: 0.0)

        # When: 400 calls each costing 0.003 cents (total = 1.2 cents)
        for _ in range(400):
            results = await store.record_and_check(
                rules=rules, scope={}, input_tokens=0, output_tokens=0, cost=0.003
            )

        # Then: exceeded (1.2 >= 1)
        assert results[0].exceeded is True


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_compute_utilization_no_limits(self) -> None:
        # Given/When: no limits set / Then: 0.0
        assert _compute_utilization(100.0, 10000, None, "usd_cents") == 0.0

    def test_compute_utilization_spend_only(self) -> None:
        # Given: 500 of 1000 spent / Then: 0.5
        assert _compute_utilization(500.0, 0, 1000, "usd_cents") == pytest.approx(0.5)

    def test_compute_utilization_clamped(self) -> None:
        # Given: overspent / Then: clamped to 1.0
        assert _compute_utilization(2000.0, 0, 1000, "usd_cents") == pytest.approx(1.0)

    def test_compute_utilization_negative_clamped_to_zero(self) -> None:
        # Given: refund made the accumulator go negative
        # When: utilization is computed
        # Then: clamped to 0.0 (BudgetSnapshot.utilization contract)
        assert _compute_utilization(-150.0, 0, 100, "usd_cents") == 0.0
        # And: negative tokens (not currently reachable but defensively clamped)
        assert _compute_utilization(0.0, -50, 100, "tokens") == 0.0

    def test_parse_period_key_valid(self) -> None:
        # Given: well-formed period key / Then: parsed tuple
        from agent_control_evaluator_budget.budget.memory_store import _parse_period_key

        assert _parse_period_key("P86400:19675") == (86400, 19675)
        assert _parse_period_key("P3600:0") == (3600, 0)

    def test_parse_period_key_malformed(self) -> None:
        # Given: empty, missing, or non-numeric period keys
        # When: parsed
        # Then: None returned (never raises)
        from agent_control_evaluator_budget.budget.memory_store import _parse_period_key

        assert _parse_period_key("") is None  # cumulative sentinel
        assert _parse_period_key("P") is None  # no separator
        assert _parse_period_key("P:1") is None  # empty window
        assert _parse_period_key("P86400:") is None  # empty index
        assert _parse_period_key("Pabc:1") is None  # non-numeric window
        assert _parse_period_key("P86400:xyz") is None  # non-numeric index
        assert _parse_period_key("X86400:1") is None  # wrong prefix
        assert _parse_period_key("PP86400:1") is None  # double P

    def test_derive_period_key_none(self) -> None:
        # Given: no window / Then: empty key
        assert _derive_period_key(None, 0.0) == ""

    def test_derive_period_key_daily(self) -> None:
        # Given: daily window at 1700000000 / Then: epoch-aligned key
        key = _derive_period_key(WINDOW_DAILY, 1700000000.0)
        assert key == "P86400:19675"

    def test_derive_period_key_weekly(self) -> None:
        # Given: weekly window / Then: key starts with P604800:
        key = _derive_period_key(WINDOW_WEEKLY, 1700000000.0)
        assert key.startswith("P604800:")

    def test_build_scope_key_global(self) -> None:
        # Given: empty scope / Then: __global__
        assert _build_scope_key({}, None, {}) == "__global__"

    def test_build_scope_key_with_scope(self) -> None:
        # Given: channel scope / Then: channel=slack
        key = _build_scope_key({"channel": "slack"}, None, {})
        assert key == "channel=slack"

    def test_build_scope_key_with_group_by(self) -> None:
        # Given: scope + group_by / Then: combined key
        key = _build_scope_key({"channel": "slack"}, "user_id", {"user_id": "u1"})
        assert key == "channel=slack|user_id=u1"

    def test_build_scope_key_group_by_missing(self) -> None:
        # Given: group_by field not in scope / Then: __global__
        key = _build_scope_key({}, "user_id", {})
        assert key == "__global__"

    def test_extract_tokens_standard(self) -> None:
        # Given: standard token fields / Then: extracted
        data = {"usage": {"input_tokens": 100, "output_tokens": 50}}
        assert _extract_tokens(data, None) == (100, 50)

    def test_extract_tokens_openai(self) -> None:
        # Given: OpenAI-style fields / Then: extracted
        data = {"usage": {"prompt_tokens": 80, "completion_tokens": 40}}
        assert _extract_tokens(data, None) == (80, 40)

    def test_extract_tokens_falls_back_when_normalized_fields_are_none(self) -> None:
        # Given: normalized fields present but unset, plus legacy OpenAI fields
        data = {
            "usage": {
                "input_tokens": None,
                "output_tokens": None,
                "prompt_tokens": 80,
                "completion_tokens": 40,
            }
        }

        # When/Then: fallback still uses the legacy fields
        assert _extract_tokens(data, None) == (80, 40)

    def test_extract_tokens_falls_back_per_field(self) -> None:
        # Given: one normalized field missing, the other present
        data = {
            "usage": {
                "input_tokens": 100,
                "output_tokens": None,
                "completion_tokens": 40,
            }
        }

        # When/Then: fallback applies independently per token side
        assert _extract_tokens(data, None) == (100, 40)

    def test_extract_tokens_none(self) -> None:
        # Given: None data / Then: (0, 0)
        assert _extract_tokens(None, None) == (0, 0)


# ---------------------------------------------------------------------------
# BudgetLimitRule config validation
# ---------------------------------------------------------------------------


class TestBudgetLimitRuleConfig:
    def test_valid_rule(self) -> None:
        # Given/When: valid limit / Then: accepted
        rule = BudgetLimitRule(limit=1000)
        assert rule.limit == 1000

    def test_no_limit_rejected(self) -> None:
        # Given/When: no limit / Then: rejected
        with pytest.raises(ValidationError, match="Field required"):
            BudgetLimitRule()

    def test_negative_limit_rejected(self) -> None:
        # Given/When: negative limit / Then: rejected
        with pytest.raises(ValidationError, match="positive"):
            BudgetLimitRule(limit=-1)

    def test_zero_limit_rejected(self) -> None:
        # Given/When: zero limit / Then: rejected
        with pytest.raises(ValidationError, match="positive"):
            BudgetLimitRule(limit=0)

    def test_negative_window_seconds_rejected(self) -> None:
        # Given/When: negative window_seconds / Then: rejected
        with pytest.raises(ValidationError, match="positive"):
            BudgetLimitRule(limit=1000, window_seconds=-1)

    def test_zero_window_seconds_rejected(self) -> None:
        # Given/When: zero window_seconds / Then: rejected
        with pytest.raises(ValidationError, match="positive"):
            BudgetLimitRule(limit=1000, window_seconds=0)

    def test_token_only_rule(self) -> None:
        # Given/When: token limit_unit / Then: accepted
        rule = BudgetLimitRule(limit=5000, limit_unit="tokens")
        assert rule.limit == 5000
        assert rule.limit_unit == "tokens"

    def test_empty_limits_rejected(self) -> None:
        # Given/When: empty limits list / Then: rejected
        with pytest.raises(ValidationError):
            BudgetEvaluatorConfig(limits=[])

    def test_window_constants(self) -> None:
        # Given/When/Then: constants have expected values
        assert WINDOW_DAILY == 86400
        assert WINDOW_WEEKLY == 604800
        assert WINDOW_MONTHLY == 2592000


class TestModelPricing:
    def test_model_pricing_validation_requires_pricing_for_cost_rules(self) -> None:
        # Given: a cost-based rule without pricing
        # When/Then: config validation rejects it
        with pytest.raises(ValidationError, match="pricing is required"):
            BudgetEvaluatorConfig(limits=[BudgetLimitRule(limit=100)])

    def test_model_pricing_token_rule_no_pricing_ok(self) -> None:
        # Given: a token-only rule without pricing
        # When: config is created
        config = BudgetEvaluatorConfig(limits=[BudgetLimitRule(limit=100, limit_unit="tokens")])

        # Then: no pricing table is required
        assert config.pricing is None


# ---------------------------------------------------------------------------
# BudgetEvaluator integration
# ---------------------------------------------------------------------------


class TestBudgetEvaluator:
    def _make_evaluator(self, **kwargs: Any) -> BudgetEvaluator:
        config = BudgetEvaluatorConfig(**kwargs)
        return BudgetEvaluator(config)

    @pytest.mark.asyncio
    async def test_single_call_under_budget(self) -> None:
        # Given: evaluator with 1000-token limit (token-only, no pricing needed)
        ev = self._make_evaluator(limits=[{"limit": 1000, "limit_unit": "tokens"}])

        # When: evaluate with usage data
        result = await ev.evaluate({"usage": {"input_tokens": 100, "output_tokens": 50}})

        # Then: not matched (150 < 1000)
        assert result.matched is False
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_accumulate_past_budget(self) -> None:
        # Given: evaluator with 50-cent limit and pricing table
        ev = self._make_evaluator(
            limits=[{"limit": 50}],
            pricing={"gpt-4": {"input_per_1k": 30.0, "output_per_1k": 60.0}},
            model_path="model",
        )

        # When: two calls with tokens costing 27 cents each
        # cost = (300*30 + 300*60) / 1000 = 27.0
        # total = 27 + 27 = 54 > 50
        step = {"model": "gpt-4", "usage": {"input_tokens": 300, "output_tokens": 300}}
        await ev.evaluate(step)
        result = await ev.evaluate(step)

        # Then: matched (54 > 50)
        assert result.matched is True
        assert result.metadata is not None

    @pytest.mark.asyncio
    async def test_group_by_user(self) -> None:
        # Given: per-user 1000-cent budget with pricing table
        ev = self._make_evaluator(
            limits=[{"group_by": "user_id", "limit": 1000}],
            pricing={"gpt-4": {"input_per_1k": 200.0, "output_per_1k": 0.0}},
            model_path="model",
            metadata_paths={"user_id": "user_id"},
        )

        # When: u1 spends 800+300=1100 cents, u2 spends 300 cents
        def _step(tokens: int, user: str) -> dict:
            return {
                "model": "gpt-4",
                "usage": {"input_tokens": tokens, "output_tokens": 0},
                "user_id": user,
            }

        await ev.evaluate(_step(4000, "u1"))
        r1 = await ev.evaluate(_step(1500, "u1"))
        r2 = await ev.evaluate(_step(1500, "u2"))

        # Then: u1 exceeded (1100 > 1000), u2 not (300 < 1000)
        assert r1.matched is True
        assert r2.matched is False

    @pytest.mark.asyncio
    async def test_token_only_limit(self) -> None:
        # Given: 500 token limit
        ev = self._make_evaluator(limits=[{"limit": 500, "limit_unit": "tokens"}])

        # When: consume 600 tokens
        result = await ev.evaluate({"usage": {"input_tokens": 300, "output_tokens": 300}})

        # Then: exceeded
        assert result.matched is True

    @pytest.mark.asyncio
    async def test_no_data_returns_not_matched(self) -> None:
        # Given: evaluator / When: None data / Then: not matched
        ev = self._make_evaluator(limits=[{"limit": 1000}], pricing={}, model_path="model")
        result = await ev.evaluate(None)
        assert result.matched is False

    @pytest.mark.asyncio
    async def test_confidence_always_one(self) -> None:
        # Given: evaluator with 1000-cent limit and pricing table
        ev = self._make_evaluator(
            limits=[{"limit": 1000}],
            pricing={"gpt-4": {"input_per_1k": 200.0, "output_per_1k": 0.0}},
            model_path="model",
        )

        # When: first call costs 50 cents, second costs 960 cents
        def _step(tokens: int) -> dict:
            return {"model": "gpt-4", "usage": {"input_tokens": tokens, "output_tokens": 0}}

        r1 = await ev.evaluate(_step(250))
        r2 = await ev.evaluate(_step(4800))

        # Then: confidence is always 1.0
        assert r1.confidence == 1.0
        assert r2.confidence == 1.0

    @pytest.mark.asyncio
    async def test_cost_computed_from_pricing_table(self) -> None:
        # Given: evaluator with pricing table and 100-cent cost limit
        ev = self._make_evaluator(
            limits=[{"limit": 100}],
            pricing={"gpt-4": {"input_per_1k": 30.0, "output_per_1k": 60.0}},
            model_path="model",
        )

        # When: evaluate with known model and tokens
        # cost = (100*30 + 200*60) / 1000 = 15.0 cents
        result = await ev.evaluate(
            {
                "model": "gpt-4",
                "usage": {"input_tokens": 100, "output_tokens": 200},
            }
        )

        # Then: not matched (15 < 100), cost tracked in metadata
        assert result.matched is False
        assert result.metadata is not None
        assert result.metadata["cost"] == pytest.approx(15.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_unknown_model_cost_zero(self) -> None:
        # Given: evaluator with warn mode and data from an unknown model
        ev = self._make_evaluator(
            limits=[{"limit": 100}],
            pricing={"gpt-4": {"input_per_1k": 30.0, "output_per_1k": 60.0}},
            model_path="model",
            unknown_model_behavior="warn",
        )

        # When: evaluate with a model not in the pricing table
        result = await ev.evaluate(
            {
                "model": "unknown-model",
                "usage": {"input_tokens": 1000, "output_tokens": 1000},
            }
        )

        # Then: not matched (cost=0 because model not in pricing)
        assert result.matched is False
        assert result.metadata is not None
        assert result.metadata["cost"] == 0.0

    @pytest.mark.asyncio
    async def test_small_cost_no_overcount(self) -> None:
        # Given: evaluator with 1-cent limit, pricing yields 0.003 cents per call
        ev = self._make_evaluator(
            limits=[{"limit": 1}],
            pricing={"gpt-4": {"input_per_1k": 0.03, "output_per_1k": 0.0}},
            model_path="model",
        )
        step = {"model": "gpt-4", "usage": {"input_tokens": 100, "output_tokens": 0}}

        # When: 100 calls (total cost = 0.3 cents, should NOT exceed 1 cent)
        for _ in range(100):
            result = await ev.evaluate(step)

        # Then: not exceeded (float accumulation, no per-call ceil)
        assert result.matched is False


class TestBudgetIdSemantics:
    @pytest.mark.asyncio
    async def test_same_budget_id_shares_store(self) -> None:
        # Given: two evaluators with the same budget_id
        config1 = BudgetEvaluatorConfig(
            limits=[{"limit": 100}],
            budget_id="shared",
            pricing={"gpt-4": {"input_per_1k": 100.0, "output_per_1k": 0.0}},
            model_path="model",
        )
        config2 = BudgetEvaluatorConfig(
            limits=[{"limit": 100}],
            budget_id="shared",
            pricing={"gpt-4": {"input_per_1k": 100.0, "output_per_1k": 0.0}},
            model_path="model",
        )
        ev1 = BudgetEvaluator(config1)
        ev2 = BudgetEvaluator(config2)
        step = {"model": "gpt-4", "usage": {"input_tokens": 500, "output_tokens": 0}}

        # When: each evaluator records a 50-cent call
        first = await ev1.evaluate(step)
        second = await ev2.evaluate(step)

        # Then: spend is shared and the second call reaches the 100-cent limit
        assert first.matched is False
        assert second.matched is True

    @pytest.mark.asyncio
    async def test_different_budget_id_isolates_store(self) -> None:
        # Given: two evaluators with different budget_id values
