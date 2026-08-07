"""A label whose value space is unbounded is a collector outage with a delay.

The failure this prevents is specific and it is always the same shape. Somebody
adds a label that is useful while debugging — a pod name, a run identifier, a
trace id — and every distinct value becomes a permanent time series. The graph
looks fine for a day. Then the collector's memory does not, and the operator
blames the tool that sent the data rather than the label that was added.

So there are two controls, and both are enforced rather than documented. A label
that is not on an instrument's allow-list cannot be written at all, and a label
that is on the list still cannot exceed its value budget.
"""

from __future__ import annotations

import pytest

from config.constants.observability import (
    MAX_METRIC_LABEL_VALUE_CHARS,
    MAX_METRIC_LABEL_VALUES,
    METRIC_LABEL_OVERFLOW,
)
from platform.observability.metrics.cardinality import (
    CardinalityGuard,
    LabelSet,
    UnknownLabel,
)

pytestmark = pytest.mark.unit


def test_a_label_set_accepts_exactly_what_it_declares() -> None:
    labels = LabelSet(("team", "model", "provider"))

    assert labels.bind({"team": "platform", "model": "x", "provider": "y"}) == (
        ("model", "x"),
        ("provider", "y"),
        ("team", "platform"),
    )


def test_binding_is_ordered_so_one_series_has_one_key() -> None:
    """Two orderings of the same labels must not become two time series."""
    labels = LabelSet(("team", "model"))

    assert labels.bind({"team": "a", "model": "b"}) == labels.bind({"model": "b", "team": "a"})


def test_an_undeclared_label_is_refused_by_name() -> None:
    labels = LabelSet(("team",))

    with pytest.raises(UnknownLabel, match="pod"):
        labels.bind({"team": "platform", "pod": "checkout-7d9f"})


def test_a_declared_label_that_was_not_supplied_is_absent_rather_than_empty() -> None:
    """An empty string is a value, and it would be a series of its own."""
    labels = LabelSet(("team", "model"))

    assert labels.bind({"team": "platform"}) == (("team", "platform"),)


def test_an_instrument_with_no_labels_accepts_nothing() -> None:
    labels = LabelSet(())

    assert labels.bind({}) == ()
    with pytest.raises(UnknownLabel):
        labels.bind({"team": "platform"})


def test_the_guard_passes_values_through_until_the_budget_is_spent() -> None:
    guard = CardinalityGuard()

    assert guard.bound("capability.invocations", "capability", "grafana.query") == "grafana.query"
    assert guard.bound("capability.invocations", "capability", "grafana.query") == "grafana.query"
    assert guard.overflowed == {}


def test_a_high_cardinality_label_collapses_into_one_bucket() -> None:
    """SC-004, as a unit. The load test drives the same guard through a registry."""
    guard = CardinalityGuard()

    bounded = [
        guard.bound("investigation.count", "team", f"team-{index}")
        for index in range(MAX_METRIC_LABEL_VALUES * 5)
    ]

    distinct = set(bounded)

    assert len(distinct) == MAX_METRIC_LABEL_VALUES + 1
    assert METRIC_LABEL_OVERFLOW in distinct
    assert guard.overflowed == {("investigation.count", "team"): MAX_METRIC_LABEL_VALUES * 4}


def test_the_budget_is_per_instrument_and_per_label() -> None:
    """One noisy label must not spend another instrument's budget."""
    guard = CardinalityGuard()

    for index in range(MAX_METRIC_LABEL_VALUES + 10):
        guard.bound("a", "team", f"team-{index}")

    assert guard.bound("b", "team", "team-9999") == "team-9999"
    assert guard.bound("a", "model", "sonnet") == "sonnet"


def test_a_value_already_admitted_keeps_working_after_the_budget_is_spent() -> None:
    """Otherwise the overflow would swallow the series an operator was watching."""
    guard = CardinalityGuard()
    guard.bound("investigation.count", "team", "platform")

    for index in range(MAX_METRIC_LABEL_VALUES * 2):
        guard.bound("investigation.count", "team", f"noise-{index}")

    assert guard.bound("investigation.count", "team", "platform") == "platform"


def test_a_long_value_is_truncated_rather_than_carried() -> None:
    guard = CardinalityGuard()

    bounded = guard.bound("capability.invocations", "capability", "x" * 5_000)

    assert len(bounded) == MAX_METRIC_LABEL_VALUE_CHARS


def test_truncation_happens_before_the_budget_so_a_prefix_cannot_multiply_it() -> None:
    guard = CardinalityGuard()
    shared = "y" * MAX_METRIC_LABEL_VALUE_CHARS

    guard.bound("i", "capability", shared + "-one")
    guard.bound("i", "capability", shared + "-two")

    assert guard.distinct("i", "capability") == 1


def test_the_guard_reports_what_it_bounded_for_an_operator() -> None:
    guard = CardinalityGuard()
    for index in range(MAX_METRIC_LABEL_VALUES + 3):
        guard.bound("investigation.count", "team", f"team-{index}")

    record = guard.to_record()

    assert record["overflowed"] == [
        {"instrument": "investigation.count", "label": "team", "collapsed": 3}
    ]
    assert record["ceiling"] == MAX_METRIC_LABEL_VALUES
