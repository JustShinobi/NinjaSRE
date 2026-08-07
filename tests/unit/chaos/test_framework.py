"""The rest of the chaos apparatus: the catalogue, injection, validity, the lock.

The assertions worth reading are the ones about *what separates two things that
look alike*. An experiment that never bit and an agent that got it wrong both
produce a failed score; a lock held by a live run and one left by a dead one
both produce a file. Getting either of those pairs the wrong way round makes the
suite report confidently on something that did not happen.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from config.constants.chaos import (
    CHAOS_EXPERIMENT_IDS,
    CHAOS_EXPERIMENT_LABEL,
    CHAOS_SUITE_LABEL,
    CHAOS_SUITE_LABEL_VALUE,
)
from core.domain.alerts.normalisation import detect_source, normalise
from tests.chaos.framework.alerts import alert_for
from tests.chaos.framework.catalogue import (
    EXPERIMENTS_ROOT,
    ExperimentError,
    discover_experiments,
    load_experiment,
)
from tests.chaos.framework.cleanup import CleanupLedger
from tests.chaos.framework.cluster import ClusterResource
from tests.chaos.framework.injector import InjectionError, inject, prepare_manifest
from tests.chaos.framework.lock import ClusterBusy, cluster_lock, held_by
from tests.chaos.framework.recorded import RecordedCluster
from tests.chaos.framework.validity import Validity, probe_validity


@pytest.fixture(name="dns_error")
def _dns_error() -> object:
    return load_experiment(EXPERIMENTS_ROOT / "dns-error")


# --- the catalogue -----------------------------------------------------------


def test_every_declared_experiment_is_on_disk_and_loads() -> None:
    found = discover_experiments(EXPERIMENTS_ROOT)

    assert tuple(experiment.experiment_id for experiment in found) == tuple(
        sorted(CHAOS_EXPERIMENT_IDS)
    )


def test_every_experiment_declares_its_symptom_and_its_cause_before_it_runs() -> None:
    for experiment in discover_experiments(EXPERIMENTS_ROOT):
        assert experiment.expectation.expected_symptom, experiment.experiment_id
        assert experiment.expectation.expected_root_cause_category, experiment.experiment_id
        assert experiment.expectation.required_keywords, experiment.experiment_id
        assert experiment.expectation.validity_probe.check, experiment.experiment_id


def test_an_experiment_whose_probe_is_missing_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "dns-error"
    directory.mkdir()
    (directory / "chaos.yaml").write_text(
        "apiVersion: chaos-mesh.org/v1alpha1\nkind: DNSChaos\n"
        "metadata:\n  name: dns-error\n  namespace: chaos-testing\n",
        encoding="utf-8",
    )
    (directory / "alert.json").write_text(json.dumps({"payload": {}}), encoding="utf-8")
    (directory / "expected.yml").write_text(
        "experiment_id: dns-error\ninjected_fault: dns_resolution_failure\n"
        "failure_mode: dns_failure\nseverity: critical\ndifficulty: 2\n"
        "integrations: [kubernetes]\navailable_evidence: [kubernetes]\n"
        "expected_symptom: [service_unreachable]\n"
        "expected_root_cause_category: network_failure\nrequired_keywords: [dns]\n",
        encoding="utf-8",
    )

    with pytest.raises(ExperimentError, match="validity_probe"):
        load_experiment(directory)


# --- injection ---------------------------------------------------------------


def test_a_prepared_manifest_carries_the_labels_a_sweep_finds_it_by(
    dns_error: object,
) -> None:
    manifest = prepare_manifest(dns_error.manifest, experiment_id="dns-error", run_id="r1")  # type: ignore[attr-defined]

    labels = manifest["metadata"]["labels"]
    assert labels[CHAOS_SUITE_LABEL] == CHAOS_SUITE_LABEL_VALUE
    assert labels[CHAOS_EXPERIMENT_LABEL] == "dns-error"
    assert manifest["metadata"]["name"].endswith("-r1")


def test_a_manifest_outside_the_chaos_api_group_is_refused() -> None:
    with pytest.raises(InjectionError, match="chaos-mesh.org"):
        prepare_manifest(
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "payments"}},
            experiment_id="pod-kill",
            run_id="r1",
        )


def test_the_fault_is_registered_for_removal_before_it_is_applied(
    dns_error: object,
) -> None:
    """The window between applying and registering is where an interruption leaks."""
    ledger = CleanupLedger()
    registered_when_applied: list[int] = []

    class Watching(RecordedCluster):
        def apply(self, manifest: object) -> ClusterResource:  # type: ignore[override]
            registered_when_applied.append(len(ledger))
            return super().apply(manifest)  # type: ignore[arg-type]

    inject(Watching(), dns_error, ledger=ledger, run_id="r1")  # type: ignore[arg-type]

    assert registered_when_applied == [1]


def test_an_apply_that_fails_leaves_the_registration_behind_to_be_swept(
    dns_error: object,
) -> None:
    """A refused apply may still have created the object; assuming it did is cheaper."""
    ledger = CleanupLedger()
    cluster = RecordedCluster(apply_failure="the admission webhook is unavailable")

    with pytest.raises(InjectionError):
        inject(cluster, dns_error, ledger=ledger, run_id="r1")  # type: ignore[arg-type]

    assert len(ledger) == 1


# --- validity ----------------------------------------------------------------


def _ticking(step: float = 25.0) -> object:
    """Return a clock that advances by ``step`` every time it is read.

    Real seconds rather than a fake clock would make the invalid case wait out
    the whole sixty-second timeout, which is a minute of a suite that is
    supposed to take seconds.
    """
    ticks = itertools.count(0.0, step)
    return lambda: next(ticks)


def test_an_experiment_that_produced_its_symptom_is_valid(dns_error: object) -> None:
    cluster = RecordedCluster(
        readings={
            "dns_lookup_fails_from_pod": [[], ["service_unreachable", "connection_timeout_errors"]]
        }
    )

    verdict = probe_validity(
        cluster,
        dns_error.expectation,  # type: ignore[attr-defined]
        sleep=lambda _: None,
        clock=_ticking(),  # type: ignore[arg-type]
    )

    assert verdict.validity is Validity.VALID
    assert "service_unreachable" in verdict.observed
    assert verdict.looks == 2


def test_an_experiment_that_never_bit_is_invalid_rather_than_an_agent_failure(
    dns_error: object,
) -> None:
    cluster = RecordedCluster(
        readings={"dns_lookup_fails_from_pod": [["connection_timeout_errors"]]}
    )

    verdict = probe_validity(
        cluster,
        dns_error.expectation,  # type: ignore[attr-defined]
        sleep=lambda _: None,
        clock=_ticking(),  # type: ignore[arg-type]
    )

    assert verdict.validity is Validity.INVALID
    assert "service_unreachable" in verdict.missing
    assert "did not produce" in verdict.detail


def test_a_probe_nothing_answers_is_unknown_not_invalid(dns_error: object) -> None:
    """A probe that could not be read says nothing about whether the fault bit.

    Reporting it as invalid would retire a working experiment; reporting it as
    valid would score the agent against telemetry nobody confirmed.
    """
    cluster = RecordedCluster(readings={})

    verdict = probe_validity(
        cluster,
        dns_error.expectation,  # type: ignore[attr-defined]
        sleep=lambda _: None,
        clock=_ticking(),  # type: ignore[arg-type]
    )

    assert verdict.validity is Validity.UNKNOWN


# --- alerts ------------------------------------------------------------------


def test_the_generated_alert_enters_the_pipeline_where_a_real_one_does(
    dns_error: object,
) -> None:
    from datetime import UTC, datetime

    from tests.chaos.framework.cleanup import FaultRecord

    fault = FaultRecord(
        experiment_id="dns-error", kind="DNSChaos", name="dns-error-r1", namespace="chaos-testing"
    )
    raw = alert_for(dns_error, fault, at=datetime(2026, 8, 7, 12, 30, tzinfo=UTC))  # type: ignore[arg-type]

    assert detect_source(raw).value == "alertmanager"
    alert = normalise(raw)
    assert alert.components
    assert alert.labels["ninjasre_experiment"] == "dns-error"


# --- the cluster lock --------------------------------------------------------


def test_a_second_run_against_the_same_cluster_is_refused(tmp_path: Path) -> None:
    with (
        cluster_lock("kind-ninjasre", root=tmp_path, run_id="first"),
        pytest.raises(ClusterBusy, match="first"),
        cluster_lock("kind-ninjasre", root=tmp_path, run_id="second"),
    ):
        pass  # pragma: no cover - the lock must not be granted


def test_a_different_cluster_is_not_blocked(tmp_path: Path) -> None:
    with (
        cluster_lock("kind-ninjasre", root=tmp_path, run_id="first"),
        cluster_lock("eks-staging", root=tmp_path, run_id="second") as held,
    ):
        assert held.run_id == "second"


def test_the_lock_is_released_even_when_the_run_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError), cluster_lock("kind-ninjasre", root=tmp_path, run_id="first"):
        raise RuntimeError("the experiment blew up")

    assert held_by("kind-ninjasre", root=tmp_path) is None


def test_a_lock_left_by_a_dead_run_is_taken_over(tmp_path: Path) -> None:
    """A killed runner leaves its lock; a suite that then refuses forever is one
    people delete lock files for by hand, which defeats the lock."""
    with (
        pytest.raises(ClusterBusy),
        cluster_lock("kind-ninjasre", root=tmp_path, run_id="dead"),
        cluster_lock("kind-ninjasre", root=tmp_path, run_id="live"),
    ):
        pass  # pragma: no cover

    with (
        cluster_lock("kind-ninjasre", root=tmp_path, run_id="dead", alive=lambda _: False),
        cluster_lock("kind-ninjasre", root=tmp_path, run_id="live", alive=lambda _: False) as held,
    ):
        assert held.run_id == "live"
