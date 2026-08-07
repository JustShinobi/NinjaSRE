"""Counting New Relic's series before reading any of them.

The first call of an investigation that reaches New Relic, and the one
most often skipped. A large answer has a shape — which group, which state, how
that distribution differs from an hour ago — and the shape decides which few
records are worth reading. Records chosen before the shape is known tell you
about those records and nothing else.

Source of truth: New Relic's ``/v2/applications.json``, read through the
bounded page walk in ``client.py`` and grouped by one field.
"""

from __future__ import annotations

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations._base.payload import counted, leader_of, total_of
from integrations.new_relic.client import NewRelicClient
from integrations.new_relic.schema import INTEGRATION

TOOL_NAME = "new_relic_metric_statistics"

#: The field the distribution is taken across when the caller names none. The
#: one that concentrates a failure most often for this vendor.
DEFAULT_GROUP_BY = "health_status"

#: How many records are read before the counting stops. The distribution is over
#: what was read, and the result says so — a statistic quoted as if it covered
#: everything is worse than no statistic.
MAX_RECORDS = 500

_USE_CASES = (
    "a saturation or error-rate alert where the affected instance is unknown",
    "establishing whether a change is one instance or the whole fleet",
)

# Anti-examples suppress this capability when they describe the incident. They
# are the field most often left empty, and without them the tool competes for a
# slot on every incident that happens to share a tag.
_ANTI_EXAMPLES = (
    "reading an individual log line, which a metric never contains",
    "a question about a single request, where a metric has no resolution",
)


@tool(
    name=TOOL_NAME,
    display_name="New Relic metric statistics",
    description=(
        "Evaluate a metric query over a window and return the series grouped by one label, with counts, rather than every sample. Use it to find which label value moved before asking anything about why."
    ),
    domain="metrics",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.METRIC,
    # Returns counts rather than record bodies, so nothing a user typed reaches
    # the result. The sampling sibling, which does return bodies, is a level up.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=(
        "metrics",
        "new_relic",
        "metrics",
        "nrql",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def new_relic_metric_statistics(
    query: str = "",
    start: str = "",
    end: str = "",
    group_by: str = DEFAULT_GROUP_BY,
) -> CapabilityResult:
    """Return the distribution of New Relic's series across ``group_by``.

    ``start`` and ``end`` are New Relic's own time expressions. Both are
    passed through rather than defaulted here, because a capability that let the
    vendor choose the window would read the wrong hours without saying so.
    """
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(NewRelicClient, capability=TOOL_NAME)
    try:
        found = await client.query_metric(query, start=start, end=end, limit=MAX_RECORDS)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    buckets = counted(found.items, group_by)
    total = total_of(buckets)
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "query": query,
            "start": start,
            "end": end,
            "group_by": group_by,
            "buckets": list(buckets),
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.METRIC,
                summary=_summary(total, group_by, buckets, found.truncated),
                reference=f"new_relic:metric_statistics:{query or 'all'}",
            ),
        ),
    )


def _summary(
    total: int,
    group_by: str,
    buckets: tuple[dict[str, object], ...],
    truncated: bool,
) -> str:
    """Return the one line a conclusion can be checked against."""
    if not buckets:
        return "no series were returned by New Relic for this request"
    leader = leader_of(buckets)
    tail = ", and more matched than were counted" if truncated else ""
    return (
        f"{total} series across {len(buckets)} {group_by} group(s); the largest is {leader!r}{tail}"
    )
