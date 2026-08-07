"""The end-to-end suites as ``pytest`` sees them: skipped without infrastructure.

Two skips with two different reasons, because the two suites need two different
things and telling somebody "no infrastructure" when they have a cluster and no
cloud account sends them to the wrong place.

What still runs everywhere is the part that needs nothing: every declaration
this repository ships loads, and every cloud scenario has a cost bound. Those
are the checks that catch a broken declaration on the pull request rather than
at four in the morning before a release.
"""

from __future__ import annotations

import os

import pytest

from config.constants.chaos import (
    CLOUD_SUITE_COST_BOUND_USD,
    NINJASRE_CHAOS_CONTEXT_ENV,
    NINJASRE_CHAOS_KUBECONFIG_ENV,
)
from tests.chaos.framework.cluster import cluster_availability, skip_reason
from tests.e2e.cloud.cost import SuiteCostReport, report_cost
from tests.e2e.cloud.scenarios import discover_scenarios
from tests.e2e.otel_demo.faults import discover_faults
from tests.e2e.otel_demo.install import DemoInstallation, missing_workloads
from tests.support.commands import SubprocessRunner, executable_present

CLUSTER = cluster_availability(
    kubeconfig=os.environ.get(NINJASRE_CHAOS_KUBECONFIG_ENV, ""),
    context=os.environ.get(NINJASRE_CHAOS_CONTEXT_ENV, ""),
)
CLUSTER_SKIP = skip_reason(CLUSTER)

#: The cloud suite provisions real infrastructure, so it needs both the provider's
#: own tool and an explicit opt-in. Having credentials configured is not consent
#: to spend money.
CLOUD_SKIP = (
    ""
    if executable_present("aws") and os.environ.get("NINJASRE_E2E_CLOUD")
    else (
        "the cloud suite provisions real infrastructure: it needs the provider CLI and "
        "NINJASRE_E2E_CLOUD set, or run 'make e2e-cloud', which sets it"
    )
)


# --- what runs everywhere ----------------------------------------------------


def test_every_demo_fault_and_cloud_scenario_this_repository_ships_loads() -> None:
    assert discover_faults()
    assert discover_scenarios()


def test_the_declared_cloud_scenarios_fit_inside_the_suite_ceiling() -> None:
    """On the pull-request path: a scenario added without revisiting the total
    is exactly the change this catches."""
    reports = [
        report_cost(
            scenario.scenario_id,
            scenario.resources,
            duration_seconds=45 * 60,
            bound_usd=scenario.bound_usd,
        )
        for scenario in discover_scenarios()
    ]

    suite = SuiteCostReport(reports=tuple(reports))
    assert suite.within, suite.render()
    assert suite.actual_usd <= CLOUD_SUITE_COST_BOUND_USD


# --- what needs a cluster ----------------------------------------------------


@pytest.mark.e2e
@pytest.mark.skipif(bool(CLUSTER_SKIP), reason=CLUSTER_SKIP or "a cluster is here")
def test_the_demo_is_installed_and_every_workload_it_needs_is_up() -> None:
    missing = missing_workloads(SubprocessRunner(), DemoInstallation())

    assert not missing, f"not ready: {', '.join(missing)}; run 'make e2e-demo-setup'"


# --- what needs a cloud account ----------------------------------------------


@pytest.mark.e2e
@pytest.mark.skipif(bool(CLOUD_SKIP), reason=CLOUD_SKIP or "the cloud suite is enabled")
def test_the_account_holds_nothing_this_suite_left_behind() -> None:
    """The leak check as a standing assertion rather than a per-run one.

    Run on the schedule, this is the assertion that catches a leak the runs
    themselves reported as clean — which is the only kind that accumulates.
    """
    from tests.e2e.cloud.provisioning import DeclarativeProvisioner
    from tests.e2e.cloud.reaper import reap

    report = reap(DeclarativeProvisioner(runner=SubprocessRunner()), dry_run=True)

    assert not report.reaped, report.render()
    assert not report.unattributable, report.render()
