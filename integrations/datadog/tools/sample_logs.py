"""Reading the log lines the statistics pointed at.

The second call, and only the second. Its value is entirely in what preceded it:
a sample drawn from the group an aggregation singled out is evidence, and the
same sample drawn from an unnarrowed query is fifty arbitrary lines that happen
to be recent.

``truncated`` travels with the result, and a caller that drops it is reporting
"these are the matches" when what happened was "we stopped looking". That
distinction is how an investigation concludes that something did not happen.

``read_sensitive`` rather than ``read``: log bodies carry whatever the
application logged, which regularly includes user identifiers and request
payloads. The classification is not about Datadog; it is about what is in a log
line.

Source of truth: Datadog's logs search endpoint,
``POST /api/v2/logs/events/search``, paged by cursor.
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

TOOL_NAME = "datadog_sample_logs"

#: How many lines one call returns. Small on purpose: the point of a sample is
#: that it is representative, and a hundred lines in a context window buys
#: nothing the tenth line did not already say.
DEFAULT_SAMPLE_SIZE = 20

_USE_CASES = (
    "reading the actual error message from the group an aggregation singled out",
    "getting the stack trace behind a spike the counts have already located",
    "quoting two or three representative lines into a finding",
)

_ANTI_EXAMPLES = (
    "an unnarrowed query, where the sample is arbitrary and teaches nothing",
    "counting anything — the statistics capability answers that in one call",
    "exporting logs in bulk, which this deliberately cannot do",
)


@tool(
    name=TOOL_NAME,
    display_name="Datadog sample logs",
    description=(
        "Return a small sample of Datadog log lines matching a query in a window, newest "
        "first. Use it after the statistics call has singled out a status, service, or "
        "host, and narrow the query to that group — a sample from an unnarrowed query is "
        "arbitrary. The result says whether more matched than were returned."
    ),
    domain="logstore",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.LOG,
    # Log bodies carry whatever the application logged, which regularly
    # includes user identifiers and request payloads.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("logs", "errors", "samples", "logstore"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def datadog_sample_logs(
    query: str,
    start: str,
    end: str,
    limit: int = DEFAULT_SAMPLE_SIZE,
) -> CapabilityResult:
    """Return up to ``limit`` matching log lines, and whether there were more."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(DatadogClient, capability=TOOL_NAME)
    try:
        found = await client.search_logs(
            query, start=start, end=end, limit=min(limit, DEFAULT_SAMPLE_SIZE)
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    lines = [_line(event) for event in found.items]
    return CapabilityResult.ok(
        TOOL_NAME,
        value={"query": query, "start": start, "end": end, "lines": lines},
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.LOG,
                summary=(
                    f"{len(lines)} log lines matching {query!r}"
                    + (", and more matched than were read" if found.truncated else "")
                ),
                reference=f"datadog:logs:search:{query}@{start}..{end}",
            ),
        ),
    )


def _line(event: dict[str, Any]) -> dict[str, Any]:
    """Return the fields of one event a finding is written from.

    The message, the service, the status, and the timestamp — not the whole
    document. A log event carries dozens of attributes and a capability that
    returned all of them would spend a context budget on tags.
    """
    attributes = event.get("attributes", {})
    if not isinstance(attributes, dict):
        return {"message": "", "service": "", "status": "", "timestamp": ""}
    return {
        "message": str(attributes.get("message", "")),
        "service": str(attributes.get("service", "")),
        "status": str(attributes.get("status", "")),
        "timestamp": str(attributes.get("timestamp", "")),
    }
