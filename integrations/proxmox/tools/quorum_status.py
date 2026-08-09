"""Whether the cluster may still decide, under what configuration, and so what.

Four readings and one answer. ``/cluster/status`` gives the vote arithmetic and
the membership; ``/cluster/config/totem`` and ``/cluster/config/nodes`` give the
settings that decide whether the arithmetic survives a node loss. A tool per
endpoint would leave the synthesis to the model, which is exactly where a small
local model does it worst and where the answer is least reproducible.

Three things here are answers rather than dumps.

**The margin, and how many losses it buys.** Total votes minus the quorum
required. On a two-node cluster with no quorum device it is zero — which is true
of a healthy, quorate, entirely green cluster, and means the next node failure is
a cluster-wide outage rather than a single-node one.

**The device's contribution, not its presence.** A ``corosync-qdevice`` whose
daemon has failed still appears in the membership view carrying no votes.
Everything that counts configured devices reads that as protection.

**The consequences, stated.** "Not quorate" is a fact an operator still has to
interpret. The three inferences that always follow it — ``/etc/pve`` goes
read-only, nothing can be started or migrated, running guests carry on — are
returned with it, so they are right every time instead of rediscovered.

A single-node installation is answered as *inapplicable*. It has not lost
quorum; it never had one, and reporting it unquorate would be a critical finding
about an installation working exactly as intended.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.investigation import Undetermined, report
from integrations.proxmox.models import ClusterConfiguration, ClusterStatus
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_quorum_status"

#: What stops working the moment a Proxmox cluster loses quorum, and what does
#: not. Written down rather than inferred, because the third line is the one
#: operators get wrong under pressure and shut guests down that were fine.
LOST_QUORUM_CONSEQUENCES: tuple[str, ...] = (
    "the cluster filesystem /etc/pve is read-only on every surviving node",
    "no guest can be started, stopped, migrated or reconfigured anywhere in the cluster",
    "running guests keep running and keep serving; losing quorum did not stop them",
)

_USE_CASES = (
    "establishing whether a cluster can act at all before investigating why a guest will not start",
    "finding out how many node losses a cluster survives, including when it is entirely green",
    "checking whether a configured quorum device is actually contributing a vote",
)

_ANTI_EXAMPLES = (
    "why one guest is unhealthy, which is a guest question this does not answer",
    "corosync link quality, which proxmox_corosync_links reads",
    "forcing quorum or changing expected votes — nothing here writes",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox quorum status",
    description=(
        "Return whether a Proxmox cluster is quorate, by what margin, under which corosync "
        "settings, and what follows from the answer. Reports how many node losses the cluster "
        "survives — zero on a two-node cluster with no quorum device, while everything is "
        "green — and, when quorum is lost, that /etc/pve is read-only and nothing can be "
        "started or migrated while running guests carry on."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "cluster", "quorum", "corosync", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_quorum_status() -> CapabilityResult:
    """Return the vote arithmetic, the configuration behind it, and the consequence."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    holes: list[Undetermined | None] = []
    try:
        status = await client.cluster_status()
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    configuration = ClusterConfiguration()
    if status.is_clustered:
        try:
            configuration = await client.cluster_configuration()
        except IntegrationError as error:
            holes.append(
                Undetermined(
                    question="which corosync settings decide whether this cluster survives a "
                    "node loss",
                    reason=str(error),
                    published_by="corosync.conf, through /cluster/config/totem",
                )
            )

    value = _value(status, configuration)
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(status, value),
        reference=f"proxmox:quorum:{status.name or 'standalone'}",
        undetermined=holes,
    )


def _value(status: ClusterStatus, configuration: ClusterConfiguration) -> dict[str, Any]:
    """Return the arithmetic, the settings, and what both of them mean."""
    margin = status.quorum_margin
    return {
        "cluster": status.name,
        "clustered": status.is_clustered,
        "applicable": status.is_clustered,
        "quorate": status.quorate,
        "expected_votes": status.expected_votes,
        "total_votes": status.total_votes,
        "quorum_required": status.quorum_required,
        "quorum_margin": margin,
        "node_losses_survived": max(margin, 0) if status.quorate else 0,
        "online_nodes": list(status.online_nodes),
        "offline_nodes": list(status.offline_nodes),
        "quorum_device": _device(status),
        "two_node": configuration.two_node,
        "wait_for_all": configuration.wait_for_all,
        "last_man_standing": configuration.last_man_standing,
        "consequences": list(_consequences(status)),
    }


def _device(status: ClusterStatus) -> dict[str, Any]:
    """Return what the quorum device is doing, which is not whether it is there."""
    configured = bool(status.quorum_device)
    contributing = configured and not status.has_non_contributing_quorum_device
    if not configured:
        verdict = "no quorum device is configured, so every vote comes from a node"
    elif contributing:
        verdict = "a quorum device is configured and contributing a vote"
    else:
        verdict = (
            "a quorum device is configured but NOT contributing: it appears in the membership "
            "view and carries no vote, which every count of configured devices reads as "
            "protection that is not there"
        )
    return {
        "configured": configured,
        "contributing": contributing,
        "reported_as": status.quorum_device,
        "verdict": verdict,
    }


def _consequences(status: ClusterStatus) -> tuple[str, ...]:
    """Return what the current state means for what can be done."""
    if not status.is_clustered:
        return (
            "this is a standalone installation with no cluster, so quorum does not apply to it "
            "and nothing here is a fault",
        )
    if not status.quorate:
        return LOST_QUORUM_CONSEQUENCES
    if status.quorum_margin <= 0:
        return (
            "the cluster is quorate with no margin: losing any single node makes /etc/pve "
            "read-only on the survivor and stops every start, stop and migration",
        )
    return (
        f"the cluster is quorate and survives {status.quorum_margin} further node loss(es) "
        f"before /etc/pve goes read-only",
    )


def _summary(status: ClusterStatus, value: dict[str, Any]) -> str:
    """Return the one line a conclusion can be checked against."""
    if not status.is_clustered:
        return (
            f"{status.name or 'this installation'} is a single node with no cluster, so quorum "
            f"is not applicable to it"
        )
    if not status.quorate:
        return (
            f"{status.name} has NO quorum: {status.total_votes} of the {status.quorum_required} "
            f"votes required, so /etc/pve is read-only and nothing can be started or migrated"
        )
    return (
        f"{status.name} is quorate with a margin of {value['quorum_margin']} and survives "
        f"{value['node_losses_survived']} further node loss(es)"
    )


__all__ = ["LOST_QUORUM_CONSEQUENCES", "TOOL_NAME", "proxmox_quorum_status"]
