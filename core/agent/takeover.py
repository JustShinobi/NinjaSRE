"""A human taking the investigation over, and giving it back.

Takeover is deliberately not cancellation, and the difference is the whole
reason this module exists. Cancelling and then fixing the problem by hand
produces two records of one incident: a run that stopped saying nothing useful,
and a set of actions in somebody's shell history. Nothing connects them, so the
trace cannot be reviewed, the episode written from it is wrong, and the next
investigation of the same failure recalls an incident that "was cancelled".

So the run is *paused*. It keeps its session, its evidence, and its identity;
the human's actions are recorded against the same run under their own principal;
and resuming puts those actions into the agent's context so it continues from
what actually happened rather than from where it left off.

Three things have to be true at the pause, and each has a failure that is only
visible later:

**It pauses at a safe point.** Tearing down mid-call leaves a tool result that
happened and was never written anywhere, which is the one thing a resumable
session cannot survive. So a takeover is *requested* and the loop honours it
between iterations, exactly as cancellation already does.

**In-flight sub-agents are reaped.** A specialist still running while a human
edits the same deployment is two things changing one system, and the second one
does not know about the first.

**Everything the run was waiting on is closed.** A question left pending is a
button on a surface for a run that a person is now driving by hand, and
answering it would inject guidance into a loop that is not reading any.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.prompts.investigation import HUMAN_ACTIONS_BLOCK
from core.agent.interaction.closure import InteractionClosure
from core.agent.interaction.registry import InteractionRegistry
from core.agent.session import Session, SessionStatus
from core.llm.types import Message, Role
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


class TakeoverState(StrEnum):
    """Where a takeover got to.

    ``PAUSING`` exists as its own state because the gap between "a human asked
    for control" and "the loop stopped and the sub-agents are reaped" is real
    and can be seconds long. A surface that showed ``HUMAN_CONTROL`` during it
    would be telling somebody it is safe to start changing things while a
    specialist is still running.
    """

    AGENT_RUNNING = "agent_running"
    PAUSING = "pausing"
    HUMAN_CONTROL = "human_control"
    RESUMED = "resumed"
    CONCLUDED = "concluded"

    @property
    def is_human_controlled(self) -> bool:
        """Return whether a person, rather than the agent, is driving."""
        return self in {TakeoverState.PAUSING, TakeoverState.HUMAN_CONTROL}


@dataclass(frozen=True, slots=True)
class HumanAction:
    """One thing a person did during their interval, recorded in the run's trace.

    ``principal`` is required and not defaulted. The reason the trace stays one
    record across a takeover is that every entry in it says who did it, and an
    action attributed to nobody makes the whole interval unreviewable — which is
    the failure this module exists to prevent, arrived at from the other side.
    """

    principal: str
    action: str
    at: datetime
    detail: str = ""
    outcome: str = ""

    def __post_init__(self) -> None:
        if not self.principal:
            raise ValueError("a human action has to say who took it")
        if not self.action.strip():
            raise ValueError("a human action has to say what was done")

    def describe(self) -> str:
        """Return the one line the resumed agent reads."""
        parts = [f"{self.principal}: {self.action}"]
        if self.detail:
            parts.append(f"({self.detail})")
        if self.outcome:
            parts.append(f"→ {self.outcome}")
        return " ".join(parts)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this action."""
        return {
            "principal": self.principal,
            "action": self.action,
            "at": self.at.isoformat(),
            "detail": self.detail,
            "outcome": self.outcome,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> HumanAction:
        """Return the action a stored record describes."""
        return cls(
            principal=str(record["principal"]),
            action=str(record["action"]),
            at=datetime.fromisoformat(str(record["at"])),
            detail=str(record.get("detail", "")),
            outcome=str(record.get("outcome", "")),
        )


@runtime_checkable
class SubAgentReaper(Protocol):
    """Whatever can stop the specialists a run has in flight.

    A port because the runtime that dispatched them is the only thing that can
    stop them, and the takeover path must work against any runtime — including
    one whose sub-agents are processes rather than coroutines.
    """

    async def reap(self, session_id: str) -> tuple[str, ...]:
        """Stop this run's in-flight sub-agents and return which were stopped."""


def _no_children(session_id: str) -> Sequence[str]:
    """Return nothing: the default for a runtime that dispatches no specialists."""
    del session_id
    return ()


@dataclass(slots=True)
class LoopReaper:
    """Reaps sub-agents by cancelling them through the runtime that spawned them.

    Sub-agent sessions are named after their parent, which is what makes them
    findable without the runtime keeping a second registry of children. That
    naming is a property of the loop rather than a coincidence, and this is the
    one place outside it that depends on it — stated here so a change to the
    convention has somewhere to look.
    """

    cancel: Callable[[str], Any]
    children: Callable[[str], Sequence[str]] = _no_children

    async def reap(self, session_id: str) -> tuple[str, ...]:
        """Cancel every child of ``session_id`` and return the ones cancelled."""
        reaped: list[str] = []
        for child in self.children(session_id):
            outcome = self.cancel(child)
            if hasattr(outcome, "__await__"):
                await outcome
            reaped.append(child)
        return tuple(reaped)


@dataclass(frozen=True, slots=True)
class TakeoverRecord:
    """One human-controlled interval, from the pause to the resume."""

    takeover_id: str
    run_id: str
    principal: str
    started_at: datetime
    state: TakeoverState = TakeoverState.HUMAN_CONTROL
    reason: str = ""
    ended_at: datetime | None = None
    actions: tuple[HumanAction, ...] = ()
    reaped_subagents: tuple[str, ...] = ()
    closed_interactions: tuple[str, ...] = ()

    @property
    def is_open(self) -> bool:
        """Return whether a person is still driving."""
        return self.ended_at is None

    def duration(self, now: datetime) -> float:
        """Return how long this interval has lasted, in seconds."""
        return ((self.ended_at or now) - self.started_at).total_seconds()

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this interval."""
        return {
            "takeover_id": self.takeover_id,
            "run_id": self.run_id,
            "principal": self.principal,
            "started_at": self.started_at.isoformat(),
            "state": self.state.value,
            "reason": self.reason,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "actions": [action.to_record() for action in self.actions],
            "reaped_subagents": list(self.reaped_subagents),
            "closed_interactions": list(self.closed_interactions),
        }


class NotUnderTakeover(RuntimeError):
    """An operation that only makes sense while a person is driving.

    Recording an action against a run nobody took over would put it in the
    trace with no interval around it, and a reviewer reading that trace would
    see an action nobody authorised — which is indistinguishable from the thing
    the whole approval mechanism exists to prevent.
    """


@dataclass(slots=True)
class Takeover:
    """Pauses one run for a person, records what they do, and hands it back.

    Holds the session rather than a copy of its state, so an action recorded
    here is in the same object the runtime resumes — which is what makes the
    trace one record rather than two that have to be stitched together
    afterwards.
    """

    session: Session
    reaper: SubAgentReaper | None = None
    interactions: InteractionRegistry | None = None
    closure: InteractionClosure | None = None
    clock: Callable[[], datetime] = _utc_now
    identifiers: Callable[[], str] = lambda: uuid.uuid4().hex[:16]
    _record: TakeoverRecord | None = field(default=None, repr=False)

    # -- reading --------------------------------------------------------------

    @property
    def state(self) -> TakeoverState:
        """Return who is driving this run."""
        if self._record is None:
            return TakeoverState.AGENT_RUNNING
        return self._record.state

    @property
    def record(self) -> TakeoverRecord | None:
        """Return the current interval, or ``None`` when the agent is driving."""
        return self._record

    @property
    def actions(self) -> tuple[HumanAction, ...]:
        """Return what the person has done so far."""
        return self._record.actions if self._record is not None else ()

    # -- pausing --------------------------------------------------------------

    async def take_over(self, *, principal: str, reason: str = "") -> TakeoverRecord:
        """Pause the run for ``principal`` and return the interval that opens.

        The order is the safety property. Sub-agents are reaped before the
        session is marked suspended, so there is no window in which a surface
        says a person is in control while a specialist is still changing things.
        """
        if not principal:
            raise ValueError("a takeover has to say who is taking over")
        if self._record is not None and self._record.is_open:
            raise NotUnderTakeover(
                f"{self.session.id} is already under takeover by {self._record.principal}"
            )

        started = self.clock()
        self._record = TakeoverRecord(
            takeover_id=self.identifiers(),
            run_id=self.session.id,
            principal=principal,
            started_at=started,
            state=TakeoverState.PAUSING,
            reason=reason,
        )

        reaped = await self._reap()
        closed = await self._close_interactions()

        self.session.status = SessionStatus.SUSPENDED
        self.session.touch()
        self._record = _replace(
            self._record,
            state=TakeoverState.HUMAN_CONTROL,
            reaped_subagents=reaped,
            closed_interactions=closed,
        )
        logger.info(
            "agent.takeover_started",
            run_id=self.session.id,
            principal=principal,
            reason=reason,
            reaped=list(reaped),
            closed_interactions=list(closed),
        )
        return self._record

    async def _reap(self) -> tuple[str, ...]:
        """Stop the run's in-flight specialists, and say so if that fails.

        A reaper that raised must not leave the takeover half done. The failure
        is recorded and the pause proceeds, because a person who asked for
        control and did not get it is worse off than one who got it and is told
        a specialist may still be running.
        """
        if self.reaper is None:
            return ()
        try:
            return await self.reaper.reap(self.session.id)
        except Exception as failure:  # noqa: BLE001 — a failed reap must not block the pause
            logger.error(
                "agent.subagent_reaping_failed",
                run_id=self.session.id,
                error=str(failure),
            )
            return ()

    async def _close_interactions(self) -> tuple[str, ...]:
        """Close everything the run was waiting on, and tell every surface."""
        if self.interactions is None:
            return ()
        superseded = self.interactions.supersede_open(reason="a person took the investigation over")
        if superseded and self.closure is not None:
            await self.closure.publish_all(superseded, at=self.clock())
        return tuple(closed.interaction_id for closed in superseded)

    # -- the human interval ---------------------------------------------------

    def record_action(
        self, *, action: str, principal: str = "", detail: str = "", outcome: str = ""
    ) -> HumanAction:
        """Record one thing the person did, in this run's own trace (FR-012).

        ``principal`` defaults to whoever opened the takeover rather than to
        nobody. An action recorded without one is unattributable, and the whole
        claim of keeping one trace is that every entry in it says who.
        """
        held = self._require_open()
        recorded = HumanAction(
            principal=principal or held.principal,
            action=action,
            at=self.clock(),
            detail=detail,
            outcome=outcome,
        )
        self._record = _replace(held, actions=(*held.actions, recorded))
        self.session.touch()
        logger.info(
            "agent.human_action_recorded",
            run_id=self.session.id,
            principal=recorded.principal,
            action=action,
        )
        return recorded

    # -- handing it back ------------------------------------------------------

    def resume(self) -> TakeoverRecord:
        """End the interval, put what happened into context, and return the run.

        The actions go into the transcript as a user message rather than into
        the evidence. They are not observations the system made — they are
        things a person did, and presenting them as evidence would let the model
        cite "the checkout deployment was restarted" as something it established.
        """
        held = self._require_open()
        ended = self.clock()
        self._record = _replace(held, state=TakeoverState.RESUMED, ended_at=ended)

        if held.actions:
            self.session.append(
                Message(role=Role.USER, text=human_actions_block(held.actions, held.principal))
            )
        self.session.status = SessionStatus.RUNNING
        self.session.touch()
        logger.info(
            "agent.takeover_resumed",
            run_id=self.session.id,
            principal=held.principal,
            actions=len(held.actions),
            seconds=held.duration(ended),
        )
        return self._record

    def conclude(self, *, answer: str = "") -> TakeoverRecord:
        """End the investigation by hand, and record that a person did (FR-011).

        The run is ``COMPLETED`` rather than ``CANCELLED``: somebody handled the
        incident, which is a conclusion. Cancelled would tell the episode writer
        that nothing was learned here, and the actions above it are exactly what
        was learned.
        """
        held = self._require_open()
        ended = self.clock()
        self._record = _replace(held, state=TakeoverState.CONCLUDED, ended_at=ended)

        if held.actions:
            self.session.append(
                Message(role=Role.USER, text=human_actions_block(held.actions, held.principal))
            )
        if answer:
            self.session.append(Message(role=Role.ASSISTANT, text=answer))
        self.session.status = SessionStatus.COMPLETED
        self.session.touch()
        logger.info(
            "agent.takeover_concluded",
            run_id=self.session.id,
            principal=held.principal,
            actions=len(held.actions),
        )
        return self._record

    def _require_open(self) -> TakeoverRecord:
        """Return the open interval, or raise saying there is not one."""
        held = self._record
        if held is None or not held.is_open:
            raise NotUnderTakeover(
                f"{self.session.id} is not under takeover, so there is no interval to record "
                f"against. Take the run over first."
            )
        return held


def human_actions_block(actions: Sequence[HumanAction], principal: str) -> str:
    """Return what the resumed agent reads about the interval it slept through."""
    items = "\n".join(
        f"{index}. {action.describe()}" for index, action in enumerate(actions, start=1)
    )
    return HUMAN_ACTIONS_BLOCK.format(principal=principal, items=items)


def _replace(record: TakeoverRecord, **changes: Any) -> TakeoverRecord:
    """Return ``record`` with ``changes`` applied."""
    return replace(record, **changes)


__all__ = [
    "HumanAction",
    "LoopReaper",
    "NotUnderTakeover",
    "SubAgentReaper",
    "Takeover",
    "TakeoverRecord",
    "TakeoverState",
    "human_actions_block",
]
