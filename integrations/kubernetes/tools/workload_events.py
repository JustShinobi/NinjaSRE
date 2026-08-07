"""Reading what Kubernetes says happened to a workload.

The single highest-value read in the integration, and the one that turns an
observation into a root cause. "The pod restarted" is a symptom that a dozen
mechanisms produce; ``reason=OOMKilled`` on the event that preceded it is the
mechanism, written down by the kubelet at the moment it happened.

Events are also the shortest-lived evidence in the cluster. The default
retention is an hour, so an investigation that reads logs first and events
second regularly finds the events already gone — which is why the skill puts
this call first and why the capability exists separately from anything that
reads pod state.

Source of truth: the core API's namespaced events collection, paged by continue
token.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.kubernetes.client import KubernetesClient
from integrations.kubernetes.schema import INTEGRATION

TOOL_NAME = "kubernetes_workload_events"

#: How many events one call returns. A workload in a crash loop generates them
#: faster than anything reads them, and the recent ones explain the incident.
DEFAULT_EVENT_LIMIT = 50

_USE_CASES = (
    "finding why a pod restarted, which the event's reason states outright",
    "distinguishing an eviction from a crash from a failed image pull",
    "establishing when a workload's trouble started, from the first warning event",
)

_ANTI_EXAMPLES = (
    "reading application output, which is a log question and not an event one",
    "anything older than the cluster's event retention, typically one hour",
    "cluster-wide health, where every workload's events at once is noise",
)


@tool(
    name=TOOL_NAME,
    display_name="Kubernetes workload events",
    description=(
        "Read Kubernetes events for a namespace, optionally for one object by name. "
        "Events carry the reason a pod was killed, evicted, or failed to schedule — the "
        "mechanism behind a restart rather than the fact of it. Call this first: events "
        "expire in about an hour, so they are the shortest-lived evidence available."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.EVENT,
    # Control-plane events: object names, reasons, and messages the kubelet
    # wrote. No application output, so nothing a user typed reaches here.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("kubernetes", "events", "restart", "cloud_control_plane"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def kubernetes_workload_events(
    namespace: str,
    object_name: str = "",
    limit: int = DEFAULT_EVENT_LIMIT,
) -> CapabilityResult:
    """Return recent events in ``namespace``, narrowed to ``object_name`` if given."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(KubernetesClient, capability=TOOL_NAME)
    try:
        found = await client.list_events(
            namespace=namespace,
            object_name=object_name,
            max_items=min(limit, DEFAULT_EVENT_LIMIT),
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    events = [_event(event) for event in found.items]
    return CapabilityResult.ok(
        TOOL_NAME,
        value={"namespace": namespace, "object": object_name, "events": events},
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.EVENT,
                summary=_summary(namespace, object_name, events),
                reference=f"kubernetes:events:{namespace}/{object_name or '*'}",
            ),
        ),
    )


def _event(event: dict[str, Any]) -> dict[str, Any]:
    """Return the fields of one event that carry the mechanism."""
    involved = event.get("involvedObject", {})
    return {
        "reason": str(event.get("reason", "")),
        "type": str(event.get("type", "")),
        "message": str(event.get("message", "")),
        "count": event.get("count"),
        "object": str(involved.get("name", "")) if isinstance(involved, dict) else "",
        "last_seen": str(event.get("lastTimestamp", "")),
    }


def _summary(namespace: str, object_name: str, events: list[dict[str, Any]]) -> str:
    """Return the one line a conclusion can be checked against."""
    scope = f"{namespace}/{object_name}" if object_name else namespace
    if not events:
        return (
            f"no events in {scope} — either nothing happened, or the events expired "
            f"before this was asked"
        )
    warnings = [event for event in events if event["type"] == "Warning"]
    if not warnings:
        return f"{len(events)} events in {scope}, none of them warnings"
    reasons = sorted({event["reason"] for event in warnings if event["reason"]})
    return f"{len(warnings)} warning event(s) in {scope}: {', '.join(reasons)}"
