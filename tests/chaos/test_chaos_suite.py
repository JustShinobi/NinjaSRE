"""The chaos suite as ``pytest`` sees it: skipped without a cluster, run with one.

This module is why skipping cleanly is a property rather than an intention. It is
collected by every ``make verify`` on every machine, and on a machine with no
cluster it skips with a sentence naming what is missing and the one command that
fixes it — rather than failing the gate, which would make the whole suite
something people delete.

The decision and the message come from ``cluster_availability``, which is
asserted directly in the unit suite. Nothing here re-decides anything.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from config.constants.chaos import (
    NINJASRE_CHAOS_CONTEXT_ENV,
    NINJASRE_CHAOS_KUBECONFIG_ENV,
    NINJASRE_CHAOS_LOCK_DIR_ENV,
)
from tests.chaos.framework.catalogue import EXPERIMENTS_ROOT, discover_experiments
from tests.chaos.framework.cluster import cluster_availability, skip_reason
from tests.chaos.framework.kubectl import KubectlCluster
from tests.chaos.framework.preflight import preflight
from tests.support.commands import SubprocessRunner

KUBECONFIG = os.environ.get(NINJASRE_CHAOS_KUBECONFIG_ENV, "")
CONTEXT = os.environ.get(NINJASRE_CHAOS_CONTEXT_ENV, "")
LOCK_ROOT = Path(os.environ.get(NINJASRE_CHAOS_LOCK_DIR_ENV, "") or ".chaos-locks")

AVAILABILITY = cluster_availability(kubeconfig=KUBECONFIG, context=CONTEXT)
SKIP = skip_reason(AVAILABILITY)

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(bool(SKIP), reason=SKIP or "a cluster is here")]


@pytest.fixture(name="cluster")
def _cluster() -> KubectlCluster:
    return KubectlCluster(
        runner=SubprocessRunner(), context=CONTEXT or AVAILABILITY.context, kubeconfig=KUBECONFIG
    )


def test_the_cluster_is_a_healthy_baseline_before_anything_is_injected(
    cluster: KubectlCluster,
) -> None:
    """An experiment on a cluster that was already broken measures the cluster."""
    report = preflight(cluster)

    assert report.healthy, report.summary


def test_every_experiment_this_repository_ships_is_loadable_against_this_cluster() -> None:
    experiments = discover_experiments(EXPERIMENTS_ROOT)

    assert experiments
    for experiment in experiments:
        assert experiment.manifest["apiVersion"].startswith("chaos-mesh.org/")


@pytest.mark.skipif(
    not os.environ.get("NINJASRE_CHAOS_RUN"),
    reason=(
        "the full chaos cycle injects real faults; set NINJASRE_CHAOS_RUN to run it, or use "
        "'make chaos-run', which does"
    ),
)
async def test_the_whole_suite_injects_investigates_scores_and_cleans_up(
    cluster: KubectlCluster,
) -> None:
    """The pre-release run. Deliberately opt-in: it breaks a real cluster.

    An investigator is not constructed here. Composing one needs a provider and
    the operator's own credentials, which is a deployment question rather than a
    test one — ``make chaos-run`` is the entry point that supplies it.
    """
    from tests.chaos.runner import expectation_of, run_suite
    from tests.support.investigators import DerivedInvestigator, correct_answer

    experiments = discover_experiments(EXPERIMENTS_ROOT)
    report, outcomes = await run_suite(
        experiments,
        cluster=cluster,
        investigator=DerivedInvestigator(
            expectations={found.experiment_id: expectation_of(found) for found in experiments},
            answer=correct_answer,
        ),
        run_id=uuid.uuid4().hex[:8],
        lock_root=LOCK_ROOT,
    )

    for outcome in outcomes:
        assert outcome.cleanup.clean, f"{outcome.experiment_id}: {outcome.cleanup.failures}"
    assert not report.inconclusive, [run.key for run in report.inconclusive]
