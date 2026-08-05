"""Token accounting, and the two ways a cost report lies.

An unpriced call reported as zero makes a run total that reads as authoritative
and is wrong. An estimate reported as a measurement does the same thing more
quietly. Both are asserted against here.
"""

from __future__ import annotations

import pytest

from core.llm.usage import Pricing, TokenCounts, UsageLedger, UsageRecord, compute_cost

pytestmark = pytest.mark.unit

_PRICING = Pricing(
    input_per_million=3.0,
    output_per_million=15.0,
    cached_input_per_million=0.3,
    cache_write_per_million=3.75,
)


def test_the_three_input_fields_are_disjoint() -> None:
    """A cached run must not read as more expensive than an uncached one."""
    tokens = TokenCounts(input_tokens=200, cached_input_tokens=800, cache_write_tokens=100)

    assert tokens.total_input_tokens == 1_100


def test_cost_uses_each_rate_for_its_own_bucket() -> None:
    tokens = TokenCounts(
        input_tokens=1_000_000,
        cached_input_tokens=1_000_000,
        cache_write_tokens=1_000_000,
        output_tokens=1_000_000,
    )

    assert compute_cost(tokens, _PRICING) == pytest.approx(3.0 + 0.3 + 3.75 + 15.0)


def test_an_unpriced_model_costs_none_not_zero() -> None:
    """Zero is a number somebody will put in a budget."""
    assert compute_cost(TokenCounts(input_tokens=10_000), None) is None


def test_a_cached_read_is_cheaper_than_an_uncached_one() -> None:
    uncached = compute_cost(TokenCounts(input_tokens=100_000), _PRICING)
    cached = compute_cost(TokenCounts(cached_input_tokens=100_000), _PRICING)

    assert uncached is not None and cached is not None
    assert cached < uncached


def test_a_missing_cached_rate_falls_back_to_the_uncached_one() -> None:
    """Better to over-report a cost than to invent a discount."""
    plain = Pricing(input_per_million=3.0, output_per_million=15.0)

    assert compute_cost(TokenCounts(cached_input_tokens=1_000_000), plain) == pytest.approx(3.0)


def test_reasoning_tokens_are_billed_as_output_unless_priced_separately() -> None:
    plain = Pricing(input_per_million=3.0, output_per_million=15.0)
    separate = Pricing(input_per_million=3.0, output_per_million=15.0, reasoning_per_million=30.0)
    tokens = TokenCounts(output_tokens=1_000_000, reasoning_tokens=1_000_000)

    assert compute_cost(tokens, plain) == pytest.approx(15.0)
    assert compute_cost(tokens, separate) == pytest.approx(15.0 + 30.0)


def test_adding_counts_keeps_the_estimate_flag_sticky() -> None:
    """One estimated call makes the total an estimate. It cannot become measured."""
    measured = TokenCounts(input_tokens=100)
    estimated = TokenCounts(input_tokens=100, estimated=True)

    assert (measured + estimated).estimated is True
    assert (estimated + measured).estimated is True


def test_a_ledger_reports_how_much_of_itself_it_could_not_price() -> None:
    ledger = UsageLedger(scope="run")
    ledger.add(
        UsageRecord.priced(
            provider_id="anthropic",
            model_id="claude-sonnet-5",
            tokens=TokenCounts(input_tokens=1_000_000),
            pricing=_PRICING,
        )
    )
    ledger.add(
        UsageRecord.priced(
            provider_id="ollama",
            model_id="llama3.1",
            tokens=TokenCounts(input_tokens=1_000_000),
            pricing=None,
        )
    )

    assert ledger.call_count == 2
    assert ledger.cost_usd == pytest.approx(3.0)
    assert ledger.unpriced_call_count == 1
    assert ledger.is_complete is False


def test_a_ledger_of_fully_priced_measured_calls_is_complete() -> None:
    ledger = UsageLedger()
    ledger.add(
        UsageRecord.priced(
            provider_id="anthropic",
            model_id="claude-sonnet-5",
            tokens=TokenCounts(input_tokens=10, output_tokens=5),
            pricing=_PRICING,
        )
    )

    assert ledger.is_complete is True


def test_an_estimated_call_makes_the_ledger_incomplete() -> None:
    ledger = UsageLedger()
    ledger.add(
        UsageRecord.priced(
            provider_id="anthropic",
            model_id="claude-sonnet-5",
            tokens=TokenCounts(input_tokens=10, estimated=True),
            pricing=_PRICING,
        )
    )

    assert ledger.is_complete is False


def test_a_ledger_ignores_a_missing_record_so_callers_need_no_guard() -> None:
    ledger = UsageLedger()
    ledger.add(None)

    assert ledger.call_count == 0
