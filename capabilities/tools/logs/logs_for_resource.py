"""Reading one resource's logs, bounded, with the bound in the answer.

The bridge could read a log stream and the catalogue could say which stream a
resource has. No capability joined them, so an investigation could read metrics
and changes and never a log line — the one evidence type an operator reaches for
first.

**It takes a resource, not a selector.** A tool accepting a raw stream selector
would be a second query language the model composes and the deployment has to
keep working, and a selector the model invented can silently match nothing. The
catalogue owns the mapping from a resource to its stream; this names a resource.

**The bound travels with the lines.** Five hundred lines out of ten thousand, or
fifteen minutes from a source that keeps ten, reads exactly like a quiet guest.
Every answer carries what it was allowed to read, and the summary is what a
report quotes beside the lines.

**Four outcomes, because the next move differs for each.** Lines are evidence. No
lines from a source that answered is a quiet guest, which is a finding. A
resource the estate does not hold is an alert naming something nobody watches. A
deployment with no log source is told what to point at, rather than handed a
negative it did not earn.

Source of truth: whichever log system the deployment composed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from capabilities.tools.logs import binding, results
from capabilities.tools.logs.binding import LogSourceUnavailable
from config.constants.observability_bridge import LOGS_TOOL_NAME
from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, SideEffectLevel
from core.capability.result import CapabilityErrorClass, CapabilityResult

TOOL_NAME = LOGS_TOOL_NAME

_USE_CASES = (
    "reading what a guest was logging around the time a symptom started",
    "confirming a service inside a container restarted, rather than inferring it from metrics",
    "establishing that a guest logged nothing unusual, so the cause is elsewhere",
)

# The first anti-example is the important one: asked before an affected resource
# is known, this can only be answered by guessing a resource, and a guessed
# resource returns somebody else's lines.
_ANTI_EXAMPLES = (
    "asking on the alert text before an affected resource has been identified",
    "searching the whole cluster's logs for a string, which this deliberately cannot do",
    "reading a log stream to build a dashboard, which is a report rather than an investigation",
)


@tool(
    name=TOOL_NAME,
    display_name="Logs for resource",
    description=(
        "Return what a specific resource's log stream held in a recent window, with the "
        "bound that shaped the answer. Every result says how much of the window was "
        "actually read: a source keeping less than the window asked for, or an answer "
        "stopped at the line limit, is reported rather than left to look like a quiet "
        "guest. An empty answer from a source that responded is a finding — it means the "
        "resource logged nothing, not that nobody could look. Call this once you know "
        "which resource is affected, not on the alert text."
    ),
    domain="observability",
    evidence_source=results.LOG_EVIDENCE_SOURCE,
    evidence_type=EvidenceType.LOG,
    # Reads somebody else's log system and writes nothing. Sensitive rather than
    # plain read because log lines are text people and their services wrote, and
    # may carry anything that was in scope when they were emitted.
    side_effect_level=SideEffectLevel.READ_SENSITIVE,
    parallel_safe=True,
    tags=("logs", "observability", "loki", "journal", "evidence"),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def logs_for_resource(resource: str) -> CapabilityResult:
    """Return the lines ``resource``'s stream held in the deployment's log window."""
    access = binding.current()
    if access is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            "this deployment has no log source configured, so nothing was read. An "
            "absence from a system nobody pointed at is not evidence that the resource "
            "was quiet.",
            detail=f"asked about {resource!r}",
        )

    try:
        answer = await access.logs_for(resource, at=datetime.now(UTC))
    except LogSourceUnavailable as unreachable:
        # Unavailable rather than empty: "we could not look" and "there was
        # nothing there" lead an investigation in opposite directions.
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.UNAVAILABLE,
            f"the log source did not answer: {unreachable}. Nothing can be "
            f"concluded about what {resource!r} logged.",
            detail=f"asked about {resource!r}",
        )

    if answer is None:
        return CapabilityResult.failed(
            TOOL_NAME,
            CapabilityErrorClass.NOT_FOUND,
            f"this estate holds no resource called {resource!r} with a log stream, so "
            f"there is nothing to read. An alert naming something the estate does not "
            f"hold is itself a finding.",
            detail="no selector rule applies, or the estate does not hold it",
        )

    return CapabilityResult.ok(
        TOOL_NAME,
        value=results.shape(answer),
        evidence=results.evidence_for(answer),
        truncated=answer.truncated,
    )


__all__ = ["TOOL_NAME", "logs_for_resource"]
