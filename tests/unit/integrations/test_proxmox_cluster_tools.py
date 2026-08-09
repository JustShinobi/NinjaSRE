"""Phase 1: whether the cluster can decide, and what follows from it if it cannot.

Every question below this one is downstream. A cluster without quorum cannot
start, stop, migrate or reconfigure anything on any node, so "the guest will not
start" has already been answered before anybody opens the guest — and an
investigation that reads the guest first spends its time describing a symptom.

The readings these tools exist to make, each one a case where the obvious
alternative is wrong:

- **The margin, not the state.** A two-node cluster with no quorum device is
  quorate, green, and one node loss away from a cluster-wide outage. That is a
  standing fact about a healthy cluster and no health word contains it.
- **The device's contribution, not its presence.** A dead ``corosync-qdevice``
  still appears in the membership view carrying zero votes. Anything counting
  configured devices reads that as protection that is not there.
- **Flapping, not down.** The same "link is down" line means a cable when it
  repeats and an address when it does not, and the remedies have nothing in
  common.
- **Skew against corosync's tolerance, not against a human's.** Two clocks a
  minute apart look identical to an operator and are far outside what the token
  protocol survives.
"""

from __future__ import annotations

import pytest

from integrations.proxmox.investigation import CLOCK_SKEW_TOLERANCE_SECONDS
from integrations.proxmox.tools.clock_skew import proxmox_clock_skew
from integrations.proxmox.tools.corosync_links import proxmox_corosync_links
from integrations.proxmox.tools.ha_state import proxmox_ha_state
from integrations.proxmox.tools.quorum_status import proxmox_quorum_status
from tests.support.proxmox import (
    PRIMARY,
    SECONDARY,
    ClusterState,
    investigating,
)

pytestmark = pytest.mark.unit


# --- Quorum -------------------------------------------------------------------


async def test_a_two_node_cluster_with_one_node_down_reports_the_whole_arithmetic() -> None:
    """Votes, membership, the quorum device, the settings, and the consequence."""
    with investigating(ClusterState.NODE_DOWN):
        result = await proxmox_quorum_status()

    value = result.value
    assert value["expected_votes"] == 2
    assert value["total_votes"] == 1
    assert value["quorum_required"] == 2
    assert value["online_nodes"] == [PRIMARY]
    assert value["offline_nodes"] == [SECONDARY]
    assert value["quorum_device"]["configured"]
    assert not value["quorum_device"]["contributing"]
    assert value["two_node"] is False
    assert value["wait_for_all"] is False
    assert value["last_man_standing"] is False


async def test_losing_quorum_is_reported_with_the_three_things_that_follow_from_it() -> None:
    """Read-only cluster filesystem, nothing starts or migrates, running guests continue."""
    with investigating(ClusterState.NO_QUORUM):
        result = await proxmox_quorum_status()

    consequence = " ".join(result.value["consequences"]).lower()
    assert "/etc/pve" in consequence
    assert "read-only" in consequence
    assert "migrat" in consequence
    assert "running guests" in consequence


async def test_a_healthy_cluster_reports_its_margin_rather_than_a_bare_quorate() -> None:
    """A margin of zero on a green cluster is the most important standing fact about it."""
    with investigating():
        result = await proxmox_quorum_status()

    value = result.value
    assert value["quorate"]
    assert value["quorum_margin"] == 0
    assert value["node_losses_survived"] == 0
    assert "0" in result.evidence[0].summary


async def test_a_cluster_with_room_to_spare_says_how_many_losses_it_survives() -> None:
    with investigating(
        responses={
            "/cluster/status": [
                {"type": "cluster", "id": "cluster", "name": "HAL9000", "nodes": 3, "quorate": 1},
                {"type": "node", "id": "node/pve01", "name": "pve01", "online": 1, "nodeid": 1},
                {"type": "node", "id": "node/pve02", "name": "pve02", "online": 1, "nodeid": 2},
                {"type": "node", "id": "node/pve03", "name": "pve03", "online": 1, "nodeid": 3},
                {
                    "type": "quorum",
                    "id": "quorum",
                    "quorate": 1,
                    "expected_votes": 5,
                    "total_votes": 5,
                    "quorum": 3,
                },
            ]
        }
    ):
        result = await proxmox_quorum_status()

    assert result.value["quorum_margin"] == 2
    assert result.value["node_losses_survived"] == 2


async def test_a_single_node_installation_reports_quorum_as_inapplicable() -> None:
    """It has not lost quorum; it never had one, and saying otherwise is a false critical."""
    with investigating(ClusterState.SINGLE_NODE):
        result = await proxmox_quorum_status()

    assert result.value["applicable"] is False
    assert not result.value["clustered"]
    assert "not" in result.evidence[0].summary.lower()


async def test_a_quorum_device_that_contributes_nothing_is_not_reported_as_protection() -> None:
    """The reference cluster's exact state, and what a device count would miss."""
    with investigating():
        result = await proxmox_quorum_status()

    device = result.value["quorum_device"]
    assert device["configured"]
    assert not device["contributing"]
    assert "not contributing" in device["verdict"].lower()


# --- Corosync links -----------------------------------------------------------


async def test_a_link_that_goes_down_and_up_repeatedly_is_reported_as_flapping() -> None:
    with investigating():
        result = await proxmox_corosync_links()

    links = {link["link"]: link for link in result.value["links"]}
    assert links[0]["state"] == "flapping"
    assert links[0]["transitions"] >= 2


async def test_a_link_that_went_down_and_stayed_down_is_reported_as_lost() -> None:
    """The same log line as a flap, and a completely different fault."""
    with investigating():
        result = await proxmox_corosync_links()

    links = {link["link"]: link for link in result.value["links"]}
    assert links[1]["state"] == "lost"
    assert links[1]["transitions"] == 1


async def test_retransmits_are_counted_and_latency_is_reported_as_undetermined() -> None:
    """Knet latency is not in the API, and an invented number would be worse than none."""
    with investigating():
        result = await proxmox_corosync_links()

    assert result.value["retransmits"] == 2
    questions = " ".join(entry["question"] for entry in result.value["undetermined"])
    assert "latency" in questions.lower()


async def test_a_link_only_one_node_declares_is_reported_as_never_able_to_come_up() -> None:
    """Corosync builds links pairwise; a ring one node has is a ring that cannot form."""
    with investigating():
        result = await proxmox_corosync_links()

    links = {link["link"]: link for link in result.value["links"]}
    assert links[1]["declared_by"] == [PRIMARY]
    assert not links[1]["declared_by_every_node"]


# --- High availability --------------------------------------------------------


async def test_managed_resources_carry_both_the_requested_and_the_current_state() -> None:
    with investigating():
        result = await proxmox_ha_state()

    resources = {entry["sid"]: entry for entry in result.value["resources"]}
    assert resources["ct:115"]["requested_state"] == "started"
    assert resources["ct:115"]["current_state"] == "started"
    assert result.value["manager"]["node"] == PRIMARY


async def test_fencing_that_has_already_happened_is_reported_as_occurred() -> None:
    with investigating(
        responses={
            "/cluster/ha/status/current": [
                {"id": "master", "type": "master", "node": PRIMARY, "status": "master"},
                {
                    "id": "service:ct:115",
                    "type": "service",
                    "sid": "ct:115",
                    "node": SECONDARY,
                    "state": "started",
                    "request_state": "started",
                    "crm_state": "fence",
                },
            ]
        }
    ):
        result = await proxmox_ha_state()

    assert result.value["fencing"]["occurred"]
    assert "ct:115" in result.value["fencing"]["resources"]


async def test_a_cluster_without_quorum_and_with_managed_resources_says_fencing_is_imminent() -> (
    None
):
    """The manager cannot act without quorum, and the watchdog does not wait for it."""
    with investigating(ClusterState.NO_QUORUM):
        result = await proxmox_ha_state()

    assert result.value["fencing"]["imminent"]


async def test_a_cluster_with_no_high_availability_says_so_rather_than_reporting_nothing() -> None:
    with investigating(ClusterState.SINGLE_NODE):
        result = await proxmox_ha_state()

    assert result.value["resources"] == []
    assert "no" in result.evidence[0].summary.lower()


# --- Clock skew ---------------------------------------------------------------


async def test_clock_skew_is_measured_against_corosyncs_tolerance_and_not_a_humans() -> None:
    with investigating(ClusterState.DEGRADED):
        result = await proxmox_clock_skew()

    assert result.value["tolerance_seconds"] == CLOCK_SKEW_TOLERANCE_SECONDS
    assert result.value["max_skew_seconds"] >= 46
    assert not result.value["within_tolerance"]


async def test_a_cluster_whose_clocks_agree_reports_within_tolerance() -> None:
    with investigating():
        result = await proxmox_clock_skew()

    assert result.value["within_tolerance"]
    assert result.value["max_skew_seconds"] <= CLOCK_SKEW_TOLERANCE_SECONDS


async def test_a_node_whose_clock_cannot_be_read_is_named_rather_than_skipped() -> None:
    """A node left out of a skew calculation is a node the calculation is wrong about."""
    with investigating(ClusterState.NODE_DOWN):
        result = await proxmox_clock_skew()

    questions = " ".join(entry["question"] for entry in result.value["undetermined"])
    assert SECONDARY in questions
