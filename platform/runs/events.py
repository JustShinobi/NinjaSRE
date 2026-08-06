"""The kinds of thing a run's log records, and the shape one carries.

Closed on purpose. An event kind nobody named is an event a console cannot
render, a replay cannot label, and an evaluation cannot count — so a new one is
a deliberate addition here rather than a string invented at a call site.

The list is what an operator asks about after the fact: what did the model do,
what did it call, what did the platform stop it from doing, and what did the
platform take away from it. The last two are the ones worth having and the ones
easiest to leave out, because they are the events where nothing the user asked
for happened.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from platform.persistence.ports.run_trace_store import TraceEventRecord


class TraceEventKind(StrEnum):
    """What one entry in a run's log is about."""

    RUN_STARTED = "run_started"
    TURN_COMPLETED = "turn_completed"
    CAPABILITY_CALLED = "capability_called"
    EVIDENCE_OBSERVED = "evidence_observed"
    SUBAGENT_DISPATCHED = "subagent_dispatched"
    GUARDRAIL_ACTION = "guardrail_action"
    MASKING_APPLIED = "masking_applied"
    BUDGET_EVICTION = "budget_eviction"
    APPROVAL_REQUESTED = "approval_requested"
    RUN_INTERRUPTED = "run_interrupted"
    RUN_FINISHED = "run_finished"


@dataclass(frozen=True, slots=True)
class RunEvent:
    """One entry in a run's log, as everything above the store sees it.

    The same fields as the stored record, with ``kind`` typed and the tenant
    implied by whoever handed it over. It exists so a subscriber holds something
    that named its kinds rather than a string it has to compare against
    literals — the broker delivers these, and the persistence record is what the
    store round-trips.
    """

    run_id: str
    kind: TraceEventKind
    sequence: int
    occurred_at: datetime | None = None
    turn_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, record: TraceEventRecord) -> RunEvent:
        """Return the event ``record`` describes.

        An unrecognised kind raises. A trace written by a newer version of this
        code is a trace this one cannot faithfully render, and rendering it
        approximately is how a console quietly stops showing a class of event.
        """
        return cls(
            run_id=record.run_id,
            kind=TraceEventKind(record.kind),
            sequence=record.sequence,
            occurred_at=record.occurred_at,
            turn_id=record.turn_id,
            payload=dict(record.payload),
        )


__all__ = ["RunEvent", "TraceEventKind"]
