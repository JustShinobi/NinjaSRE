"""Reading a capped number of PagerDuty's timeline entries, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: PagerDuty's ``/incidents``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.pagerduty.client import PagerdutyClient
from integrations.pagerduty.schema import INTEGRATION

TOOL_NAME = "pagerduty_incident_timeline"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "picking up an incident somebody else has already been working",
    "recovering what was tried before the current responder arrived",
)

_ANTI_EXAMPLES = (
    "how many incidents there are, which the statistics answer",
    "system state, which the timeline only reports secondhand",
)


@tool(
    name=TOOL_NAME,
    display_name="PagerDuty incident timeline",
    description=(
        "Return one incident's timeline — the notes, escalations, and status changes, oldest first and capped. It is what tells an investigation what humans already tried, so it does not repeat them."
    ),
    domain="incident",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.INCIDENT,
    # The result carries what people or systems wrote, so it is one level up
    # from a count: masking applies, and a trace of it is treated as sensitive.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "incident",
        "pagerduty",
        "paging",
        "oncall",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def pagerduty_incident_timeline(
    incident: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of PagerDuty's timeline entries, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(PagerdutyClient, capability=TOOL_NAME)
    try:
        found = await client.incident_timeline(
            incident, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "incident": incident,
            "start": start,
            "end": end,
            "timeline_entries": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.INCIDENT,
                summary=f"{len(entries)} timeline entries from PagerDuty{tail}",
                reference=f"pagerduty:incident_timeline:{incident or 'all'}",
            ),
        ),
    )
