"""A year of remediation history, answered inside the budget a proposal can afford.

The budget is in ``config.constants.closed_loop`` rather than here, so the number
and the assertion cannot drift apart. What this file adds is the *shape* it was
measured against, because a budget without one is not a budget:

- a year of remediations at a hundred a week, which is a busy deployment acting
  roughly fifteen times a day;
- fifty resources and seven capabilities, so the slice a proposal asks about is
  a small fraction of the whole and the query has to narrow rather than scan;
- every row verified, because an unverified one is cheaper to count and a
  benchmark over the cheap case is not a benchmark.

The question measured is the one on the decision path: "has this capability
worked on this resource before". It is asked once per proposal, and an
investigation that waits on it is an investigation that stalls — which is why
NFR-003 puts a number on it rather than an intention.

The in-memory backend is what runs here, and it is the honest floor rather than
the answer: it filters in Python over every row, so a real backend with the
partial index on ``(resource, capability, condition, executed_at)`` cannot be
slower than this for the same shape. A regression here is a regression in the
aggregate, not in the storage.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.closed_loop import EFFECTIVENESS_QUERY_BUDGET_SECONDS
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.persistence.ports.remediation_ledger import (
    RemediationOutcome,
    VerificationState,
    VerificationVerdict,
)
from platform.remediation.history import EffectivenessHistory

pytestmark = pytest.mark.benchmark

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

#: A year at a hundred a week. Fifteen production changes a day is a deployment
#: acting rather than one that has autonomy switched on and never uses it.
ACTIONS_IN_A_YEAR = 52 * 100

#: Fifty resources and seven capabilities — the shipped catalogue's size — so the
#: slice one proposal asks about is roughly fifteen rows out of five thousand.
RESOURCES = tuple(f"resource-{index}" for index in range(50))
CAPABILITIES = (
    "restart_workload",
    "rollback_deployment",
    "scale_workload",
    "cordon_drain_node",
    "update_resource_limits",
    "toggle_feature_flag",
    "clear_cache",
)

#: Four verdicts in rotation. ``UNVERIFIABLE`` is left out because it is settled
#: at record time and never reaches the aggregate through this path.
VERDICTS = (
    VerificationVerdict.EFFECTIVE,
    VerificationVerdict.INEFFECTIVE,
    VerificationVerdict.WORSENED,
    VerificationVerdict.INCONCLUSIVE,
)


def at(hours: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``hours``."""
    return EPOCH + timedelta(hours=hours)


def a_year() -> tuple[RemediationOutcome, ...]:
    """Return a year of verified remediations across the estate."""
    return tuple(
        RemediationOutcome(
            action_id=f"action-{index}",
            capability=CAPABILITIES[index % len(CAPABILITIES)],
            resource_id=RESOURCES[index % len(RESOURCES)],
            condition_key=f"condition-{index % 9}",
            team_node_id="team-payments",
            executed_at=at(-index * 1.68),
            due_at=at(-index * 1.68 + 0.1),
            settle_seconds=300,
            state=VerificationState.VERIFIED,
            verdict=VERDICTS[index % len(VERDICTS)],
            signal_names=("workload.error_rate",),
            before={"workload.error_rate": 10.0},
            after={"workload.error_rate": 1.0},
        )
        for index in range(ACTIONS_IN_A_YEAR)
    )


@pytest.fixture
async def a_year_of_history() -> FakePersistence:
    """Return a store holding a year of remediation outcomes."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme Corp")
    async with store.begin(TenantScope(org_id="acme")) as unit:
        for outcome in a_year():
            await unit.remediation.record(outcome)
    return store


async def test_the_question_a_proposal_asks_answers_inside_its_budget(
    a_year_of_history: FakePersistence,
) -> None:
    """NFR-003: asked once per proposal, over a year, and it cannot be the slow part."""
    async with a_year_of_history.begin(TenantScope(org_id="acme")) as unit:
        history = EffectivenessHistory(ledger=unit.remediation)

        started = time.perf_counter()
        prior = await history.prior(CAPABILITIES[0], RESOURCES[0])
        elapsed = time.perf_counter() - started

    assert prior.summary.total > 0
    assert elapsed < EFFECTIVENESS_QUERY_BUDGET_SECONDS, (
        f"answering 'has {CAPABILITIES[0]} worked on {RESOURCES[0]}' over "
        f"{ACTIONS_IN_A_YEAR} rows took {elapsed:.3f}s, above the "
        f"{EFFECTIVENESS_QUERY_BUDGET_SECONDS}s budget a proposal can afford"
    )


async def test_each_dimension_answers_inside_the_same_budget(
    a_year_of_history: FakePersistence,
) -> None:
    """FR-014's three dimensions are three queries, and all three are on a screen."""
    async with a_year_of_history.begin(TenantScope(org_id="acme")) as unit:
        history = EffectivenessHistory(ledger=unit.remediation)

        for name, question in (
            ("resource", history.by_resource(RESOURCES[0])),
            ("capability", history.by_capability(CAPABILITIES[0])),
            ("condition", history.by_condition("condition-0")),
        ):
            started = time.perf_counter()
            summary = await question
            elapsed = time.perf_counter() - started

            assert summary.total > 0, name
            assert elapsed < EFFECTIVENESS_QUERY_BUDGET_SECONDS, (
                f"the {name} slice took {elapsed:.3f}s over {ACTIONS_IN_A_YEAR} rows"
            )


async def test_the_aggregate_counts_every_row_rather_than_the_first_page(
    a_year_of_history: FakePersistence,
) -> None:
    """The failure this budget could hide: a fast answer that is wrong.

    A count assembled from a page would come in well inside the budget and would
    understate a year by two orders of magnitude, so the timing assertions above
    are only worth having beside this one.
    """
    async with a_year_of_history.begin(TenantScope(org_id="acme")) as unit:
        summary = await EffectivenessHistory(ledger=unit.remediation).by_capability(CAPABILITIES[0])

    expected = len([index for index in range(ACTIONS_IN_A_YEAR) if index % len(CAPABILITIES) == 0])
    assert summary.total == expected
    assert summary.verified == summary.total
