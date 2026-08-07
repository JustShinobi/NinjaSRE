"""Reading a capped number of Confluence's issues, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: Confluence's ``/wiki/rest/api/content/search``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.confluence.client import ConfluenceClient
from integrations.confluence.schema import INTEGRATION

TOOL_NAME = "confluence_recent_issues"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "reading the ticket that already describes the symptom under investigation",
    "finding who last worked on a recurring failure",
)

_ANTI_EXAMPLES = (
    "how many issues there are, which the statistics answer more cheaply",
    "the current state of the system, which a ticket only describes secondhand",
)


@tool(
    name=TOOL_NAME,
    display_name="Confluence recent issues",
    description=(
        "Return the issues matching a query, newest first and capped, with title, status, and assignee. Call it after the statistics so the ones read are from the group that matters."
    ),
    domain="ticketing",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.DOCUMENT,
    # The result carries what people or systems wrote, so it is one level up
    # from a count: masking applies, and a trace of it is treated as sensitive.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "ticketing",
        "confluence",
        "docs",
        "runbooks",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def confluence_recent_issues(
    query: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of Confluence's issues, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(ConfluenceClient, capability=TOOL_NAME)
    try:
        found = await client.recent_issues(
            query, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "query": query,
            "start": start,
            "end": end,
            "issues": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.DOCUMENT,
                summary=f"{len(entries)} issues from Confluence{tail}",
                reference=f"confluence:recent_issues:{query or 'all'}",
            ),
        ),
    )
