"""Whether the cluster can still make decisions, which precedes every other question.

A Proxmox cluster without quorum keeps its running guests running and can do
nothing else: the cluster filesystem goes read-only, ``/etc/pve`` becomes
unwritable, and no guest can be started, stopped, migrated or reconfigured on any
surviving node. Every "why will this guest not start" question has already been
answered at that point, and an investigation that reads the guest first spends
its time describing a symptom.

The number this returns that nothing else does is the **quorum margin**: how many
votes could be lost before quorum is. On a two-node cluster with no quorum device
it is zero, which means either node's loss is a cluster-wide outage — and that is
true of a healthy, quorate, entirely green cluster, which is why it has to be
reported rather than derived from a health state.

It also reports a quorum device that is **configured and contributing nothing**.
A dead ``corosync-qdevice`` still appears in the membership view, so anything
counting configured devices reads it as protection that is not there.

Source of truth: ``/cluster/status``, one call.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.models import ClusterStatus
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_cluster_health"

_USE_CASES = (
    "establishing whether the cluster can start, stop or migrate anything at all",
    "finding out how many node failures the cluster survives before it stops deciding",
    "checking whether a quorum device that is configured is actually contributing a vote",
)

_ANTI_EXAMPLES = (
    "why one guest is unhealthy, which is a guest question and this does not answer",
    "how full a datastore is, which proxmox_storage_pressure reads",
    "changing anything about the cluster — nothing here writes",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox cluster health",
    description=(
        "Return a Proxmox cluster's quorum state, its vote arithmetic, and which nodes are "
        "answering. Reports the quorum margin — how many votes can be lost before the "
        "cluster stops being able to decide anything — which on a two-node cluster is "
        "usually zero even when everything is green."
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
async def proxmox_cluster_health() -> CapabilityResult:
    """Return the cluster's quorum state, votes and membership."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        status = await client.cluster_status()
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    return CapabilityResult.ok(
        TOOL_NAME,
        value=_value(status),
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.METRIC,
                summary=_summary(status),
                reference=f"proxmox:cluster:{status.name or 'standalone'}",
            ),
        ),
    )


def _value(status: ClusterStatus) -> dict[str, Any]:
    """Return the fields that carry the mechanism rather than the whole answer."""
    return {
        "cluster": status.name,
        "clustered": status.is_clustered,
        "quorate": status.quorate,
        "expected_votes": status.expected_votes,
        "total_votes": status.total_votes,
        "quorum_required": status.quorum_required,
        "quorum_margin": status.quorum_margin,
        "quorum_device": status.quorum_device,
        "quorum_device_contributing": not status.has_non_contributing_quorum_device,
        "online_nodes": list(status.online_nodes),
        "offline_nodes": list(status.offline_nodes),
    }


def _summary(status: ClusterStatus) -> str:
    """Return the one line a conclusion can be checked against."""
    if not status.is_clustered:
        return (
            f"{status.name or 'this installation'} is a single node with no cluster, so "
            f"quorum does not apply to it"
        )
    if not status.quorate:
        return (
            f"{status.name} has NO quorum: {status.total_votes} of the "
            f"{status.quorum_required} votes required. /etc/pve is read-only and nothing "
            f"can be started, stopped or migrated."
        )
    margin = status.quorum_margin
    if margin <= 0:
        return (
            f"{status.name} is quorate with a margin of {margin}: losing any single node "
            f"makes /etc/pve read-only on the survivor"
        )
    return f"{status.name} is quorate and survives {margin} more node loss(es)"


__all__ = ["TOOL_NAME", "proxmox_cluster_health"]
