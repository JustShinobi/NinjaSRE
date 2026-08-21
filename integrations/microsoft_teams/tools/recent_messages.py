"""Reading a capped number of Microsoft Teams's messages, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: Microsoft Teams's ``/v1.0/teams/{team_id}/channels/messages``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.microsoft_teams.client import MicrosoftTeamsClient
from integrations.microsoft_teams.schema import INTEGRATION

TOOL_NAME = "microsoft_teams_recent_messages"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "joining an incident channel where responders have already been talking",
    "finding what was tried before an automated investigation started",
)

_ANTI_EXAMPLES = (
    "system state, which chat reports secondhand and often wrongly",
    "a channel with no relation to the incident, where the messages are noise",
)


@tool(
    name=TOOL_NAME,
    display_name="Microsoft Teams recent messages",
    description=(
        "Return the recent messages in a channel, newest first and capped. What people have already said about an incident is evidence, and reading it is what stops an investigation repeating work that is already done."
    ),
    domain="communication",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.DOCUMENT,
    # The result carries what people or systems wrote, so it is one level up
    # from a count: masking applies, and a trace of it is treated as sensitive.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "communication",
        "microsoft_teams",
        "chat",
        "incident-channel",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def microsoft_teams_recent_messages(
    channel: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of Microsoft Teams's messages, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(MicrosoftTeamsClient, capability=TOOL_NAME)
    try:
        found = await client.recent_messages(
            channel, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "channel": channel,
            "start": start,
            "end": end,
            "messages": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.DOCUMENT,
                summary=f"{len(entries)} messages from Microsoft Teams{tail}",
                reference=f"microsoft_teams:recent_messages:{channel or 'all'}",
            ),
        ),
    )
