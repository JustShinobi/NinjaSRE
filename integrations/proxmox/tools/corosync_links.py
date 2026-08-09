"""Corosync's links, and the difference between one that flaps and one that is gone.

Both produce the same line. ``link: host: 2 link: 0 is down`` appears once for a
link whose address no longer exists and four times in two minutes for a cable
that is failing, and the remedies have nothing in common: the first is a
configuration change, the second is a physical fault that is still happening and
will take the cluster's membership with it while nobody is watching.

So the reading is the *transition count*, not the last state. A link that went
down and came back is healthy right now and is the most urgent thing on the
cluster.

Two further readings this makes and a link-state check does not:

**A ring only one node declares.** Corosync builds links pairwise. A
``ring1_addr`` on one node and not on the other is a link that can never come
up, and no error is ever logged for it — it simply never forms.

**Retransmits.** The knet layer re-sends what did not arrive and says so in the
log. Retransmits without a link going down are a link that is degrading rather
than failing, which is the state before the state everybody notices.

What is deliberately absent is per-link latency. Proxmox does not publish it —
it lives in ``corosync-cfgtool``'s output, and this integration is forbidden a
shell — so it is reported as undetermined with the publisher named. An invented
number would be worse than none, because a latency figure is exactly the kind of
reading a conclusion gets built on.

Source of truth: ``/cluster/config/nodes`` for the declared rings, and
``/cluster/log`` for what corosync said about them.
"""

from __future__ import annotations

import re
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.investigation import (
    LINK_FLAP_TRANSITIONS,
    MAX_REPORTED_ITEMS,
    Undetermined,
    report,
)
from integrations.proxmox.models import ClusterConfiguration
from integrations.proxmox.schema import INTEGRATION

TOOL_NAME = "proxmox_corosync_links"

#: How many log entries are read. Corosync is quiet until it is not, and the
#: entries that explain a membership change are the recent ones.
LOG_ENTRIES = 200

#: What corosync writes when a link changes state. The host number is the
#: corosync node id rather than the node's name, which is why the link index
#: rather than the host is what this groups by.
_LINK_EVENT = re.compile(r"link:\s*(?:host:\s*(\d+)\s+)?link:\s*(\d+)\s+is\s+(up|down)")

#: What the knet layer writes when it re-sends. Not a link failure; a link that
#: is losing packets, which is the state before the one that gets noticed.
_RETRANSMIT = re.compile(r"retransmit list", re.IGNORECASE)

_USE_CASES = (
    "telling a corosync link that is flapping from one that is simply gone",
    "finding a corosync ring that only one node declares and therefore can never come up",
    "counting knet retransmits on a cluster whose membership keeps changing",
)

_ANTI_EXAMPLES = (
    "whether the cluster currently has quorum, which proxmox_quorum_status answers",
    "a node's own interface configuration, which is a host-layer reading",
    "restarting corosync or editing its configuration — nothing here writes",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox corosync links",
    description=(
        "Return each corosync link's recent behaviour: how many times it changed state, "
        "whether it is flapping or was simply lost, which nodes declare it, and how many knet "
        "retransmits the cluster logged. A link that went down and came back is healthy now "
        "and is the most urgent thing on the cluster; a link that went down once and stayed "
        "down is usually an address that no longer exists."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.EVENT,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "corosync", "cluster", "network", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_corosync_links() -> CapabilityResult:
    """Return per-link state, transitions and retransmits, with flapping named."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ProxmoxClient, capability=TOOL_NAME)
    try:
        configuration = await client.cluster_configuration()
        entries = await client.cluster_log(limit=LOG_ENTRIES)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    events, retransmits = _read_log(entries)
    links = _links(configuration, events)
    value: dict[str, Any] = {
        "cluster": configuration.cluster_name,
        "transport": configuration.transport,
        "links": links,
        "retransmits": retransmits,
        "log_entries_read": min(len(entries), LOG_ENTRIES),
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=_summary(links, retransmits),
        reference=f"proxmox:corosync:{configuration.cluster_name or 'cluster'}",
        evidence_type=EvidenceType.EVENT,
        undetermined=[
            Undetermined(
                question="per-link knet latency and the retransmit counters corosync keeps",
                reason=(
                    "the Proxmox API does not publish them — they exist only in "
                    "corosync-cfgtool's output on each node, and this integration is "
                    "deliberately forbidden a shell"
                ),
                published_by="corosync-cfgtool -n, on each node",
            )
        ],
    )


def _read_log(entries: tuple[Any, ...]) -> tuple[dict[int, list[dict[str, Any]]], int]:
    """Return each link's state changes, newest last, and the retransmit count."""
    events: dict[int, list[dict[str, Any]]] = {}
    retransmits = 0
    for entry in entries:
        message = str(entry.get("msg", ""))
        if _RETRANSMIT.search(message):
            retransmits += 1
            continue
        found = _LINK_EVENT.search(message)
        if found is None:
            continue
        index = int(found.group(2))
        events.setdefault(index, []).append(
            {
                "at": int(entry.get("time", 0) or 0),
                "state": found.group(3),
                "node": str(entry.get("node", "")),
                "peer": found.group(1) or "",
            }
        )
    for changes in events.values():
        changes.sort(key=lambda change: change["at"])
    return events, retransmits


def _links(
    configuration: ClusterConfiguration, events: dict[int, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Return one record per link, declared or merely observed."""
    declared = dict(configuration.links)
    members = {name for names in declared.values() for name in names}
    indexes = sorted(set(declared) | set(events))

    links: list[dict[str, Any]] = []
    for index in indexes:
        changes = events.get(index, [])
        by = sorted(declared.get(index, ()))
        everywhere = bool(by) and set(by) == members
        state = _state(changes)
        links.append(
            {
                "link": index,
                "declared_by": by,
                "declared_by_every_node": everywhere,
                "state": state,
                "transitions": len(changes),
                "last_event_at": changes[-1]["at"] if changes else 0,
                "recent_events": changes[-MAX_REPORTED_ITEMS:],
                "verdict": _verdict(index, state, declared_by=by, everywhere=everywhere),
            }
        )
    return links


def _state(changes: list[dict[str, Any]]) -> str:
    """Return what this link is doing, which the last event alone does not say."""
    if not changes:
        return "no state change logged"
    downs = [change for change in changes if change["state"] == "down"]
    ups = [change for change in changes if change["state"] == "up"]
    if len(downs) >= LINK_FLAP_TRANSITIONS and ups:
        return "flapping"
    if changes[-1]["state"] == "down":
        return "lost"
    return "up"


def _verdict(index: int, state: str, *, declared_by: list[str], everywhere: bool) -> str:
    """Return what to do about this link, which is not the same as its state."""
    if declared_by and not everywhere:
        return (
            f"link {index} is declared only by {', '.join(declared_by)}. Corosync builds links "
            f"pairwise, so this one can never come up and nothing will ever log an error for it"
        )
    if state == "flapping":
        return (
            f"link {index} went down and came back repeatedly. It is up now, which is why "
            f"nothing is alerting, and a physical fault is still in progress"
        )
    if state == "lost":
        return (
            f"link {index} went down and has not returned; check whether its address still exists"
        )
    return f"link {index} has not changed state in the log window"


def _summary(links: list[dict[str, Any]], retransmits: int) -> str:
    """Return the one line a conclusion can be checked against."""
    parts: list[str] = []
    for link in links:
        if link["declared_by"] and not link["declared_by_every_node"]:
            parts.append(f"link {link['link']} is declared by only one node and cannot form")
        if link["state"] in {"flapping", "lost"}:
            parts.append(
                f"link {link['link']} is {link['state']} ({link['transitions']} change(s))"
            )
    if retransmits:
        parts.append(f"{retransmits} knet retransmit entries logged")
    if not parts:
        return f"{len(links)} corosync link(s), none of which changed state or retransmitted"
    return "; ".join(parts)


__all__ = ["LOG_ENTRIES", "TOOL_NAME", "proxmox_corosync_links"]
