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
from typing import Any, Protocol, runtime_checkable

from config.constants.runs import (
    TURN_PAYLOAD_CAPABILITIES,
    TURN_PAYLOAD_MODEL_RATIONALE,
    TURN_PAYLOAD_RATIONALE,
    TURN_USAGE_COMPLETION_TOKENS,
    TURN_USAGE_COST,
    TURN_USAGE_DURATION_MS,
    TURN_USAGE_MODEL,
    TURN_USAGE_PROMPT_TOKENS,
)
from platform.persistence.ports.run_trace_store import (
    AgentRun,
    RunStatus,
    RunTrace,
    RunTraceStore,
    ToolCallRecord,
    ToolCallStatus,
)
from platform.runs.events import RunEvent

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

    @property
    def is_priced(self) -> bool:
        """Return whether this turn carries a recorded cost."""
        return self.cost is not None


@dataclass(frozen=True, slots=True)
class ReplayedRun:
    """A whole investigation, reconstructed.

    ``events`` is the ordering the live client saw, and it is carried rather
    than folded into the turns because that is what a completeness comparison
    is made against. The turns are the same facts arranged for a reader.
    """

    run: AgentRun
    turns: tuple[ReplayedTurn, ...] = ()
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
    def total_tokens(self) -> int:
        """Return prompt and completion tokens across every turn."""
        return sum(turn.prompt_tokens + turn.completion_tokens for turn in self.turns)

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
        )
        for record in trace.turns
    )

    return ReplayedRun(
        run=trace.run,
        turns=turns,
        events=tuple(RunEvent.of(record) for record in trace.events),
        evidence_ids=tuple(item.evidence_id for item in trace.evidence),
    )


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
    "CapabilityDescriptions",
    "ReplayedCall",
    "ReplayedRun",
    "ReplayedTurn",
    "replay_run",
    "replay_trace",
    "touched_resources_of",
]
