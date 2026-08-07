"""Reading a capped number of Hermes's log lines, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: Hermes's ``/v1/logs/search``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.hermes.client import HermesClient
from integrations.hermes.schema import INTEGRATION

TOOL_NAME = "hermes_sample_logs"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "reading the actual error text behind a spike the statistics located",
    "checking whether a stack trace matches one from a previous incident",
)

_ANTI_EXAMPLES = (
    "establishing how much of something there is, which sampling cannot answer",
    "a query that has not been narrowed, where the sample is arbitrary",
)


@tool(
    name=TOOL_NAME,
    display_name="Hermes log samples",
    description=(
        "Return a small, capped sample of the log lines matching a query over a window, newest first. Narrow the query with the statistics capability before calling this: a sample from an unnarrowed query is arbitrary."
    ),
    domain="logstore",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.LOG,
    # The result carries what people or systems wrote, so it is one level up
    # from a count: masking applies, and a trace of it is treated as sensitive.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "logstore",
        "hermes",
        "logs",
        "classification",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def hermes_sample_logs(
    query: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of Hermes's log lines, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(HermesClient, capability=TOOL_NAME)
    try:
        found = await client.recent_logs(
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
            "log_lines": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.LOG,
                summary=f"{len(entries)} log lines from Hermes{tail}",
                reference=f"hermes:sample_logs:{query or 'all'}",
            ),
        ),
    )
