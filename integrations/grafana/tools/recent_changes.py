"""Reading a capped number of Grafana's changes, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: Grafana's ``/api/annotations``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.grafana.client import GrafanaClient
from integrations.grafana.schema import INTEGRATION

TOOL_NAME = "grafana_recent_changes"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "an incident whose start time is known and whose cause is not",
    "checking whether anything was changed shortly before the symptom",
)

_ANTI_EXAMPLES = (
    "how much of the estate is affected, which the inventory answers",
    "a symptom with no change window, where the history is noise",
)


@tool(
    name=TOOL_NAME,
    display_name="Grafana recent changes",
    description=(
        "Return the control-plane changes in a window, newest first and capped. Most incidents follow a change, and this is the capability that turns 'it started at 14:05' into a specific thing somebody did."
    ),
    domain="cloud_control_plane",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.CHANGE,
    # Returns records the vendor's control plane produced rather than anything
    # a user typed, so a plain read is the honest level.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "cloud_control_plane",
        "grafana",
        "dashboards",
        "annotations",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def grafana_recent_changes(
    kind: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of Grafana's changes, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(GrafanaClient, capability=TOOL_NAME)
    try:
        found = await client.list_changes(
            kind, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "kind": kind,
            "start": start,
            "end": end,
            "changes": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.CHANGE,
                summary=f"{len(entries)} changes from Grafana{tail}",
                reference=f"grafana:recent_changes:{kind or 'all'}",
            ),
        ),
    )
