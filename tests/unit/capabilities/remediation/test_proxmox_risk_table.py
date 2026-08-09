"""The risk table is the safety-critical artefact, so it is asserted, not read.

A risk class scattered across thirteen capability modules is a classification
nobody has ever read as a whole. One table, one review, and the assertions below
— which fail when the table and the registry disagree, when a data-losing action
is classified below the top of the scale, or when a recovery point is graded by
how large it is rather than by what it protects.
"""

from __future__ import annotations

import pytest

from capabilities.tools.remediation.proxmox import risk
from platform.autonomy.risk import RiskClass

pytestmark = pytest.mark.unit


def test_the_table_covers_every_action_this_feature_ships() -> None:
    """A capability absent from the table is a capability nobody classified."""
    from capabilities.tools.remediation.proxmox import DECLARATIONS

    assert {row.capability for row in risk.RISK_TABLE} == set(DECLARATIONS)


def test_every_row_carries_the_four_questions_a_class_is_the_worst_answer_to() -> None:
    """Reversibility, data loss, availability and blast radius, in prose, per row."""
    for row in risk.RISK_TABLE:
        assert row.reversibility.strip(), row.capability
        assert row.data_loss.strip(), row.capability
        assert row.availability.strip(), row.capability
        assert row.blast_radius.strip(), row.capability


def test_an_action_that_can_lose_data_is_the_top_of_the_scale() -> None:
    """Size does not enter into it: a hundred-megabyte loss is still a loss."""
    losing = [row for row in risk.RISK_TABLE if row.loses_data]

    assert losing, "the shipped set contains no data-losing action, which cannot be right"
    assert all(row.risk_class is RiskClass.CRITICAL for row in losing)


def test_a_row_that_loses_data_below_the_top_of_the_scale_cannot_be_written() -> None:
    """The rule is enforced where the table is written, not where it is read."""
    with pytest.raises(ValueError, match="loses data"):
        risk.RiskRow(
            capability="proxmox_invented_action",
            risk_class=RiskClass.MODERATE,
            reversibility="not at all",
            data_loss="the only copy of the volume",
            availability="none",
            blast_radius="one volume",
            loses_data=True,
        )


def test_the_lock_clear_and_the_guest_start_are_inside_the_default_risk_bound() -> None:
    """The two actions the primary story turns on. Above the bound they never run."""
    from config.constants.autonomy import DEFAULT_RISK_BOUND

    bound = RiskClass(DEFAULT_RISK_BOUND)

    assert risk.class_of("proxmox_unlock_guest").at_or_below(bound)
    assert risk.class_of("proxmox_start_guest").at_or_below(bound)


def test_the_hard_stop_is_classified_apart_from_the_graceful_shutdown() -> None:
    """Pulling the power on a running database is not an ACPI shutdown."""
    assert risk.class_of("proxmox_stop_guest").rank > risk.class_of("proxmox_shutdown_guest").rank


def test_relocating_a_managed_resource_outranks_migrating_a_guest_by_hand() -> None:
    """They are separate decisions: the manager acts on its own schedule, on its own set."""
    assert risk.class_of("proxmox_ha_relocate").rank > risk.class_of("proxmox_migrate_guest").rank
    assert risk.class_of("proxmox_ha_relocate") is RiskClass.HIGH


def test_the_replication_resync_states_the_link_impact_it_expects() -> None:
    """Corosync runs over the link a resync saturates, and the row has to say so."""
    row = risk.row_for("proxmox_resync_replication")

    assert "link" in row.availability
    assert "corosync" in row.availability


def test_a_recovery_point_is_the_top_of_the_scale_however_small_it_is() -> None:
    """What an item protects decides its class; what it costs does not."""
    tiny = risk.ReclaimableItem(
        volume_id="TeraChad:backup/vzdump-lxc-100-2025_08_09-07_00_02.tar.zst",
        content="backup",
        size_bytes=1,
    )
    huge = risk.ReclaimableItem(
        volume_id="local-lvm:vm-129-disk-0",
        content="images",
        size_bytes=8_000_000_000_000,
    )

    assert risk.item_class(tiny) is RiskClass.CRITICAL
    assert risk.item_class(huge).rank < RiskClass.CRITICAL.rank


@pytest.mark.parametrize("content", ["backup", "snapshot", "replication-base"])
def test_every_kind_of_recovery_point_is_recognised(content: str) -> None:
    """A snapshot, a backup and the last replication base are one category."""
    item = risk.ReclaimableItem(volume_id=f"store:{content}/thing", content=content, size_bytes=10)

    assert item.is_recovery_point
    assert risk.item_class(item) is RiskClass.CRITICAL


def test_the_whole_table_prints_as_one_block_a_review_can_read() -> None:
    """One table, one review. A table nobody can print is a table nobody reads."""
    printed = risk.describe_table()

    for row in risk.RISK_TABLE:
        assert row.capability in printed
        assert f"[{row.risk_class.value}]" in printed
        assert row.reversibility in printed
        assert row.data_loss in printed


def test_asking_for_an_unclassified_capability_raises_rather_than_guessing() -> None:
    """A guess here would be a class nobody reviewed, presented as one somebody did."""
    with pytest.raises(KeyError, match="proxmox_not_a_capability"):
        risk.class_of("proxmox_not_a_capability")


def test_the_prohibitions_name_what_no_capability_may_ever_reach() -> None:
    """The deliberate hole. It is a declaration so a test can assert over it."""
    named = {prohibition.name for prohibition in risk.PROHIBITED_OPERATIONS}

    assert {"fencing", "quorum", "corosync", "node_services", "node_network"} <= named
    for prohibition in risk.PROHIBITED_OPERATIONS:
        assert prohibition.why.strip(), prohibition.name
        assert prohibition.paths, prohibition.name


@pytest.mark.parametrize(
    "path",
    [
        "/nodes/pve01/qemu/9000/status/stop",
        "/cluster/config/qdevice",
        "/nodes/pve01/network",
        "/nodes/pve01/services/pveproxy/restart",
    ],
)
def test_a_prohibited_path_is_recognised_wherever_it_appears(path: str) -> None:
    """Recognition is by path, because a path is what a write actually reaches."""
    forbidden = risk.prohibition_for(path)

    if path.startswith("/nodes/pve01/qemu"):
        assert forbidden is None
    else:
        assert forbidden is not None
        assert forbidden.why.strip()
