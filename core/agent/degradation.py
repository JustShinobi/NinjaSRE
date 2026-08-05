"""What comes back when the model becomes unavailable halfway through.

An investigation that gathered eleven observations and then lost its provider
has not produced nothing. It has produced eleven observations, and the operator
who is currently in the incident would like them.

So the failure path is a value, not an exception: the evidence is preserved, the
answer says plainly that the run did not finish and why, and the caller gets a
result whose status distinguishes "incomplete" from "wrong". A traceback would
throw away the work and tell the operator less than the partial answer does.

Nothing here retries. Retry is the provider client's job and it has already
happened by the time a failure reaches this module — retrying again here would
multiply two backoffs together and turn a thirty-second outage into a run that
appears to hang.
"""

from __future__ import annotations

from config.prompts.investigation import (
    DEGRADED_EVIDENCE_LINE,
    DEGRADED_INVESTIGATION_PREAMBLE,
)
from core.agent.runtime_port import RunResult, RunStatus
from core.agent.session import Session, SessionStatus


def degraded_answer(session: Session, *, failure: str) -> str:
    """Return the partial answer a failed run leaves behind.

    Written for an operator rather than for the model: it names the failure, the
    point the run reached, and every observation that survived it, each with the
    reference that makes it checkable.
    """
    lines = [
        DEGRADED_INVESTIGATION_PREAMBLE.format(
            iterations=session.iteration, failure=failure or "cause unrecorded"
        )
    ]
    if session.evidence:
        lines.append("")
        lines.extend(
            DEGRADED_EVIDENCE_LINE.format(
                capability=entry.capability,
                summary=entry.summary,
                reference=f" ({entry.reference})" if entry.reference else "",
            )
            for entry in session.evidence
        )
    return "\n".join(lines)


def degraded_result(session: Session, *, failure: str) -> RunResult:
    """Return the partial result for a run the model could not finish.

    The session is marked ``FAILED`` and the run ``PARTIAL``: the objective was
    not met, and the answer that came back is still worth reading. Collapsing
    the two would either hide a failure or throw away an answer.
    """
    session.status = SessionStatus.FAILED
    session.touch()
    return RunResult(
        session=session,
        status=RunStatus.PARTIAL,
        answer=degraded_answer(session, failure=failure),
        failure=failure,
    )


__all__ = [
    "degraded_answer",
    "degraded_result",
]
