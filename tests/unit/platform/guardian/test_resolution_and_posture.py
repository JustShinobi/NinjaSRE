"""The shipped set as this deployment runs it, and the two postures it picks between.

Two concerns in one file because they are the same decision seen twice: what the
deployment watches, and how much it may do about what it sees. Both are shipped
defaults an operator changes without editing anything that ships.
"""

from __future__ import annotations

import pytest

from config.constants.autonomy import RISK_CLASS_MODERATE
from platform.autonomy.configuration import policy_set_of
from platform.autonomy.policy import PolicySet
from platform.config_service.schema.policies import (
    AutonomyPolicySettings,
    DetectorOverrideSettings,
    GuardianSettings,
    PoliciesConfig,
)
from platform.guardian.catalogue import detector_by_id
from platform.guardian.posture import (
    RECOMMENDED_AUTONOMOUS_CAPABILITIES,
    PosturePreset,
    PostureProposal,
    is_propose_only,
    preset_document,
)
from platform.guardian.resolution import resolve, threshold_for
from platform.guardian.topology import ClusterShape
from platform.notifications.models import Severity

pytestmark = pytest.mark.unit


def _policies(document: dict[str, object]) -> PolicySet:
    """Return the resolved policy set a preset document produces."""
    return policy_set_of(
        PoliciesConfig(autonomy=AutonomyPolicySettings.model_validate(document)),
        source="deployment",
    )


# -- the shipped set, resolved ---------------------------------------------------


def test_a_guardian_nobody_enabled_declares_nothing_at_all() -> None:
    """FR-008: the set ships enabled by choice, not by default."""
    resolved = resolve(GuardianSettings(), shape=ClusterShape.TWO_NODE)

    assert not resolved.enabled
    assert resolved.declarations == ()


def test_enabling_it_declares_the_detectors_this_topology_supports() -> None:
    resolved = resolve(GuardianSettings(enabled=True), shape=ClusterShape.TWO_NODE)

    assert len(resolved.declarations) == len(resolved.detectors)
    assert resolved.not_applicable == ()


def test_a_single_node_installation_declares_no_cluster_detectors() -> None:
    """SC-007. Not merely "they do not fire" — they are never declared."""
    resolved = resolve(GuardianSettings(enabled=True), shape=ClusterShape.SINGLE_NODE)

    declared = {declaration.detector_id for declaration in resolved.declarations}

    assert not any(name.startswith("cluster-") for name in declared)
    assert any(name.startswith("cluster-") for name in resolved.not_applicable)


def test_a_three_node_cluster_gets_the_cluster_detectors_and_not_the_two_node_ones() -> None:
    """SC-006, the half that is easy to get wrong by gating on "clustered"."""
    resolved = resolve(GuardianSettings(enabled=True), shape=ClusterShape.MULTI_NODE)

    declared = {declaration.detector_id for declaration in resolved.declarations}

    assert "cluster-quorum-lost" in declared
    assert "cluster-quorum-margin-zero" not in declared
    assert "cluster-two-node-quorum-survival" not in declared


def test_the_two_node_detectors_are_declared_on_a_two_node_cluster() -> None:
    """SC-006, the other half."""
    resolved = resolve(GuardianSettings(enabled=True), shape=ClusterShape.TWO_NODE)

    declared = {declaration.detector_id for declaration in resolved.declarations}

    assert "cluster-quorum-margin-zero" in declared
    assert "cluster-two-node-quorum-survival" in declared


# -- overrides -------------------------------------------------------------------


def test_a_threshold_is_overridable_without_editing_the_shipped_set() -> None:
    """FR-016 and T-042."""
    settings = GuardianSettings(
        enabled=True,
        overrides=(
            DetectorOverrideSettings(
                detector_id="storage-datastore-usage-high",
                fire_value=92.0,
                reason="this array is deliberately run full",
            ),
        ),
    )

    resolved = resolve(settings, shape=ClusterShape.TWO_NODE)
    declaration = next(
        entry
        for entry in resolved.declarations
        if entry.detector_id == "storage-datastore-usage-high"
    )

    assert declaration.condition.fire_value == 92.0
    shipped = detector_by_id("storage-datastore-usage-high")
    assert shipped is not None
    assert shipped.fire_value == 85.0, "the shipped catalogue is not mutated"


def test_moving_a_firing_value_carries_its_clear_value_with_it() -> None:
    """Otherwise an override of one number refuses at construction, which reads
    to an operator as their override having broken the detector."""
    settings = GuardianSettings(
        enabled=True,
        overrides=(
            DetectorOverrideSettings(detector_id="storage-datastore-usage-high", fire_value=92.0),
        ),
    )

    resolved = resolve(settings, shape=ClusterShape.TWO_NODE)
    declaration = next(
        entry
        for entry in resolved.declarations
        if entry.detector_id == "storage-datastore-usage-high"
    )

    assert declaration.condition.clear_value == 87.0
    assert resolved.problems == ()


def test_a_per_resource_override_beats_the_deployment_wide_one() -> None:
    """One datastore that genuinely runs at ninety per cent is a fact about that
    datastore, and turning the detector off everywhere is the alternative."""
    detector = detector_by_id("storage-datastore-usage-high")
    assert detector is not None
    settings = GuardianSettings(
        enabled=True,
        overrides=(
            DetectorOverrideSettings(detector_id=detector.detector_id, fire_value=90.0),
            DetectorOverrideSettings(
                detector_id=detector.detector_id, resource_id="res-media", fire_value=97.0
            ),
        ),
    )

    assert threshold_for(detector, settings) == 90.0
    assert threshold_for(detector, settings, resource_id="res-media") == 97.0
    assert threshold_for(detector, settings, resource_id="res-other") == 90.0


def test_an_override_naming_a_detector_nobody_ships_is_reported() -> None:
    """A mistyped identifier is otherwise a threshold that never takes effect."""
    settings = GuardianSettings(
        enabled=True,
        overrides=(
            DetectorOverrideSettings(detector_id="storage-datastore-usage", fire_value=9.0),
        ),
    )

    resolved = resolve(settings, shape=ClusterShape.TWO_NODE)

    assert any(name == "storage-datastore-usage" for name, _ in resolved.problems)


def test_an_override_naming_a_severity_nobody_declared_is_reported_not_ignored() -> None:
    """Silently keeping the shipped severity would mean a notification that pages
    when it was meant not to."""
    settings = GuardianSettings(
        enabled=True,
        overrides=(
            DetectorOverrideSettings(detector_id="storage-datastore-usage-high", severity="urgent"),
        ),
    )

    resolved = resolve(settings, shape=ClusterShape.TWO_NODE)

    assert any(name == "storage-datastore-usage-high" for name, _ in resolved.problems)
    assert not any(
        entry.detector_id == "storage-datastore-usage-high" for entry in resolved.declarations
    )


def test_an_override_can_turn_one_shipped_detector_off() -> None:
    settings = GuardianSettings(
        enabled=True,
        overrides=(DetectorOverrideSettings(detector_id="guest-cpu-saturated", enabled=False),),
    )

    resolved = resolve(settings, shape=ClusterShape.TWO_NODE)
    declaration = next(
        entry for entry in resolved.declarations if entry.detector_id == "guest-cpu-saturated"
    )

    assert not declaration.enabled


def test_an_override_changes_only_what_it_names() -> None:
    settings = GuardianSettings(
        enabled=True,
        overrides=(
            DetectorOverrideSettings(detector_id="guest-locked-too-long", for_seconds=7_200),
        ),
    )

    resolved = resolve(settings, shape=ClusterShape.TWO_NODE)
    adjusted = resolved.detector_for("guest-locked-too-long")
    shipped = detector_by_id("guest-locked-too-long")

    assert adjusted is not None and shipped is not None
    assert adjusted.for_seconds == 7_200
    assert adjusted.severity is shipped.severity
    assert adjusted.fire_value == shipped.fire_value


# -- posture ---------------------------------------------------------------------


def test_the_default_posture_on_a_fresh_deployment_is_propose_only() -> None:
    """SC-004, read off what an empty policy resolves to rather than off a document."""
    assert is_propose_only(_policies(preset_document(PosturePreset.PROPOSE_ONLY)))
    assert is_propose_only(_policies({}))


def test_the_recommended_preset_acts_on_something_and_proposes_the_rest() -> None:
    """FR-018."""
    policies = _policies(preset_document(PosturePreset.RECOMMENDED))

    assert not is_propose_only(policies)
    assert any(not rule.level.acts for rule in policies.rules), (
        "the deployment-wide rule stays propose-only; only named capabilities act"
    )


def test_the_recommended_preset_never_lets_anything_destructive_run() -> None:
    """A homelab has no second copy of most of what is on it."""
    named = {capability for capability, _bound, _reason in RECOMMENDED_AUTONOMOUS_CAPABILITIES}

    assert not named & {
        "proxmox_reclaim_storage",
        "proxmox_remove_orphaned_volume",
        "proxmox_stop_guest",
        "proxmox_migrate_guest",
        "proxmox_ha_relocate",
    }


def test_every_capability_in_the_preset_says_why_it_is_there() -> None:
    """A preset an operator cannot audit is one they apply or refuse on trust."""
    for capability, _bound, reason in RECOMMENDED_AUTONOMOUS_CAPABILITIES:
        assert len(reason.split()) >= 10, capability


def test_a_bound_raised_above_the_default_says_so_in_its_own_reason() -> None:
    """The two capabilities the preset acts on above ``low`` are the two whose
    reasons have to carry the argument."""
    raised = [
        (capability, reason)
        for capability, bound, reason in RECOMMENDED_AUTONOMOUS_CAPABILITIES
        if bound == RISK_CLASS_MODERATE
    ]

    assert raised
    for capability, reason in raised:
        assert "bound" in reason or "asymmetry" in reason, capability


def test_both_presets_describe_themselves_in_something_an_operator_can_read() -> None:
    for preset in PosturePreset:
        assert len(preset.describe().split()) >= 20, preset


def test_a_proposal_with_no_history_says_so_rather_than_showing_an_empty_list() -> None:
    """T-046: a preview against nothing is not a preview, and pretending it is
    would be the most reassuring possible way to be wrong."""
    proposal = PostureProposal(
        preset=PosturePreset.RECOMMENDED,
        document=preset_document(PosturePreset.RECOMMENDED),
    )

    assert not proposal.has_history_to_judge_by
    assert "Nothing has been recorded yet" in proposal.summarise()


def test_a_shipped_severity_survives_being_rendered_as_a_record() -> None:
    detector = detector_by_id("cluster-quorum-lost")

    assert detector is not None
    assert detector.severity is Severity.CRITICAL
    assert detector.to_record()["severity"] == "critical"
