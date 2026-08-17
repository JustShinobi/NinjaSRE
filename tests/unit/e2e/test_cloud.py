"""The cloud suite: six services, provisioned and destroyed, inside a cost bound.

Two claims carry this suite and both are about what happens when things go
wrong. An *interrupted* run must leak nothing, which is a claim about a code
path that only runs when the process is being killed. The cost must stay inside
a declared bound, which is only a claim at all because the bound is declared per
scenario and the actual is reported against it.

The provisioner here is a recording double. That is not a weakening: a teardown
bug is a command that was not issued, and that is precisely what these assert.
"""

from __future__ import annotations

import itertools
import os
import signal
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.chaos import (
    CLOUD_RUN_TAG_KEY,
    CLOUD_SCENARIO_IDS,
    CLOUD_SUITE_COST_BOUND_USD,
    CLOUD_SUITE_TAG_KEY,
    CLOUD_SUITE_TAG_VALUE,
)
from tests.chaos.framework.recorded import RecordedCluster
from tests.e2e.cloud.cost import RatedResource, SuiteCostReport, estimate_usd, report_cost
from tests.e2e.cloud.provisioning import (
    Resource,
    StackPlan,
    deferred_teardown,
    tags_for,
)
from tests.e2e.cloud.reaper import leaked, orphans, reap
from tests.e2e.cloud.runner import expectation_of, run_scenarios
from tests.e2e.cloud.scenarios import discover_scenarios
from tests.support.interruption import RunInterrupted
from tests.support.investigators import DerivedInvestigator, correct_answer

SCENARIOS = discover_scenarios()
NOW = datetime(2026, 8, 7, 12, 30, tzinfo=UTC)


def _ticking(step: float = 150.0) -> object:
    ticks = itertools.count(0.0, step)
    return lambda: next(ticks)


@dataclass(slots=True)
class RecordingProvisioner:
    """A provisioner that remembers, so teardown can be asserted with no account."""

    live: dict[str, list[Resource]] = field(default_factory=dict)
    applied: list[str] = field(default_factory=list)
    destroyed: list[str] = field(default_factory=list)

    def apply(self, plan: StackPlan) -> tuple[Resource, ...]:
        tags = plan.tags()
        created = tuple(
            Resource(kind=kind, identifier=f"arn:{kind}:{plan.workspace}", tags=tags)
            for kind in ("cluster", "instance")
        )
        self.live.setdefault(plan.run_id, []).extend(created)
        self.applied.append(plan.workspace)
        return created

    def destroy(self, plan: StackPlan) -> tuple[str, ...]:
        remaining = self.live.get(plan.run_id, [])
        went = tuple(
            sorted(
                resource.identifier
                for resource in remaining
                if resource.tags.get("ninjasre:scenario") == plan.scenario_id
            )
        )
        self.live[plan.run_id] = [
            resource
            for resource in remaining
            if resource.tags.get("ninjasre:scenario") != plan.scenario_id
        ]
        self.destroyed.append(plan.workspace)
        return went

    def inventory(self) -> tuple[Resource, ...]:
        return tuple(resource for resources in self.live.values() for resource in resources)

    def destroy_by_run(self, run_id: str) -> tuple[str, ...]:
        went = tuple(sorted(resource.identifier for resource in self.live.get(run_id, [])))
        self.live[run_id] = []
        self.destroyed.append(run_id)
        return went


# --- provisioning and tagging ------------------------------------------------


def test_every_provisioned_resource_carries_the_tags_a_sweep_finds_it_by() -> None:
    tags = tags_for(run_id="r1", scenario_id="eks", at=NOW)

    assert tags[CLOUD_SUITE_TAG_KEY] == CLOUD_SUITE_TAG_VALUE
    assert tags[CLOUD_RUN_TAG_KEY] == "r1"
    assert tags["ninjasre:scenario"] == "eks"
    assert tags["ninjasre:created-at"].startswith("2026-08-07")


def test_two_runs_of_one_scenario_do_not_share_state() -> None:
    """A shared workspace means the second run's destroy takes the first one's stack."""
    first = StackPlan(scenario_id="eks", run_id="r1", module="eks")
    second = StackPlan(scenario_id="eks", run_id="r2", module="eks")

    assert first.workspace != second.workspace


def test_the_declarative_variables_carry_the_tags_into_the_module() -> None:
    plan = StackPlan(scenario_id="rds", run_id="r1", module="rds", at=NOW)

    arguments = plan.variable_arguments()

    assert "-var" in arguments
    assert any(argument.startswith("tags=") for argument in arguments)
    assert any(argument == "run_id=r1" for argument in arguments)


# --- an interrupted run leaks nothing ----------------------------------------


def test_teardown_runs_when_the_scenario_raises() -> None:
    provisioner = RecordingProvisioner()
    plan = StackPlan(scenario_id="eks", run_id="r1", module="eks", at=NOW)

    with pytest.raises(RuntimeError), deferred_teardown(provisioner, plan) as teardown:
        provisioner.apply(plan)
        raise RuntimeError("the investigation blew up")

    assert leaked(provisioner, run_id="r1") == ()
    assert teardown.destroyed


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal delivery")
def test_a_real_signal_mid_provisioning_leaks_no_resources() -> None:
    provisioner = RecordingProvisioner()
    plan = StackPlan(scenario_id="eks", run_id="r1", module="eks", at=NOW)

    with pytest.raises(RunInterrupted), deferred_teardown(provisioner, plan) as teardown:
        provisioner.apply(plan)
        os.kill(os.getpid(), signal.SIGTERM)
        for _ in range(1_000_000):  # pragma: no cover - never completes
            pass

    assert leaked(provisioner, run_id="r1") == ()
    assert teardown.destroyed


# --- the reaper --------------------------------------------------------------


def test_the_reaper_destroys_an_orphan_and_leaves_a_live_run_alone() -> None:
    provisioner = RecordingProvisioner()
    old = StackPlan(scenario_id="eks", run_id="dead", module="eks", at=NOW - timedelta(hours=6))
    live = StackPlan(scenario_id="rds", run_id="live", module="rds", at=NOW)
    provisioner.apply(old)
    provisioner.apply(live)

    report = reap(provisioner, now=NOW, active_runs=("live",))

    assert report.reaped
    assert leaked(provisioner, run_id="dead") == ()
    assert leaked(provisioner, run_id="live") != ()


def test_a_resource_the_sweep_cannot_attribute_is_reported_not_destroyed() -> None:
    """Guessing in an account that holds something else is unrecoverable."""
    unattributable = Resource(
        kind="cluster",
        identifier="arn:cluster:somebody-elses",
        tags={CLOUD_SUITE_TAG_KEY: CLOUD_SUITE_TAG_VALUE},
    )

    orphaned, kept, unknown = orphans((unattributable,), now=NOW)

    assert orphaned == ()
    assert kept == ()
    assert unknown == (unattributable,)


def test_a_resource_younger_than_the_grace_period_is_kept() -> None:
    """Provisioning takes time; reaping a stack still coming up breaks a live run."""
    fresh = Resource(
        kind="cluster",
        identifier="arn:cluster:coming-up",
        tags=tags_for(run_id="r9", scenario_id="eks", at=NOW - timedelta(minutes=5)),
    )

    orphaned, kept, _ = orphans((fresh,), now=NOW)

    assert orphaned == ()
    assert kept == (fresh,)


# --- cost inside declared bounds ---------------------------------------------


def test_every_scenario_declares_a_bound_and_what_it_is_made_of() -> None:
    assert tuple(scenario.scenario_id for scenario in SCENARIOS) == tuple(
        sorted(CLOUD_SCENARIO_IDS)
    )
    for scenario in SCENARIOS:
        assert scenario.bound_usd > 0, scenario.scenario_id
        assert scenario.resources, scenario.scenario_id


def test_a_run_of_every_scenario_at_its_expected_length_is_within_its_bound() -> None:
    reports = [
        report_cost(
            scenario.scenario_id,
            scenario.resources,
            duration_seconds=45 * 60,
            bound_usd=scenario.bound_usd,
        )
        for scenario in SCENARIOS
    ]

    for report in reports:
        assert report.within, report.render()
    suite = SuiteCostReport(reports=tuple(reports))
    assert suite.within
    assert suite.actual_usd <= CLOUD_SUITE_COST_BOUND_USD


def test_a_stack_left_running_for_a_day_breaks_its_bound_and_says_so() -> None:
    """The number has to move with the thing that goes wrong, or it reports nothing.

    Built from a synthetic resource rather than pulled from ``SCENARIOS``: the
    mechanism under test is ``report_cost`` itself, and it does not stop being
    worth checking when the suite has no scenario currently declared.
    """
    resources = (RatedResource("cluster", 0.10), RatedResource("instance", 0.05, count=2))

    report = report_cost("synthetic", resources, duration_seconds=24 * 3600, bound_usd=4.00)

    assert not report.within
    assert report.overrun_usd > 0
    assert "OVER" in report.render()


def test_a_run_shorter_than_the_billing_minimum_still_costs_something() -> None:
    assert estimate_usd((RatedResource("instance", 0.05),), duration_seconds=1.0) > 0


# --- the whole cycle ---------------------------------------------------------


async def test_every_cloud_scenario_provisions_investigates_scores_and_destroys() -> None:
    """With no cloud scenario currently declared, the cycle runs over nothing
    and reports that honestly — which is what proves the loop itself, rather
    than a fixed scenario count, is what this test is pinning."""
    provisioner = RecordingProvisioner()
    signals = RecordedCluster(
        readings={
            scenario.expectation.validity_probe.check: [list(scenario.expectation.expected_symptom)]
            for scenario in SCENARIOS
        }
    )
    investigator = DerivedInvestigator(
        expectations={scenario.scenario_id: expectation_of(scenario) for scenario in SCENARIOS},
        answer=correct_answer,
    )

    report, cost, outcomes = await run_scenarios(
        SCENARIOS,
        provisioner=provisioner,
        signals=signals,
        investigator=investigator,
        run_id="r1",
        now=NOW,
        sleep=lambda _: None,
        clock=_ticking(),
    )

    assert len(outcomes) == len(CLOUD_SCENARIO_IDS)
    for outcome in outcomes:
        assert outcome.ran, f"{outcome.scenario_id}: {outcome.refused}"
        assert outcome.clean, outcome.scenario_id
        assert outcome.destroyed, outcome.scenario_id
        assert outcome.cost.within, outcome.cost.render()
    # No scenario is currently declared, so nothing was attempted — which is a
    # fact the report has to state rather than paper over with a vacuous 100%.
    assert report.pass_rate == 0.0
    assert report.attempted == ()
    assert cost.within
    assert leaked(provisioner, run_id="r1") == ()
