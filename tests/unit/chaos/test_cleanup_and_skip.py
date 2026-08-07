"""The two properties the chaos framework is built around, asserted first.

**Cleanup survives interruption.** A chaos run that is stopped part-way through
must not leave the fault it injected running against a cluster somebody else is
about to use. That is asserted here for the three ways a run stops early — an
exception, a keyboard interrupt, and a real signal delivered to this process —
because they take three different paths out of the block and only one of them
is the one people remember to handle.

**No cluster means a clear skip.** A suite that needs infrastructure and does
not have it has to say so in a sentence somebody can act on. Failing would make
the whole gate red on every laptop; skipping silently would let the suite
quietly stop running in CI and nobody would notice for a quarter.
"""

from __future__ import annotations

import os
import signal

import pytest

from tests.chaos.framework.cleanup import (
    CleanupLedger,
    FaultRecord,
    RunInterrupted,
    clean_up,
    deferred_cleanup,
    sweep_orphans,
)
from tests.chaos.framework.cluster import cluster_availability, skip_reason
from tests.chaos.framework.recorded import RecordedCluster

POD_KILL = FaultRecord(
    experiment_id="pod-kill", kind="PodChaos", name="pod-kill-run1", namespace="chaos-testing"
)


def _injected(cluster: RecordedCluster, ledger: CleanupLedger) -> None:
    """Register and apply one fault, the way the injector does."""
    ledger.register(POD_KILL)
    cluster.apply(
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": POD_KILL.kind,
            "metadata": {"name": POD_KILL.name, "namespace": POD_KILL.namespace},
        }
    )


# --- cleanup on interruption -------------------------------------------------


def test_an_exception_mid_experiment_leaves_no_fault_active() -> None:
    cluster = RecordedCluster()

    with pytest.raises(RuntimeError), deferred_cleanup(cluster) as ledger:
        _injected(cluster, ledger)
        assert cluster.active_faults()
        raise RuntimeError("the investigation blew up half way through")

    assert cluster.active_faults() == ()


def test_a_keyboard_interrupt_mid_experiment_leaves_no_fault_active() -> None:
    cluster = RecordedCluster()

    with pytest.raises(KeyboardInterrupt), deferred_cleanup(cluster) as ledger:
        _injected(cluster, ledger)
        raise KeyboardInterrupt

    assert cluster.active_faults() == ()


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal delivery")
def test_a_real_signal_mid_experiment_leaves_no_fault_active() -> None:
    """The case the other two do not cover: the runner is signalled, not raised in.

    ``SIGTERM`` is what a CI cancellation sends, and its default disposition
    ends the process without unwinding anything — so the fault would outlive the
    run unless the handler removes it before the process goes.
    """
    cluster = RecordedCluster()

    with pytest.raises(RunInterrupted) as caught, deferred_cleanup(cluster) as ledger:
        _injected(cluster, ledger)
        os.kill(os.getpid(), signal.SIGTERM)
        # The handler raises before this ever runs; the loop is only here so
        # the signal has an interruptible instruction to land on.
        for _ in range(1_000_000):  # pragma: no cover - never completes
            pass

    assert "SIGTERM" in str(caught.value)
    assert cluster.active_faults() == ()


def test_the_signal_handlers_are_put_back_after_a_normal_run() -> None:
    """A suite that left its handlers installed would swallow the next Ctrl-C."""
    before = signal.getsignal(signal.SIGINT)

    with deferred_cleanup(RecordedCluster()):
        pass

    assert signal.getsignal(signal.SIGINT) is before


def test_a_deletion_that_fails_is_reported_rather_than_swallowed() -> None:
    """Cleanup that cannot remove a fault must say so; the cluster is not clean."""
    cluster = RecordedCluster(delete_failures={"pod-kill-run1"})
    ledger = CleanupLedger()
    _injected(cluster, ledger)

    report = clean_up(cluster, ledger)

    assert not report.clean
    assert any("pod-kill-run1" in failure for failure in report.failures)


def test_cleanup_verifies_the_cluster_came_back_to_baseline() -> None:
    cluster = RecordedCluster(unhealthy_pods=("checkout-7f4c",))
    ledger = CleanupLedger()
    _injected(cluster, ledger)

    report = clean_up(cluster, ledger)

    assert cluster.active_faults() == ()
    assert not report.baseline_restored
    assert any("checkout-7f4c" in reason for reason in report.baseline_reasons)


def test_a_fault_a_killed_run_never_registered_is_still_swept() -> None:
    """``SIGKILL`` runs no handler, so the ledger is not the only line of defence.

    Everything this suite applies carries its own label, and the sweep removes
    what carries it regardless of which run put it there.
    """
    cluster = RecordedCluster()
    cluster.apply(
        {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "NetworkChaos",
            "metadata": {"name": "orphan-from-a-killed-run", "namespace": "chaos-testing"},
        }
    )

    swept = sweep_orphans(cluster)

    assert swept == ("NetworkChaos/chaos-testing/orphan-from-a-killed-run",)
    assert cluster.active_faults() == ()


# --- skipping without infrastructure -----------------------------------------


def test_no_kubectl_skips_with_a_message_naming_what_is_missing() -> None:
    availability = cluster_availability(which=lambda _: None)

    assert not availability.available
    assert "kubectl" in availability.reason
    assert "make chaos-setup" in availability.reason


def test_an_unreachable_cluster_skips_with_the_reason_it_gave() -> None:
    availability = cluster_availability(
        which=lambda _: "/usr/bin/kubectl",
        reach=lambda: (False, "connection refused to 127.0.0.1:6443"),
    )

    assert not availability.available
    assert "connection refused" in availability.reason


def test_a_reachable_cluster_is_available_and_names_its_context() -> None:
    availability = cluster_availability(
        which=lambda _: "/usr/bin/kubectl",
        reach=lambda: (True, "kind-ninjasre"),
    )

    assert availability.available
    assert availability.context == "kind-ninjasre"
    assert availability.reason == ""


def test_the_skip_reason_is_empty_exactly_when_the_suite_can_run() -> None:
    """What a module-level ``pytest.skip`` reads, so the two cannot disagree."""
    assert skip_reason(cluster_availability(which=lambda _: None)) != ""
    assert (
        skip_reason(
            cluster_availability(which=lambda _: "/usr/bin/kubectl", reach=lambda: (True, "kind"))
        )
        == ""
    )
