"""The typed events every surface consumes, and the replay that proves them complete.

One vocabulary, thirteen kinds, and one hard requirement: replaying the
persisted events reconstructs the investigation view. That is not a
nice property to have — it is what makes the event stream a record rather than
a progress bar. A console that shows something the trace cannot reproduce is
showing something nobody can audit afterwards.

Two consequences follow, and both are visible in the types.

**Every event carries its own context.** A ``tool_end`` names the capability and
the call it belongs to rather than relying on the reader having seen the
matching ``tool_start``. Events are dropped, replayed from an offset, and
resumed after a reconnect, so an event that only makes sense in sequence makes
sense to nobody.

**A sink that fails does not fail the run.** A disconnected browser must not end
an incident investigation, so emission records the sink failure and continues.
The one exception would be a sink that persists the trace, and that is why the
recorder here is in-process and synchronous rather than something over a wire.

The wire format — SSE framing, the reconnect offset — belongs to the gateway.
This module owns the vocabulary and the JSON round trip, and nothing here knows
what a browser is.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from core.state.types import StageName
from platform.observability.logging import get_logger

logger = get_logger(__name__)


class PipelineEventKind(StrEnum):
    """What one event on the investigation stream says.

    Closed. A surface renders on this enum, so a fourteenth kind is a change
    every consumer sees — which is the point: an event nobody knows how to
    render is an event nobody renders.
    """

    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    THOUGHT = "thought"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_END = "subagent_end"
    EVIDENCE = "evidence"
    QUESTION = "question"
    APPROVAL_REQUEST = "approval_request"
    MESSAGE_QUEUED = "message_queued"
    RESULT = "result"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PipelineEvent:
    """One thing that happened during an investigation.

    A single shape for all thirteen kinds rather than thirteen classes. A
    consumer switches on ``kind`` either way, and one shape is what makes the
    JSON round trip a single function instead of a registry of parsers that can
    fall out of step with the producers.
    """

    kind: PipelineEventKind
    run_id: str = ""
    sequence: int = 0
    occurred_at: datetime = datetime.fromtimestamp(0, tz=UTC)
    stage: StageName | None = None
    text: str = ""
    capability: str = ""
    call_id: str = ""
    subagent: str = ""
    evidence_id: str = ""
    failed: bool = False
    detail: Mapping[str, str] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this event."""
        return {
            "kind": self.kind.value,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at.isoformat(),
            "stage": self.stage.value if self.stage else "",
            "text": self.text,
            "capability": self.capability,
            "call_id": self.call_id,
            "subagent": self.subagent,
            "evidence_id": self.evidence_id,
            "failed": self.failed,
            "detail": dict(self.detail),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> PipelineEvent:
        """Return the event a stored record describes."""
        stage = str(record.get("stage", ""))
        return cls(
            kind=PipelineEventKind(record["kind"]),
            run_id=str(record.get("run_id", "")),
            sequence=int(record.get("sequence", 0)),
            occurred_at=datetime.fromisoformat(str(record["occurred_at"])),
            stage=StageName(stage) if stage else None,
            text=str(record.get("text", "")),
            capability=str(record.get("capability", "")),
            call_id=str(record.get("call_id", "")),
            subagent=str(record.get("subagent", "")),
            evidence_id=str(record.get("evidence_id", "")),
            failed=bool(record.get("failed", False)),
            detail={str(key): str(value) for key, value in (record.get("detail") or {}).items()},
        )

    def to_json(self) -> str:
        """Return this event as one JSON document."""
        return json.dumps(self.to_record(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, document: str) -> PipelineEvent:
        """Return the event a JSON document describes."""
        return cls.from_record(json.loads(document))


@runtime_checkable
class EventSink(Protocol):
    """Somewhere events go: a browser connection, a log, a trace store."""

    async def emit(self, event: PipelineEvent) -> None:
        """Take ``event``, or raise — the stream records the failure and continues."""


@dataclass(slots=True)
class RecordingSink:
    """Keeps every event in memory, in order. What tests and replay read."""

    events: list[PipelineEvent] = field(default_factory=list)

    async def emit(self, event: PipelineEvent) -> None:
        """Store ``event``."""
        self.events.append(event)

    def records(self) -> tuple[dict[str, Any], ...]:
        """Return every event as a stored record, in order."""
        return tuple(event.to_record() for event in self.events)


class EventStream:
    """Assigns sequence numbers and fans events out to every sink.

    The sequence number is the stream's own, not a timestamp. Two events in the
    same millisecond are ordered by it, and a client reconnecting says which
    number it got to — a wall clock cannot answer either question.
    """

    def __init__(
        self,
        run_id: str,
        sinks: Sequence[EventSink] = (),
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._run_id = run_id
        self._sinks = tuple(sinks)
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._sequence = 0

    @property
    def run_id(self) -> str:
        """Return the investigation this stream belongs to."""
        return self._run_id

    @property
    def emitted(self) -> int:
        """Return how many events have been emitted."""
        return self._sequence

    async def emit(self, event: PipelineEvent) -> PipelineEvent:
        """Stamp ``event`` with its run, sequence, and time, then fan it out.

        A sink that raises is logged and skipped. A disconnected browser must
        not end an incident investigation, and a sink whose failure *should*
        stop the run has no business being on the fan-out list.
        """
        self._sequence += 1
        stamped = replace(
            event,
            run_id=self._run_id,
            sequence=self._sequence,
            occurred_at=self._clock(),
        )
        for sink in self._sinks:
            try:
                await sink.emit(stamped)
            except Exception as error:
                logger.warning(
                    "event sink failed",
                    extra={
                        "run_id": self._run_id,
                        "sequence": stamped.sequence,
                        "kind": stamped.kind.value,
                        "sink": type(sink).__name__,
                        "error": str(error),
                    },
                )
        return stamped

    async def stage_start(self, stage: StageName) -> PipelineEvent:
        """Emit the start of ``stage``."""
        return await self.emit(PipelineEvent(kind=PipelineEventKind.STAGE_START, stage=stage))

    async def stage_end(
        self, stage: StageName, *, detail: Mapping[str, str] | None = None
    ) -> PipelineEvent:
        """Emit the end of ``stage``."""
        return await self.emit(
            PipelineEvent(kind=PipelineEventKind.STAGE_END, stage=stage, detail=dict(detail or {}))
        )

    async def error(self, stage: StageName | None, message: str) -> PipelineEvent:
        """Emit a failure, naming the stage it came out of."""
        return await self.emit(
            PipelineEvent(kind=PipelineEventKind.ERROR, stage=stage, text=message, failed=True)
        )

    async def result(self, text: str, *, detail: Mapping[str, str] | None = None) -> PipelineEvent:
        """Emit the run's outcome."""
        return await self.emit(
            PipelineEvent(kind=PipelineEventKind.RESULT, text=text, detail=dict(detail or {}))
        )


def silent_stream(run_id: str = "") -> EventStream:
    """Return a stream nobody is listening to.

    The pipeline always holds a stream, so no stage needs a branch for
    "streaming is off" — the events are emitted and go nowhere.
    """
    return EventStream(run_id)


# -- replay -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StageRun:
    """One stage's pass, as the events recorded it."""

    stage: StageName
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failed: bool = False
    detail: Mapping[str, str] = field(default_factory=dict)

    @property
    def completed(self) -> bool:
        """Return whether this stage was seen to finish."""
        return self.ended_at is not None and not self.failed


@dataclass(frozen=True, slots=True)
class ToolCallView:
    """One capability invocation, as the events recorded it."""

    capability: str
    call_id: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    failed: bool = False
    summary: str = ""

    @property
    def completed(self) -> bool:
        """Return whether this call was seen to return."""
        return self.ended_at is not None


@dataclass(frozen=True, slots=True)
class SubAgentView:
    """One specialist dispatch, as the events recorded it."""

    name: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    headline: str = ""


@dataclass(frozen=True, slots=True)
class InvestigationView:
    """The whole investigation, rebuilt from its events and nothing else.

    The completeness property in one type: this is what a console shows, and it is derived from
    the stream rather than from the pipeline's own state. Anything a surface
    displays that is not reachable from here is displayed from a source the
    trace cannot reproduce.
    """

    run_id: str = ""
    stages: tuple[StageRun, ...] = ()
    thoughts: tuple[str, ...] = ()
    tool_calls: tuple[ToolCallView, ...] = ()
    subagents: tuple[SubAgentView, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    approval_requests: tuple[str, ...] = ()
    queued_messages: tuple[str, ...] = ()
    result: str = ""
    errors: tuple[str, ...] = ()

    def stage(self, name: StageName) -> StageRun | None:
        """Return the recorded pass of ``name``, or ``None`` if it never ran."""
        return next((found for found in self.stages if found.stage is name), None)

    @property
    def failed(self) -> bool:
        """Return whether any stage was recorded failing."""
        return bool(self.errors) or any(found.failed for found in self.stages)


def replay(events: Sequence[PipelineEvent]) -> InvestigationView:
    """Return the investigation ``events`` describe.

    Order comes from ``sequence`` rather than from the argument's order, so a
    trace reassembled out of order — several sinks, a store paged back —
    reconstructs the same view.
    """
    ordered = sorted(events, key=lambda event: event.sequence)

    run_id = next((event.run_id for event in ordered if event.run_id), "")
    stages: dict[StageName, StageRun] = {}
    calls: dict[str, ToolCallView] = {}
    subagents: dict[str, SubAgentView] = {}
    thoughts: list[str] = []
    evidence_ids: list[str] = []
    questions: list[str] = []
    approvals: list[str] = []
    queued: list[str] = []
    errors: list[str] = []
    result = ""

    for event in ordered:
        match event.kind:
            case PipelineEventKind.STAGE_START if event.stage is not None:
                stages[event.stage] = StageRun(stage=event.stage, started_at=event.occurred_at)
            case PipelineEventKind.STAGE_END if event.stage is not None:
                current = stages.get(event.stage, StageRun(stage=event.stage))
                stages[event.stage] = replace(
                    current, ended_at=event.occurred_at, detail=dict(event.detail)
                )
            case PipelineEventKind.THOUGHT:
                thoughts.append(event.text)
            case PipelineEventKind.TOOL_START:
                key = event.call_id or f"{event.capability}#{event.sequence}"
                calls[key] = ToolCallView(
                    capability=event.capability,
                    call_id=event.call_id,
                    started_at=event.occurred_at,
                )
            case PipelineEventKind.TOOL_END:
                key = event.call_id or _last_open_call(calls, event.capability)
                current_call = calls.get(key, ToolCallView(capability=event.capability))
                calls[key] = replace(
                    current_call,
                    capability=current_call.capability or event.capability,
                    call_id=current_call.call_id or event.call_id,
                    ended_at=event.occurred_at,
                    failed=event.failed,
                    summary=event.text,
                )
            case PipelineEventKind.SUBAGENT_START:
                subagents[event.subagent] = SubAgentView(
                    name=event.subagent, started_at=event.occurred_at
                )
            case PipelineEventKind.SUBAGENT_END:
                current_agent = subagents.get(event.subagent, SubAgentView(name=event.subagent))
                subagents[event.subagent] = replace(
                    current_agent, ended_at=event.occurred_at, headline=event.text
                )
            case PipelineEventKind.EVIDENCE:
                evidence_ids.append(event.evidence_id)
            case PipelineEventKind.QUESTION:
                questions.append(event.text)
            case PipelineEventKind.APPROVAL_REQUEST:
                approvals.append(event.text)
            case PipelineEventKind.MESSAGE_QUEUED:
                queued.append(event.text)
            case PipelineEventKind.RESULT:
                result = event.text
            case PipelineEventKind.ERROR:
                errors.append(event.text)
                if event.stage is not None:
                    failing = stages.get(event.stage, StageRun(stage=event.stage))
                    stages[event.stage] = replace(failing, failed=True, ended_at=event.occurred_at)
            case _:
                # A stage-scoped event with no stage on it. Recorded as an error
                # rather than dropped: an event nobody can place is a hole in
                # the trace, and a silent hole is the one nobody finds.
                errors.append(f"unplaceable {event.kind.value} event at sequence {event.sequence}")

    return InvestigationView(
        run_id=run_id,
        stages=tuple(stages[name] for name in StageName if name in stages),
        thoughts=tuple(thoughts),
        tool_calls=tuple(calls.values()),
        subagents=tuple(subagents.values()),
        evidence_ids=tuple(evidence_ids),
        questions=tuple(questions),
        approval_requests=tuple(approvals),
        queued_messages=tuple(queued),
        result=result,
        errors=tuple(errors),
    )


def _last_open_call(calls: Mapping[str, ToolCallView], capability: str) -> str:
    """Return the key of the most recent unfinished call to ``capability``.

    A provider that omits call identifiers still produces a matchable stream as
    long as the calls it made are matched newest-first — which is the order a
    loop finishes them in when it made them one at a time.
    """
    for key, call in reversed(list(calls.items())):
        if call.capability == capability and call.ended_at is None:
            return key
    return f"{capability}#end"


__all__ = [
    "EventSink",
    "EventStream",
    "InvestigationView",
    "PipelineEvent",
    "PipelineEventKind",
    "RecordingSink",
    "StageRun",
    "SubAgentView",
    "ToolCallView",
    "replay",
    "silent_stream",
]
