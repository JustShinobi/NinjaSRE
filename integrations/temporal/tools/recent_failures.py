"""Reading a capped number of Temporal's failures, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: Temporal's ``/api/v1/namespaces/{namespace}/workflows``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.temporal.client import TemporalClient
from integrations.temporal.schema import INTEGRATION

TOOL_NAME = "temporal_recent_failures"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "finding the first failure in a chain of downstream ones",
    "checking whether a retry succeeded before treating a failure as current",
)

_ANTI_EXAMPLES = (
    "how far behind the platform is, which the health summary answers",
    "a slow but succeeding pipeline, where nothing has failed to list",
)


@tool(
    name=TOOL_NAME,
    display_name="Temporal recent failures",
    description=(
        "Return the recently failed tasks or jobs, newest first and capped, with the reason each gave. Call it after the health summary, so the ones read are from whichever stage the backlog pointed at."
    ),
    domain="data_platform",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.EVENT,
    # Returns records the vendor's control plane produced rather than anything
    # a user typed, so a plain read is the honest level.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "data_platform",
        "temporal",
        "workflows",
        "durable",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def temporal_recent_failures(
    scope: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of Temporal's failures, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(TemporalClient, capability=TOOL_NAME)
    try:
        found = await client.list_failures(
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
            "failures": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.EVENT,
                summary=f"{len(entries)} failures from Temporal{tail}",
                reference=f"temporal:recent_failures:{scope or 'all'}",
            ),
        ),
    )
