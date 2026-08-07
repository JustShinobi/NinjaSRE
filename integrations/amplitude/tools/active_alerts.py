"""Reading a capped number of Amplitude's alerts, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: Amplitude's ``/api/2/annotations``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.amplitude.client import AmplitudeClient
from integrations.amplitude.schema import INTEGRATION

TOOL_NAME = "amplitude_active_alerts"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "establishing what else was already broken when this alert fired",
    "finding the earliest firing alert, which is usually nearest the cause",
)

_ANTI_EXAMPLES = (
    "the value of a metric, which needs a query rather than an alert list",
    "an alert that resolved before the investigation started",
)


@tool(
    name=TOOL_NAME,
    display_name="Amplitude active alerts",
    description=(
        "List the alert rules currently firing, with their labels and the time each started. Reach for it early: what else is already alerting is the cheapest way to tell a local failure from a shared one."
    ),
    domain="metrics",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.EVENT,
    # Returns records the vendor's control plane produced rather than anything
    # a user typed, so a plain read is the honest level.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "metrics",
        "amplitude",
        "analytics",
        "product",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def amplitude_active_alerts(
    state: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of Amplitude's alerts, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(AmplitudeClient, capability=TOOL_NAME)
    try:
        found = await client.list_alerts(
            state, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "state": state,
            "start": start,
            "end": end,
            "alerts": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.EVENT,
                summary=f"{len(entries)} alerts from Amplitude{tail}",
                reference=f"amplitude:active_alerts:{state or 'all'}",
            ),
        ),
    )
