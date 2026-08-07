"""Reading a capped number of Jaeger's traces, after something narrowed the question.

Deliberately small. The point of a sample is that the query was narrowed first,
and a large sample from an unnarrowed query is the failure this capability's cap
exists to make impossible rather than merely discouraged.

The result says when more matched than were returned. An investigation reporting
"{n} of roughly {m}" is doing its job; one reporting "{n}" is wrong.

Source of truth: Jaeger's ``/api/traces``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.jaeger.client import JaegerClient
from integrations.jaeger.schema import INTEGRATION

TOOL_NAME = "jaeger_slow_traces"

#: How many records one call returns. Small on purpose: the model reads every
#: one of them, and the fiftieth rarely says anything the tenth did not.
DEFAULT_LIMIT = 20

_USE_CASES = (
    "finding an exemplar of the latency an aggregate has already located",
    "seeing which downstream call dominates a slow request",
)

_ANTI_EXAMPLES = (
    "establishing how common the slowness is, which needs the aggregate",
    "an error with no latency component, where traces add nothing",
)


@tool(
    name=TOOL_NAME,
    display_name="Jaeger slow traces",
    description=(
        "Return the slowest traces for a service in a window, capped, with their duration and root operation. Use it after the statistics have named the operation, so the exemplars are from the part that is actually slow."
    ),
    domain="tracing",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.TRACE,
    # Returns records the vendor's control plane produced rather than anything
    # a user typed, so a plain read is the honest level.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "tracing",
        "jaeger",
        "traces",
        "latency",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def jaeger_slow_traces(
    service: str = "",
    start: str = "",
    end: str = "",
    limit: int = DEFAULT_LIMIT,
) -> CapabilityResult:
    """Return up to ``limit`` of Jaeger's traces, newest first."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(JaegerClient, capability=TOOL_NAME)
    try:
        found = await client.slow_traces(
            service, start=start, end=end, limit=min(limit, DEFAULT_LIMIT)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    entries: list[dict[str, Any]] = [dict(entry) for entry in found.items]
    tail = ", and more matched than were read" if found.truncated else ""
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "service": service,
            "start": start,
            "end": end,
            "traces": entries,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.TRACE,
                summary=f"{len(entries)} traces from Jaeger{tail}",
                reference=f"jaeger:slow_traces:{service or 'all'}",
            ),
        ),
    )
