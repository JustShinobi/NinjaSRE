"""Reading a capped number of MongoDB Atlas's statements, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: MongoDB Atlas's ``/api/atlas/v2/groups/{group}/clusters``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.mongodb_atlas.client import MongodbAtlasClient
from integrations.mongodb_atlas.schema import INTEGRATION

TOOL_NAME = "mongodb_atlas_slow_queries"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "a database whose sessions are dominated by one kind of work",
    "finding the statement behind a latency change with a known start",
)

_ANTI_EXAMPLES = (
    "whether the database is the problem at all, which sessions answer first",
    "a connectivity failure, where no statement ever ran",
)


@tool(
    name=TOOL_NAME,
    display_name="MongoDB Atlas slow queries",
    description=(
        "Return the slowest statements recorded, capped, with their timing. Call it after the session statistics: a slow query on an unblocked database is a different problem from the same query behind a lock queue."
    ),
    domain="database",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.ANALYSIS,
    # The result carries what people or systems wrote, so it is one level up
    # from a count: masking applies, and a trace of it is treated as sensitive.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "database",
        "mongodb_atlas",
        "mongodb",
        "atlas",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def mongodb_atlas_slow_queries(
    scope: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of MongoDB Atlas's statements, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(MongodbAtlasClient, capability=TOOL_NAME)
    try:
        found = await client.slow_queries(
            scope, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "scope": scope,
            "start": start,
            "end": end,
            "statements": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.ANALYSIS,
                summary=f"{len(entries)} statements from MongoDB Atlas{tail}",
                reference=f"mongodb_atlas:slow_queries:{scope or 'all'}",
            ),
        ),
    )
