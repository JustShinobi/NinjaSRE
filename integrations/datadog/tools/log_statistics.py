"""Counting Datadog's logs before reading any of them.

The first call of a log investigation, and the one that is skipped most often.
Four hundred thousand matching lines have a shape — which status, which service,
which host, and how that distribution differs from an hour ago — and that shape
decides which fifty lines are worth reading. Fifty lines chosen before the shape
is known tell you about fifty lines.

The aggregation happens on Datadog's side. That is not an optimisation: the
volume never crosses the wire, so it never enters a context budget, and the
capability stays affordable on the incident where the log volume is itself the
symptom.

Source of truth: Datadog's logs analytics aggregate endpoint,
``POST /api/v2/logs/analytics/aggregate``, grouped by one facet.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.datadog.client import DatadogClient
from integrations.datadog.schema import INTEGRATION

TOOL_NAME = "datadog_log_statistics"

_USE_CASES = (
    "an error-rate alert where the failing status, service, or host is not yet known",
    "establishing whether one thing is failing loudly or everything is failing",
    "comparing the shape of a window against the equivalent window before the symptom",
)

_ANTI_EXAMPLES = (
    "reading a specific error message, which is what sampling is for",
    "latency across services, which a trace answers and a log count does not",
    "a question about a single known request, where the count is one",
)


@tool(
    name=TOOL_NAME,
    display_name="Datadog log statistics",
    description=(
        "Count Datadog logs matching a query over a window, grouped by one facet — "
        "status, service, host, or any other. Returns the distribution rather than the "
        "lines, so it is affordable on a query matching millions. Call this before "
        "sampling: the group it singles out is where the samples should come from."
    ),
    domain="logstore",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.LOG,
    # Reads log aggregations and returns counts, not message bodies. The
    # sampling capability, which does return bodies, is read_sensitive.
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("logs", "errors", "statistics", "logstore"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def datadog_log_statistics(
    query: str,
    start: str,
    end: str,
    group_by: str = "status",
) -> CapabilityResult:
    """Return the counts for ``query`` in the window, grouped by ``group_by``.

    ``start`` and ``end`` are Datadog's own time expressions — ``now-1h``, an
    ISO timestamp, an epoch in milliseconds. Both are required rather than
    defaulted, because a capability that let the vendor choose the window would
    silently read the wrong hours.
    """
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(DatadogClient, capability=TOOL_NAME)
    try:
        answer = await client.aggregate_logs(query, start=start, end=end, group_by=group_by)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    buckets = _buckets(answer)
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "query": query,
            "start": start,
            "end": end,
            "group_by": group_by,
            "buckets": buckets,
        },
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.LOG,
                summary=_summary(query, group_by, buckets),
                reference=f"datadog:logs:aggregate:{query}@{start}..{end}",
            ),
        ),
    )


def _buckets(answer: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the grouped counts, read defensively rather than by index.

    An error response has the same content type as a successful one, and
    indexing into it raises a ``KeyError`` a long way from the cause.
    """
    data = answer.get("data")
    if not isinstance(data, dict):
        return []
    found: list[dict[str, Any]] = []
    for bucket in data.get("buckets", ()):
        if not isinstance(bucket, dict):
            continue
        found.append({"by": bucket.get("by", {}), "count": bucket.get("computes", {}).get("c0", 0)})
    return found


def _summary(query: str, group_by: str, buckets: list[dict[str, Any]]) -> str:
    """Return the one line a conclusion can be checked against."""
    if not buckets:
        return f"no logs matched {query!r} in the window"
    total = sum(int(bucket["count"] or 0) for bucket in buckets)
    leader = max(buckets, key=lambda bucket: int(bucket["count"] or 0))
    return (
        f"{total} logs matched {query!r}, across {len(buckets)} {group_by} groups; "
        f"the largest is {leader['by']} with {leader['count']}"
    )
