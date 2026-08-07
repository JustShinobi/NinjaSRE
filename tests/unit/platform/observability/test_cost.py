"""Cost attributed three ways at once, including when the model changes mid-run.

SC-009 exists because of a specific defect that a naive implementation always
has. A run is recorded with "its" model — whichever was active when the run
finished — and every dollar the run spent is attributed there. The escalation
from a cheap model to an expensive one, which is exactly the behaviour an
operator is trying to see the cost of, becomes invisible: the whole run bills to
the expensive model and the cheap one looks unused.

So attribution is per call, and the three views are summations over the same
records rather than three counters kept in parallel. That is the property being
tested here: the per-model records for one run sum to that run's total, whatever
the run did in the middle.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.llm.usage import Pricing, TokenCounts, UsageRecord
from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter, RecordingTransport
from platform.observability.metrics.cost import CostLedger
from platform.observability.metrics.definitions import MetricRegistry

pytestmark = pytest.mark.unit

ENABLED = TelemetryConfig(endpoint="http://collector.internal:4318")

CHEAP = Pricing(input_per_million=1.0, output_per_million=2.0)
EXPENSIVE = Pricing(input_per_million=15.0, output_per_million=75.0)

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def usage(model: str, pricing: Pricing | None, *, tokens: int = 1_000) -> UsageRecord:
    """Return one priced call against ``model``."""
    return UsageRecord.priced(
        provider_id="anthropic",
        model_id=model,
        tokens=TokenCounts(input_tokens=tokens, output_tokens=tokens),
        pricing=pricing,
    )


def ledger() -> CostLedger:
    """Return a ledger writing into a registry whose transport records."""
    return CostLedger(
        metrics=MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, RecordingTransport()))
    )


def test_one_call_is_attributed_to_a_run_a_team_and_a_model() -> None:
    costs = ledger()
    costs.record(usage("sonnet", CHEAP), run_id="run-1", team="platform", at=MOMENT)

    assert costs.by_run()["run-1"].cost_usd == pytest.approx(0.003)
    assert costs.by_team()["platform"].cost_usd == pytest.approx(0.003)
    assert costs.by_model()[("anthropic", "sonnet")].cost_usd == pytest.approx(0.003)


def test_a_run_that_switches_models_keeps_a_record_per_model() -> None:
    """SC-009. Two records, not one attributed to whichever was last."""
    costs = ledger()
    costs.record(usage("haiku", CHEAP), run_id="run-2", team="platform", at=MOMENT)
    costs.record(usage("opus", EXPENSIVE), run_id="run-2", team="platform", at=MOMENT)

    per_model = costs.by_model()

    assert set(per_model) == {("anthropic", "haiku"), ("anthropic", "opus")}
    assert per_model[("anthropic", "haiku")].cost_usd == pytest.approx(0.003)
    assert per_model[("anthropic", "opus")].cost_usd == pytest.approx(0.09)


def test_the_per_model_records_for_a_run_sum_to_that_runs_total() -> None:
    """SC-009's actual assertion: the parts add up to the whole."""
    costs = ledger()
    costs.record(usage("haiku", CHEAP), run_id="run-3", team="platform", at=MOMENT)
    costs.record(usage("opus", EXPENSIVE), run_id="run-3", team="platform", at=MOMENT)
    costs.record(usage("haiku", CHEAP), run_id="run-3", team="platform", at=MOMENT)

    per_model_for_run = costs.by_model(run_id="run-3")

    assert sum(entry.cost_usd for entry in per_model_for_run.values()) == pytest.approx(
        costs.by_run()["run-3"].cost_usd
    )
    assert per_model_for_run[("anthropic", "haiku")].calls == 2


def test_another_run_does_not_leak_into_the_first() -> None:
    costs = ledger()
    costs.record(usage("haiku", CHEAP), run_id="run-a", team="platform", at=MOMENT)
    costs.record(usage("opus", EXPENSIVE), run_id="run-b", team="payments", at=MOMENT)

    assert costs.by_run()["run-a"].cost_usd == pytest.approx(0.003)
    assert costs.by_team()["payments"].cost_usd == pytest.approx(0.09)
    assert set(costs.by_model(run_id="run-a")) == {("anthropic", "haiku")}


def test_an_unpriced_call_is_counted_rather_than_billed_at_zero() -> None:
    """A local model costs nothing knowable, not nothing."""
    costs = ledger()
    costs.record(usage("llama-3", None), run_id="run-4", team="platform", at=MOMENT)

    entry = costs.by_run()["run-4"]

    assert entry.cost_usd == 0.0
    assert entry.unpriced_calls == 1
    assert entry.is_complete is False


def test_a_mixed_run_says_how_much_of_itself_it_could_not_price() -> None:
    costs = ledger()
    costs.record(usage("sonnet", CHEAP), run_id="run-5", team="platform", at=MOMENT)
    costs.record(usage("llama-3", None), run_id="run-5", team="platform", at=MOMENT)

    entry = costs.by_run()["run-5"]

    assert entry.calls == 2
    assert entry.unpriced_calls == 1
    assert entry.is_complete is False


def test_tokens_are_attributed_alongside_the_money() -> None:
    costs = ledger()
    costs.record(usage("sonnet", CHEAP, tokens=500), run_id="run-6", team="platform", at=MOMENT)

    entry = costs.by_model()[("anthropic", "sonnet")]

    assert entry.input_tokens == 500
    assert entry.output_tokens == 500


def test_recording_writes_the_cost_metrics_with_bounded_labels() -> None:
    costs = ledger()
    costs.record(usage("sonnet", CHEAP), run_id="run-7", team="platform", at=MOMENT)

    metrics = costs.metrics

    assert (
        metrics.counter("llm.input_tokens").value(
            team="platform", model="sonnet", provider="anthropic"
        )
        == 1_000
    )
    assert metrics.counter("llm.cost_usd").value(
        team="platform", model="sonnet", provider="anthropic"
    ) == pytest.approx(0.003)


def test_an_unpriced_call_increments_its_own_counter() -> None:
    costs = ledger()
    costs.record(usage("llama-3", None), run_id="run-8", team="platform", at=MOMENT)

    assert (
        costs.metrics.counter("llm.unpriced_calls").value(
            team="platform", model="llama-3", provider="anthropic"
        )
        == 1
    )


def test_a_period_report_covers_a_team_over_a_window() -> None:
    """FR-023: what the CLI and the console both read."""
    costs = ledger()
    costs.record(
        usage("sonnet", CHEAP), run_id="r1", team="platform", at=datetime(2026, 8, 1, tzinfo=UTC)
    )
    costs.record(
        usage("opus", EXPENSIVE), run_id="r2", team="platform", at=datetime(2026, 9, 1, tzinfo=UTC)
    )

    august = costs.report(
        since=datetime(2026, 8, 1, tzinfo=UTC), until=datetime(2026, 8, 31, tzinfo=UTC)
    )

    assert set(august.by_team) == {"platform"}
    assert august.by_team["platform"].cost_usd == pytest.approx(0.003)
    assert august.total.calls == 1


def test_a_report_breaks_the_window_down_by_team_and_by_model() -> None:
    costs = ledger()
    costs.record(usage("sonnet", CHEAP), run_id="r1", team="platform", at=MOMENT)
    costs.record(usage("opus", EXPENSIVE), run_id="r2", team="payments", at=MOMENT)

    report = costs.report()

    assert set(report.by_team) == {"platform", "payments"}
    assert set(report.by_model) == {("anthropic", "sonnet"), ("anthropic", "opus")}
    assert report.total.cost_usd == pytest.approx(0.093)


def test_a_report_renders_as_records_a_surface_can_print() -> None:
    costs = ledger()
    costs.record(usage("sonnet", CHEAP), run_id="r1", team="platform", at=MOMENT)

    records = costs.report().to_record()

    assert records["total"]["calls"] == 1
    assert records["by_team"][0]["team"] == "platform"
    assert records["by_model"][0]["model"] == "sonnet"
    assert records["by_model"][0]["provider"] == "anthropic"


def test_a_team_that_spent_nothing_is_absent_rather_than_zero() -> None:
    """A row of zeroes for every team that exists is a report nobody reads."""
    costs = ledger()

    assert costs.report().by_team == {}
