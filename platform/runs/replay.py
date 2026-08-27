"""Reconstructing what a client saw, from what was written down.

The success criterion this module exists for is a comparison: the view a live
client observed and the view a replay produces are asserted equal. That makes
one design decision for us — **replay reads the same event log the live stream
delivered from**, rather than re-deriving an ordering from four tables of
records whose timestamps routinely collide. The stored records supply the
detail; the log supplies the order, and the order is the part a reconstruction
gets wrong.

The other decision is what to do about a capability that no longer exists. A
replay is read months later, catalogues change, and a reconstruction that
refused to render a call to a since-removed tool would fail on exactly the runs
worth reviewing. So a call carries what it needs to be rendered — its name, its
arguments, its result, its outcome — and the live catalogue is consulted only to
*enrich*. A missing entry marks the call as unavailable and changes nothing
else.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.runs import (
    MAX_REPLAY_RESULT_BYTES,
    MAX_REPLAY_RESULT_ITEMS,
    MAX_REPLAY_RESULT_STRING_LENGTH,
    STAGE_DETAIL_COMPLETION_TOKENS,
    STAGE_DETAIL_FINDING,
    STAGE_DETAIL_LLM_CALLS,
    STAGE_DETAIL_PROMPT_TOKENS,
    STAGE_EVENT_DURATION_MS,
    STAGE_EVENT_FAILED,
    STAGE_EVENT_NAME,
    TRUNCATION_MARKER_KEY,
    TURN_PAYLOAD_CAPABILITIES,
    TURN_PAYLOAD_MODEL_RATIONALE,
    TURN_PAYLOAD_RATIONALE,
    TURN_PAYLOAD_STAGE,
    TURN_USAGE_COMPLETION_TOKENS,
    TURN_USAGE_COST,
    TURN_USAGE_DURATION_MS,
    TURN_USAGE_MODEL,
    TURN_USAGE_PROMPT_TOKENS,
)
from core.state.types import STAGE_ORDER, StageName
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    RunStatus,
    RunTrace,
    RunTraceStore,
    ToolCallRecord,
    ToolCallStatus,
    TraceEventRecord,
)
from platform.runs.events import RunEvent, TraceEventKind
from platform.runs.truncation import Bounds, truncate

#: What a reader gets of a result, as against what the recorder stored of it.
#: Tighter on every axis, because the two are bounding different things: the
#: recorder bounds one row, and a replay hands over every call of a run at once.
REPLAY_RESULT_BOUNDS: Final = Bounds(
    payload_bytes=MAX_REPLAY_RESULT_BYTES,
    string_length=MAX_REPLAY_RESULT_STRING_LENGTH,
    sequence_items=MAX_REPLAY_RESULT_ITEMS,
)

#: Argument keys tried, in order, for "the resource one call touched" — tool
#: schemas across the capability catalogue do not share one name for it, so
#: every key a call's own arguments might carry is tried.
_RESOURCE_ARGUMENT_KEYS: tuple[str, ...] = (
    "resource_id",
    "resource",
    "instance",
    "node",
    "host",
    "pod",
    "vmid",
    "vm_id",
)


@runtime_checkable
class CapabilityDescriptions(Protocol):
    """What the live catalogue can tell a replay about a capability.

    A protocol rather than an import, because the catalogue is tier 2 and this
    is tier 3. A replay with no describer renders every call from what was
    recorded, which is the behaviour the removed-capability case needs anyway —
    so the enrichment is genuinely optional rather than a dependency dressed as
    one.
    """

    def describe(self, name: str) -> str | None:
        """Return the current description of ``name``, or ``None`` if it is gone."""


@dataclass(frozen=True, slots=True)
class ReplayedCall:
    """One capability invocation, as a reviewer reads it back."""

    call_id: str
    turn_id: str
    name: str
    status: ToolCallStatus
    arguments: Mapping[str, Any] = field(default_factory=dict)
    result: Mapping[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    error: str | None = None
    error_class: str | None = None
    evidence_ids: tuple[str, ...] = ()
    description: str | None = None
    available: bool = True
    #: Whether the recorder cut anything out of this call's stored body on the
    #: way in. Read from the marker the recorder writes beside the payload, not
    #: from inside ``result`` — an oversized result is shed *wholesale*, so the
    #: only surviving evidence that it was ever there is that sibling marker,
    #: and a replay that looked for it inside the result would find an empty
    #: mapping and report a call that returned nothing.
    result_truncated: bool = False

    @property
    def degraded(self) -> bool:
        """Return whether this call names a capability the catalogue has lost.

        Not a failure of the replay. The call happened, its arguments and its
        result are recorded, and the only thing missing is a description the
        catalogue would have supplied — which is what "degrading to recorded
        metadata" means.
        """
        return not self.available


@dataclass(frozen=True, slots=True)
class ReplayedTurn:
    """One iteration of the loop, as a reviewer reads it back."""

    turn_id: str
    index: int
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: ``None`` when no price was recorded for this turn — a provider with no
    #: published price, never a fabricated ``0.0``.
    cost: float | None = None
    duration_ms: int = 0
    selection_rationale: str = ""
    #: What the model said on this turn. Empty for a turn that emitted only
    #: tool calls, which is a real answer — the agent said nothing — and not
    #: the same as a turn whose words were never written down.
    model_rationale: str = ""
    offered_capabilities: tuple[str, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    calls: tuple[ReplayedCall, ...] = ()
    #: Which of the six stages this turn ran inside. ``None`` for a turn the
    #: recorder wrote with no stage open — a sub-agent's own loop, a bare
    #: runtime, or any run recorded before stages reached the trace.
    stage: StageName | None = None

    @property
    def is_priced(self) -> bool:
        """Return whether this turn carries a recorded cost."""
        return self.cost is not None


@dataclass(frozen=True, slots=True)
class ReplayedStage:
    """One of the six stages, as a reviewer reads it back.

    ``turns`` is the turns that ran inside it, which for five of the six is
    empty and stays empty. Only the gathering stage drives the loop; intake and
    diagnosis each make a model call of their own and hand back a value, and
    resolving and planning make none at all. ``llm_calls`` is what tells the
    two apart, and it is the reason this type exists rather than a grouping of
    the turn list: a stage that made a model call and produced no turn is
    invisible to any view assembled from turns.
    """

    stage: StageName
    finding: str = ""
    duration_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    failed: bool = False
    occurred_at: datetime | None = None
    turns: tuple[ReplayedTurn, ...] = ()

    @property
    def tokens(self) -> int:
        """Return what this stage spent, prompt and completion together."""
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class ReplayedRun:
    """A whole investigation, reconstructed.

    ``events`` is the ordering the live client saw, and it is carried rather
    than folded into the turns because that is what a completeness comparison
    is made against. The turns are the same facts arranged for a reader.
    """

    run: AgentRun
    turns: tuple[ReplayedTurn, ...] = ()
    #: The stages that finished, in pipeline order. Empty for a run driven
    #: without a pipeline, and for every run recorded before stages reached the
    #: trace — which is what ``total_tokens`` below reads to decide whether it
    #: can state a total or only a floor.
    stages: tuple[ReplayedStage, ...] = ()
    events: tuple[RunEvent, ...] = ()
    evidence_ids: tuple[str, ...] = ()

    @property
    def total_cost(self) -> float:
        """Return what the priced turns of this run cost, added up.

        Read this with ``unpriced_turn_count``. On its own it is a floor, not
        a total — an unpriced provider must never look free by omission.
        """
        return sum(turn.cost for turn in self.turns if turn.cost is not None)

    @property
    def unpriced_turn_count(self) -> int:
        """Return how many turns carried no recorded cost."""
        return sum(1 for turn in self.turns if turn.cost is None)

    @property
    def turn_tokens(self) -> int:
        """Return prompt and completion tokens across the recorded turns.

        The loop's spend and nothing else, which for a pipelined run is the
        gathering stage's alone.
        """
        return sum(turn.prompt_tokens + turn.completion_tokens for turn in self.turns)

    @property
    def total_tokens(self) -> int:
        """Return what the whole run spent, every model call included.

        Summed over the stages when the run recorded any, because only the
        gathering stage produces turns: intake classifies and diagnosis
        structures, each on a model call of its own, and a total summed over
        the turn records leaves both of them out. That is not a rounding error
        — it is the second and fifth of six stages missing from the number an
        operator uses to decide whether this is affordable to run on every
        alert.

        Falls back to the turns for a run with no stages recorded, which is
        every run written before stages reached the trace and every loop driven
        without a pipeline. The number is a floor there, and the empty stage
        list is what says so.
        """
        if not self.stages:
            return self.turn_tokens
        return sum(stage.tokens for stage in self.stages)

    @property
    def degraded_calls(self) -> tuple[ReplayedCall, ...]:
        """Return the calls whose capability the catalogue no longer knows."""
        return tuple(call for turn in self.turns for call in turn.calls if call.degraded)

    @property
    def is_interrupted(self) -> bool:
        """Return whether this run stopped without anybody concluding anything."""
        return self.run.status is RunStatus.INTERRUPTED


async def replay_run(
    store: RunTraceStore,
    run_id: str,
    *,
    catalogue: CapabilityDescriptions | None = None,
) -> ReplayedRun:
    """Return ``run_id`` reconstructed, raising if the run does not exist."""
    return replay_trace(await store.replay(run_id), catalogue=catalogue)


def replay_trace(
    trace: RunTrace,
    *,
    catalogue: CapabilityDescriptions | None = None,
) -> ReplayedRun:
    """Return the client view ``trace`` describes.

    Pure, so the comparison against a live-observed view is a comparison of two
    values rather than of two sequences of database reads.
    """
    calls_by_turn: dict[str, list[ReplayedCall]] = {}
    for record in trace.tool_calls:
        arguments = dict(record.arguments)
        call = ReplayedCall(
            call_id=record.call_id,
            turn_id=record.turn_id,
            name=record.tool_name,
            status=record.status,
            arguments=_section(arguments, "arguments"),
            result=_section(arguments, "result"),
            duration_ms=int(arguments.get("duration_ms", 0) or 0),
            error=record.error,
            error_class=_optional_str(arguments.get("error_class")),
            evidence_ids=record.evidence_ids,
            result_truncated=TRUNCATION_MARKER_KEY in arguments,
            **_availability(record.tool_name, catalogue),
        )
        calls_by_turn.setdefault(record.turn_id, []).append(call)

    turns = tuple(
        ReplayedTurn(
            turn_id=record.turn_id,
            index=record.index,
            model=str(record.usage.get(TURN_USAGE_MODEL, "")),
            prompt_tokens=int(record.usage.get(TURN_USAGE_PROMPT_TOKENS, 0) or 0),
            completion_tokens=int(record.usage.get(TURN_USAGE_COMPLETION_TOKENS, 0) or 0),
            cost=_optional_cost(record.usage.get(TURN_USAGE_COST)),
            duration_ms=int(record.usage.get(TURN_USAGE_DURATION_MS, 0) or 0),
            selection_rationale=str(record.payload.get(TURN_PAYLOAD_RATIONALE, "")),
            model_rationale=str(record.payload.get(TURN_PAYLOAD_MODEL_RATIONALE, "")),
            offered_capabilities=_names(record.payload.get(TURN_PAYLOAD_CAPABILITIES)),
            started_at=record.started_at,
            finished_at=record.finished_at,
            calls=tuple(calls_by_turn.get(record.turn_id, ())),
            stage=_stage_named(record.payload.get(TURN_PAYLOAD_STAGE)),
        )
        for record in trace.turns
    )

    return ReplayedRun(
        run=trace.run,
        turns=turns,
        stages=_stages_of(trace.events, turns),
        events=tuple(RunEvent.of(record) for record in trace.events),
        evidence_ids=tuple(item.evidence_id for item in trace.evidence),
    )


def _stages_of(
    events: Sequence[TraceEventRecord], turns: Sequence[ReplayedTurn]
) -> tuple[ReplayedStage, ...]:
    """Return the stages ``events`` recorded, in pipeline order, holding their turns.

    Ordered by ``STAGE_ORDER`` rather than by the order the events came back.
    The pipeline's order is a property of the pipeline; a log paged back out of
    sequence, or a stage written by a replica whose clock disagreed, must not
    reorder the account of a run.

    A turn is placed by the stage it recorded for itself, never by falling
    between two stage boundaries. A turn with no stage on it — a run recorded
    before this, a loop driven without a pipeline — belongs to no stage and
    stays where it always was, in ``ReplayedRun.turns``.
    """
    recorded: dict[StageName, ReplayedStage] = {}
    turns_by_stage: dict[StageName, list[ReplayedTurn]] = {}
    for turn in turns:
        if turn.stage is not None:
            turns_by_stage.setdefault(turn.stage, []).append(turn)

    for event in events:
        if event.kind != TraceEventKind.STAGE_COMPLETED.value:
            continue
        named = _stage_named(event.payload.get(STAGE_EVENT_NAME))
        if named is None:
            continue
        recorded[named] = ReplayedStage(
            stage=named,
            finding=str(event.payload.get(STAGE_DETAIL_FINDING, "")),
            duration_ms=int(event.payload.get(STAGE_EVENT_DURATION_MS, 0) or 0),
            prompt_tokens=int(event.payload.get(STAGE_DETAIL_PROMPT_TOKENS, 0) or 0),
            completion_tokens=int(event.payload.get(STAGE_DETAIL_COMPLETION_TOKENS, 0) or 0),
            llm_calls=int(event.payload.get(STAGE_DETAIL_LLM_CALLS, 0) or 0),
            failed=bool(event.payload.get(STAGE_EVENT_FAILED, False)),
            occurred_at=event.occurred_at,
            turns=tuple(turns_by_stage.get(named, ())),
        )

    return tuple(recorded[name] for name in STAGE_ORDER if name in recorded)


def _stage_named(value: Any) -> StageName | None:
    """Return the stage ``value`` names, or ``None`` when it names none.

    A name outside the six is dropped rather than raised on. A trace written by
    a newer version of the pipeline is still a trace worth reading, and the
    stage it holds that this code cannot place is one section missing rather
    than a run nobody can open.
    """
    if not value:
        return None
    try:
        return StageName(str(value))
    except ValueError:
        return None


def bounded_result(call: ReplayedCall) -> tuple[dict[str, Any], bool]:
    """Return what a reader is served of ``call``'s result, and whether it is short.

    A projection rather than the recorded body. The recorder's ceiling is per
    stored row, and a replay hands over every call of a run in one response, so
    serving each result at the storage bound turns a forty-call run into a
    multi-megabyte page. A reader wants enough to say what the call found — the
    statement, the fields, the handful of rows — and the raw vendor body it
    found them in stays in the trace, reachable per call, rather than riding
    along on the summary.

    The reduction is the recorder's own under tighter bounds, so a result cut
    on the way out carries exactly the marker a result cut on the way in
    carries, and a reader has one thing to look for rather than two.

    The flag is true when *either* side cut something. A body the recorder had
    already shortened is still a short body, and reporting "not truncated"
    because this projection happened to remove nothing would launder that into
    a result which looks complete.
    """
    served, removal = truncate(call.result, bounds=REPLAY_RESULT_BOUNDS)
    return served, removal.happened or call.result_truncated


def _availability(name: str, catalogue: CapabilityDescriptions | None) -> dict[str, Any]:
    """Return what the live catalogue adds to a recorded call, if anything."""
    if catalogue is None:
        return {"description": None, "available": True}
    description = catalogue.describe(name)
    return {"description": description, "available": description is not None}


def _section(arguments: Mapping[str, Any], key: str) -> dict[str, Any]:
    """Return one sub-mapping of a stored call body, or an empty one.

    A body written by an older recorder may not have the section at all, and a
    replay that raised on it would fail on exactly the old runs somebody kept
    for a reason.
    """
    value = arguments.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _names(value: Any) -> tuple[str, ...]:
    """Return a recorded list of capability names as a tuple of strings."""
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    return ()


def _optional_cost(value: Any) -> float | None:
    """Return a turn's recorded cost, or ``None`` when the key was never written.

    The key is absent, not ``0.0``, for a turn the recorder could not price —
    coercing a missing key to zero here would be the exact fabrication the
    write side refuses to produce.
    """
    return None if value is None else float(value)


def touched_resources_of(calls: Sequence[ToolCallRecord]) -> tuple[str, ...]:
    """Return the resources ``calls`` named, derived from what was recorded.

    Never from the alert's declared subjects — only from the
    arguments a call was actually made with, read the same way ``replay_trace``
    already unwraps them. A capability whose schema uses a name outside
    ``_RESOURCE_ARGUMENT_KEYS`` contributes nothing; the list is a known,
    declared heuristic over the catalogue's common argument names, not a
    schema-aware reading of every capability's contract.
    """
    found: list[str] = []
    seen: set[str] = set()
    for record in calls:
        arguments = _section(dict(record.arguments), "arguments")
        for key in _RESOURCE_ARGUMENT_KEYS:
            value = arguments.get(key)
            if isinstance(value, str) and value and value not in seen:
                seen.add(value)
                found.append(value)
    return tuple(found)


def _optional_str(value: Any) -> str | None:
    """Return ``value`` as a string, or ``None`` when it was not recorded."""
    return None if value is None else str(value)


__all__ = [
    "REPLAY_RESULT_BOUNDS",
    "CapabilityDescriptions",
    "ReplayedCall",
    "ReplayedRun",
    "ReplayedStage",
    "ReplayedTurn",
    "bounded_result",
    "replay_run",
    "replay_trace",
    "touched_resources_of",
]
