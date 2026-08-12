"""Turning a log answer into something a report can quote and a console can draw.

Two decisions here, and each is a way the answer arrives true and reads wrongly.

**The bound is in the value, not only in a log line.** Five hundred lines out of
ten thousand, or fifteen minutes of a source that keeps ten, produces a responder
who concludes there was nothing in the logs — which is the opposite of what
happened. So ``summary`` and ``complete`` travel beside the lines, and the
evidence entry carries the sentence too.

**The evidence cites the query, not the source.** One entry naming the selector
and the window actually read, so a conclusion drawn from these lines can be
checked by somebody who was not there — including the case where the answer was
short.
"""

from __future__ import annotations

from typing import Any

from config.constants.observability_bridge import LOG_REFERENCE_PREFIX, LOGS_TOOL_NAME
from core.capability.metadata import EvidenceType
from core.capability.result import Evidence
from platform.observation.bridge.logs import LogAnswer

#: What the evidence entries name as their source. Not a vendor: the claim is
#: made from the deployment's log system, whichever one answered.
LOG_EVIDENCE_SOURCE = "logs"


def render(answer: LogAnswer) -> str:
    """Return the whole answer as one block of text, the bound included."""
    lines = [answer.summary]
    lines.extend(f"{line.observed_at.isoformat()} {line.line}" for line in answer.lines)
    if not answer.lines:
        lines.append(
            "The stream matched nothing in this window. The source answered, so this is "
            "a quiet guest rather than a log system nobody could reach."
        )
    return "\n".join(lines)


def evidence_for(answer: LogAnswer) -> tuple[Evidence, ...]:
    """Return one entry for the query, carrying its own bound.

    One rather than one per line: the finding is what the window held, and a
    hundred entries saying the same thing would bury the sentence that says how
    much of the window was actually read.
    """
    return (
        Evidence(
            source=LOG_EVIDENCE_SOURCE,
            evidence_type=EvidenceType.LOG,
            summary=answer.summary,
            reference=f"{LOG_REFERENCE_PREFIX}:{answer.selector}@{answer.start.isoformat()}",
        ),
    )


def shape(answer: LogAnswer) -> dict[str, Any]:
    """Return the structured value the tool hands back.

    Both a rendered block and the structured answer: the text is what the model
    reads, the structure is what the trace and the console read, and deriving
    one from the other afterwards is how the two come to disagree.
    """
    return {
        "tool": LOGS_TOOL_NAME,
        "selector": answer.selector,
        "start": answer.start.isoformat(),
        "end": answer.end.isoformat(),
        "lines": [
            {
                "at": line.observed_at.isoformat(),
                "line": line.line,
                "labels": dict(line.labels),
            }
            for line in answer.lines
        ],
        "complete": answer.complete,
        "truncated": answer.truncated,
        "retention_shortfall_seconds": answer.retention_shortfall_seconds,
        "summary": answer.summary,
        "text": render(answer),
    }


__all__ = ["LOG_EVIDENCE_SOURCE", "evidence_for", "render", "shape"]
