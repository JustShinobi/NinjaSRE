"""The properties the whole shipped set has to hold, asserted over the whole set.

The value of a test here is that it is parameterised over every detector rather
than written per detector. Thirty-odd shipped detectors is thirty-odd chances to
ship a threshold nobody can justify, and the only thing that keeps that from
happening as detectors are added is a test that fails on the next one.
"""

from __future__ import annotations

import pytest

from config.constants.guardian import BLIND_SPOT_DETECTOR_ID
from config.constants.observation import (
    MAX_DETECTOR_ID_CHARS,
    MAX_DETECTOR_WINDOW_SECONDS,
    MAX_DETECTORS,
    MIN_DETECTOR_DURATION_SECONDS,
)
from platform.guardian.catalogue import (
    SHIPPED_DETECTORS,
    Reading,
    ShippedDetector,
    SignalOrigin,
    detector_by_id,
)
from platform.guardian.topology import ClusterShape, TopologyRequirement
from platform.observation.detectors.model import ConditionKind

pytestmark = pytest.mark.unit

IDS = [detector.detector_id for detector in SHIPPED_DETECTORS]


def test_the_shipped_set_covers_every_domain_the_feature_names() -> None:
    """Cluster, storage, guest, backup, maintenance and the host layer."""
    prefixes = {detector.detector_id.split("-")[0] for detector in SHIPPED_DETECTORS}

    assert {"cluster", "storage", "guest", "backup", "maintenance", "host"} <= prefixes


def test_the_shipped_set_fits_inside_the_platform_bound() -> None:
    """A shipped set larger than one deployment may hold is one that silently truncates."""
    assert 0 < len(SHIPPED_DETECTORS) <= MAX_DETECTORS


def test_no_two_shipped_detectors_share_an_identifier() -> None:
    assert len(set(IDS)) == len(IDS)


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_every_shipped_detector_states_a_threshold_a_rationale_and_a_remedy(
    detector: ShippedDetector,
) -> None:
    """SC-003 and NFR-005, asserted over the whole set rather than spot-checked."""
    assert detector.threshold.strip(), detector.detector_id
    assert detector.rationale.strip(), detector.detector_id
    assert detector.remedy.strip(), detector.detector_id
    assert detector.watches.strip(), detector.detector_id


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_every_rationale_says_more_than_the_threshold_repeats(
    detector: ShippedDetector,
) -> None:
    """A rationale that restates the number is a number with no reason beside it."""
    assert len(detector.rationale.split()) >= 8, detector.detector_id
    assert detector.rationale != detector.threshold, detector.detector_id


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_every_shipped_detector_builds_a_valid_declaration(
    detector: ShippedDetector,
) -> None:
    """The shipped set goes through the same validation an operator's own does."""
    declaration = detector.declaration()

    assert declaration.detector_id == detector.detector_id
    assert len(declaration.detector_id) <= MAX_DETECTOR_ID_CHARS
    assert declaration.description
    assert declaration.for_seconds >= MIN_DETECTOR_DURATION_SECONDS
    assert declaration.longest_window_seconds <= MAX_DETECTOR_WINDOW_SECONDS


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_every_shipped_detector_names_the_resource_kinds_it_applies_to(
    detector: ShippedDetector,
) -> None:
    """An unbounded detector evaluates every resource in the estate every tick."""
    assert detector.resource_kinds, detector.detector_id


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_a_published_reading_names_what_publishes_it(detector: ShippedDetector) -> None:
    """ "Unavailable" with no next step is a dead end, and this one has a short fix."""
    if detector.origin is SignalOrigin.PUBLISHED:
        assert detector.matcher.strip(), detector.detector_id
    else:
        assert not detector.matcher, detector.detector_id


@pytest.mark.parametrize("detector", SHIPPED_DETECTORS, ids=IDS)
def test_every_signal_is_namespaced_to_the_guardian(detector: ShippedDetector) -> None:
    """A reading, not a metric a particular exporter happens to publish."""
    assert detector.signal.startswith("guardian."), detector.detector_id


def test_a_detector_without_a_rationale_is_refused_at_construction() -> None:
    """NFR-005: a threshold with no rationale fails, and it fails here."""
    with pytest.raises(ValueError, match="rationale"):
        ShippedDetector(
            detector_id="storage-invented",
            name="Invented",
            watches="a datastore",
            threshold="above 80%",
            rationale="   ",
            remedy="free some space",
            signal="guardian.storage.usage",
            resource_kinds=("datastore",),
            firing=Reading(value=96.0),
            healthy=Reading(value=56.0),
            fire_value=80.0,
            clear_value=75.0,
        )


def test_a_detector_without_a_remedy_is_refused_at_construction() -> None:
    """A finding an operator cannot act on is an interruption, not information."""
    with pytest.raises(ValueError, match="remedy"):
        ShippedDetector(
            detector_id="storage-invented",
            name="Invented",
            watches="a datastore",
            threshold="above 80%",
            rationale="eighty is where a snapshot starts failing on this pool shape",
            remedy="",
            signal="guardian.storage.usage",
            resource_kinds=("datastore",),
            firing=Reading(value=96.0),
            healthy=Reading(value=56.0),
            fire_value=80.0,
            clear_value=75.0,
        )


# -- topology gating ---------------------------------------------------------------


def test_the_two_node_detectors_are_the_ones_about_quorum_arithmetic() -> None:
    """FR-014, and it is a short list on purpose."""
    two_node = {
        detector.detector_id
        for detector in SHIPPED_DETECTORS
        if detector.topology is TopologyRequirement.TWO_NODE
    }

    assert two_node == {"cluster-quorum-margin-zero", "cluster-two-node-quorum-survival"}


def test_no_cluster_detector_claims_to_work_on_a_single_node() -> None:
    """SC-007: quorum on a machine with no quorum to lose is not a finding."""
    for detector in SHIPPED_DETECTORS:
        if detector.detector_id.startswith("cluster-"):
            assert not detector.topology.activates_on(ClusterShape.SINGLE_NODE), (
                detector.detector_id
            )


#: The one detector outside the cluster domain that needs more than one node.
#: Replication is a copy onto *another* node, so on a single-node installation
#: there is nowhere for it to go and "no replication jobs" is the arrangement
#: rather than a finding.
NEEDS_A_SECOND_NODE = {"backup-no-replication-jobs"}


def test_storage_and_backup_detectors_apply_at_every_size() -> None:
    """A single node's datastore fills exactly as a cluster's does."""
    for detector in SHIPPED_DETECTORS:
        if detector.detector_id in NEEDS_A_SECOND_NODE:
            continue
        if detector.detector_id.split("-")[0] in {"storage", "backup", "guest", "maintenance"}:
            assert detector.topology is TopologyRequirement.ANY, detector.detector_id


def test_nothing_that_needs_a_second_node_would_fire_on_a_single_one() -> None:
    """SC-007 beyond the cluster prefix: a single-node install must not be told
    it has no replication onto a node it does not have."""
    for detector_id in NEEDS_A_SECOND_NODE:
        detector = detector_by_id(detector_id)
        assert detector is not None
        assert not detector.activates_on(ClusterShape.SINGLE_NODE), detector_id
        assert detector.activates_on(ClusterShape.MULTI_NODE), detector_id


# -- the specific detectors the field baseline demanded ------------------------------


@pytest.mark.parametrize(
    "detector_id",
    [
        "cluster-quorum-margin-zero",
        "cluster-quorum-device-not-contributing",
        "storage-thin-pool-metadata",
        "storage-guest-volume-near-full",
        "storage-datastore-status-unknown",
        "backup-job-disabled",
        "backup-guest-uncovered",
        "backup-retention-below-floor",
        "backup-no-replication-jobs",
        "maintenance-kernel-never-booted",
        "host-systemd-units-failed",
        "host-bridge-down",
        BLIND_SPOT_DETECTOR_ID,
    ],
)
def test_the_conditions_a_real_cluster_is_in_right_now_all_have_a_detector(
    detector_id: str,
) -> None:
    """Each of these is true in the surveyed cluster today or caused a documented
    incident there. They are the reason the shipped set is not a generic one."""
    assert detector_by_id(detector_id) is not None


def test_the_kernel_detector_is_not_a_softer_reboot_required_detector() -> None:
    """They read different signals, because the whole point is that the usual one
    is silent: the package is installed, ``/var/run/reboot-required`` is absent,
    and the first boot of that kernel will be an unplanned one."""
    unbooted = detector_by_id("maintenance-kernel-never-booted")
    reboot = detector_by_id("maintenance-reboot-required")

    assert unbooted is not None and reboot is not None
    assert unbooted.signal != reboot.signal


def test_the_blind_spot_detector_is_cleared_by_acknowledgement_not_by_recovery() -> None:
    """FR-013b: it is a structural finding, so waiting does not resolve it."""
    detector = detector_by_id(BLIND_SPOT_DETECTOR_ID)

    assert detector is not None
    assert detector.acknowledged_to_clear
    assert detector.condition_kind is ConditionKind.STATE_TRANSITION


def test_no_other_detector_is_cleared_by_acknowledgement() -> None:
    """Every other condition is one that can actually stop being true."""
    acknowledged = [
        detector.detector_id for detector in SHIPPED_DETECTORS if detector.acknowledged_to_clear
    ]

    assert acknowledged == [BLIND_SPOT_DETECTOR_ID]
