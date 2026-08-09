"""How far apart the nodes' clocks are, measured against what corosync tolerates.

Corosync's token protocol assumes the members agree about time to within about a
second. Two nodes a minute apart look identical to an operator glancing at two
web interfaces, and produce a cluster whose membership will not settle — which
presents as random link failures, guests that will not migrate, and a cluster log
full of retransmits, none of which mention a clock.

So the number this returns is the skew *against the tolerance*, not against a
human's sense of "close enough". The tolerance is named rather than inlined
because it is a judgement about a protocol rather than a fact about a cluster.

A node whose clock could not be read is named rather than skipped. A skew
calculated across the nodes that answered is a skew that is quietly wrong about
the one that did not, and the node that did not answer is usually the interesting
one.

Source of truth: the cluster membership, and ``/nodes/<node>/time`` for each.
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
from integrations.proxmox.investigation import (
    CLOCK_SKEW_TOLERANCE_SECONDS,
    Undetermined,
    report,
)
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_clock_skew"

_USE_CASES = (
    "checking clock agreement across a cluster whose corosync membership keeps changing",
    "ruling time out before investigating link failures that have no physical cause",
    "finding a node whose NTP has stopped without anything reporting a failure",
)

_ANTI_EXAMPLES = (
    "setting a clock or restarting a time daemon — nothing here writes",
    "corosync link behaviour, which proxmox_corosync_links reads",
    "whether the cluster is quorate, which proxmox_quorum_status answers",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox clock skew",
    description=(
        "Return each Proxmox node's clock and how far apart they are, measured against what "
        "corosync tolerates rather than against what looks close to a person. Two nodes a "
        "minute apart present as random link failures and unmigratable guests, and nothing in "
        "those symptoms mentions time."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "cluster", "corosync", "time", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_clock_skew() -> CapabilityResult:
    """Return per-node clocks, the widest gap between them, and the tolerance."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    clocks: dict[str, dict[str, Any]] = {}
    holes: list[Undetermined | None] = []
    try:
        status = await client.cluster_status()
        for member in status.members:
            reading = await client.node_time(member.name)
            when = int(reading.get("time", 0) or 0)
            if not when:
                holes.append(
                    Undetermined(
                        question=f"what time the {member.name} node thinks it is",
                        reason=(
                            f"{member.name} did not answer its own time endpoint, so it is not "
                            f"in this comparison and the skew below is only about the rest"
                        ),
                        published_by=f"the {member.name} node itself",
                    )
                )
                continue
            clocks[member.name] = {
                "node": member.name,
                "clock": when,
                "timezone": str(reading.get("timezone", "")),
            }
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    value = _value(clocks)
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(status.name, value),
        reference=f"proxmox:clock:{status.name or 'standalone'}",
        undetermined=holes,
    )


def _value(clocks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return each node's clock, its offset from the earliest, and the widest gap."""
    times = [entry["clock"] for entry in clocks.values()]
    earliest = min(times) if times else 0
    skew = float(max(times) - earliest) if times else 0.0
    nodes = [
        {**entry, "skew_seconds": float(entry["clock"] - earliest)}
        for entry in sorted(clocks.values(), key=lambda entry: entry["node"])
    ]
    return {
        "nodes": nodes,
        "nodes_compared": len(nodes),
        "max_skew_seconds": skew,
        "tolerance_seconds": CLOCK_SKEW_TOLERANCE_SECONDS,
        "within_tolerance": skew <= CLOCK_SKEW_TOLERANCE_SECONDS,
    }


def _summary(cluster: str, value: dict[str, Any]) -> str:
    """Return the one line a conclusion can be checked against."""
    name = cluster or "this installation"
    if value["nodes_compared"] < 2:
        return f"{name}: fewer than two clocks could be read, so there is no skew to report"
    if value["within_tolerance"]:
        return (
            f"{name}: the widest clock gap is {value['max_skew_seconds']:.1f}s, inside the "
            f"{CLOCK_SKEW_TOLERANCE_SECONDS}s corosync tolerates"
        )
    worst = max(value["nodes"], key=lambda entry: entry["skew_seconds"])
    return (
        f"{name}: clocks differ by {value['max_skew_seconds']:.1f}s, far outside the "
        f"{CLOCK_SKEW_TOLERANCE_SECONDS}s corosync tolerates — {worst['node']} is the "
        f"furthest ahead, and unstable membership is the symptom this produces"
    )


__all__ = ["TOOL_NAME", "proxmox_clock_skew"]
