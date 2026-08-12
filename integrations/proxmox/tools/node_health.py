"""What a node publishes about itself that the Proxmox API cannot answer.

``integrations/proxmox/supplementary.py`` carries the shape — failed
``systemd`` units, bridge state, thin-pool metadata — and this is the caller
that fills it for one named node, on demand. It never reaches the
observability bridge itself: a structural rule keeps the whole hypervisor
integration working with no bridge configured at all, so a tool asks
``integrations.proxmox.bridge_readings`` — a plain callable a composition root
binds — rather than importing anything under ``platform.observation.bridge``.

A node's own state at the moment somebody is looking is what an investigation
asks for; a detector watching a trend is a different question with a
different answer, which is why this reads current values rather than history.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult
from integrations._base.capability import unconfigured
from integrations.proxmox import bridge_readings
from integrations.proxmox.investigation import report
from integrations.proxmox.schema import INTEGRATION
from integrations.proxmox.supplementary import supplementary_readings

TOOL_NAME = "proxmox_node_health"

#: Named as the "integration" ``unconfigured`` reports — not Proxmox itself,
#: which may be perfectly configured, but the separate metrics system this
#: tool reads instead of the Proxmox API.
_METRICS_BRIDGE = "the observability bridge's metrics source"

_USE_CASES = (
    "checking whether a node's failed systemd units explain a guest that will not start",
    "checking whether a configured bridge is down before blaming the guests on top of it",
    "checking an LVM thin pool's metadata usage, which stops writes while data usage still "
    "looks comfortable",
)

_ANTI_EXAMPLES = (
    "a guest's own CPU or memory pressure, which proxmox_guest_pressure reads",
    "a physical disk's SMART attributes, which proxmox_disk_health reads",
    "trend or history over these three readings — this asks for the node's state now",
)


@tool(
    name=TOOL_NAME,
    display_name="Proxmox node health",
    description=(
        "Return a node's failed systemd units, whether its configured bridges are up, and "
        "its LVM thin-pool metadata usage — the three readings that explained the reference "
        "cluster's only total outage and that no Proxmox REST endpoint answers. Reported as "
        "unavailable, by name, for whichever of the three nothing is publishing, rather than "
        "as an absence that could be mistaken for health."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("proxmox", "node", "systemd", "bridge", "thin-pool", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def proxmox_node_health(node: str) -> CapabilityResult:
    """Return what ``node`` publishes about itself beyond what the Proxmox API answers."""
    reader = bridge_readings.current()
    if reader is None:
        return unconfigured(TOOL_NAME, _METRICS_BRIDGE)

    try:
        published = await reader(node)
    except bridge_readings.NodeReadingsUnavailable as error:
        return CapabilityResult.failed(
            TOOL_NAME, CapabilityErrorClass.UPSTREAM_ERROR, str(error), detail=str(error)
        )

    readings = supplementary_readings(node=node, published=published)
    value: dict[str, Any] = {
        "node": node,
        "health": readings.health_verdict().value,
        "signals": readings.signals(),
    }
    return report(
        TOOL_NAME,
        value=value,
        summary=readings.summary(),
        reference=f"proxmox:node-health:{node}",
    )


__all__ = ["TOOL_NAME", "proxmox_node_health"]
