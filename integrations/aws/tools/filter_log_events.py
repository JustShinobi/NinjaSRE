"""Reading CloudWatch log events for one group over one window.

The capability the AWS integration exists for, and the one whose arguments are
worth defending. Both ends of the window are required and both are epoch
milliseconds, which is what CloudWatch takes — a capability that let the vendor
default the window would read whatever CloudWatch considers recent, and the
answer would be silently about the wrong hours.

``truncated`` travels with the result. CloudWatch will return a next token
indefinitely on a busy group, and the walk stops at the page ceiling; a caller
that drops the flag reports "these are the matches" when what happened was "we
stopped looking".

``read_sensitive`` rather than ``read``: log bodies carry whatever the
application wrote, which regularly includes user identifiers and request
payloads.

Source of truth: CloudWatch Logs ``FilterLogEvents``, paged by ``nextToken``.
"""

from __future__ import annotations

from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.aws.client import CloudWatchLogsClient, log_event_message
from integrations.aws.schema import INTEGRATION

TOOL_NAME = "aws_filter_log_events"

#: How many events one call returns. CloudWatch will happily return ten
#: thousand; an investigation reads the first few and pays for the rest.
DEFAULT_EVENT_LIMIT = 50

_USE_CASES = (
    "reading the error text behind a Lambda or ECS failure in a known window",
    "checking whether a service logged anything at all during an outage",
    "finding the first occurrence of an error, to establish onset",
)

_ANTI_EXAMPLES = (
    "counting events, which this does expensively and a metric does in one call",
    "searching every log group at once, which CloudWatch cannot do",
    "a window wider than the group's retention, which returns nothing either way",
)


@tool(
    name=TOOL_NAME,
    display_name="AWS filter log events",
    description=(
        "Read CloudWatch log events from one log group between two epoch-millisecond "
        "timestamps, optionally narrowed by a CloudWatch filter pattern. Both ends of the "
        "window are required. Returns the messages with their timestamps and stream "
        "names, and says when more matched than were read."
    ),
    domain="logstore",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.LOG,
    # Log bodies carry whatever the application wrote, which regularly includes
    # user identifiers and request payloads.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    requires=Requirements(integrations=(INTEGRATION,)),
    tags=("logs", "cloudwatch", "aws", "logstore"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def aws_filter_log_events(
    log_group: str,
    start_ms: int,
    end_ms: int,
    pattern: str = "",
    limit: int = DEFAULT_EVENT_LIMIT,
) -> CapabilityResult:
    """Return the events in ``log_group`` inside the window, and whether there were more."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(CloudWatchLogsClient, capability=TOOL_NAME)
    try:
        found = await client.filter_log_events(
            log_group,
            start_ms=start_ms,
            end_ms=end_ms,
            pattern=pattern,
            limit=min(limit, DEFAULT_EVENT_LIMIT),
        )
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    events = [_event(event) for event in found.items]
    return CapabilityResult.ok(
        TOOL_NAME,
        value={
            "log_group": log_group,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "pattern": pattern,
            "events": events,
        },
        truncated=found.truncated,
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.LOG,
                summary=(
                    f"{len(events)} CloudWatch event(s) in {log_group}"
                    + (f" matching {pattern!r}" if pattern else "")
                    + (", and more matched than were read" if found.truncated else "")
                ),
                reference=f"aws:logs:{client.region}:{log_group}@{start_ms}..{end_ms}",
            ),
        ),
    )


def _event(event: dict[str, Any]) -> dict[str, Any]:
    """Return the three fields of one event a finding is written from."""
    return {
        "timestamp": event.get("timestamp"),
        "stream": str(event.get("logStreamName", "")),
        "message": log_event_message(event),
    }
