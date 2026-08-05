"""The runtime contract, and the one property that keeps it honest.

Article V allows alternative runtimes to exist and allows exactly one of them
to produce a published number. ``is_canonical`` is where that distinction is
written down, so the guard in front of the evaluation suite reads a declared
property rather than matching class names — a check that would pass the day
somebody wrapped the adapter in a subclass.

The port is structural. An adapter never subclasses anything here; it satisfies
``Runtime`` by having the methods, which is what lets a first-party loop, a
vendor SDK adapter, and a replay harness all be runtimes without sharing an
ancestor.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from config.constants.investigation import MAX_INVESTIGATION_LOOPS, RUN_WALL_CLOCK_SECONDS
from core.agent.session import EvidenceEntry, Session
from core.agent.turn import HookFailure, Turn
from core.llm.usage import TokenCounts


class RunStatus(StrEnum):
    """How a run ended.

    ``PARTIAL`` is the degraded outcome an LLM failure produces: the evidence
    gathered so far is intact and the answer is whatever could be said from it.
    It is distinct from ``FAILED``, which means nothing usable came back.
    """

    COMPLETED = "completed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SeedCall:
    """A deterministic call made before the model's first turn."""

    capability: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunRequest:
    """One investigation, as the caller states it.

    ``max_iterations`` and ``wall_clock_seconds`` may only be lowered.
    Article II's constants are ceilings rather than defaults: a caller that
    knows this run is cheap may ask for less, and one that would like more is
    asking for the bound to not be a bound.
    """

    objective: str
    alert_source: str = ""
    session_id: str = ""
    system_prompt: str = ""
    context: Mapping[str, str] = field(default_factory=dict)
    seed_calls: Sequence[SeedCall] = ()
    max_iterations: int = MAX_INVESTIGATION_LOOPS
    wall_clock_seconds: float = RUN_WALL_CLOCK_SECONDS
    context_budget_tokens: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.max_iterations <= MAX_INVESTIGATION_LOOPS:
            raise ValueError(
                f"max_iterations must be between 1 and {MAX_INVESTIGATION_LOOPS}, "
                f"got {self.max_iterations}"
            )
        if not 0 < self.wall_clock_seconds <= RUN_WALL_CLOCK_SECONDS:
            raise ValueError(
                f"wall_clock_seconds must be above 0 and at most {RUN_WALL_CLOCK_SECONDS}, "
                f"got {self.wall_clock_seconds}"
            )
        if self.context_budget_tokens < 0:
            raise ValueError("context_budget_tokens must not be negative")


@dataclass(frozen=True, slots=True)
class RunResult:
    """What one run produced, and the session it produced it in.

    The session travels with the result rather than being copied out of it.
    Two records of the same evidence are two chances for a report and a trace
    to disagree, and the resumption path needs the session object anyway.
    """

    session: Session
    status: RunStatus
    answer: str = ""
    failure: str = ""
    # Run-level hook failures. Turn-level ones are on the turn they happened
    # during; ``on_run_start``, ``on_run_end``, and ``on_cancel`` have no turn
    # to attach to, and a hook that broke without leaving a record is a hook
    # nobody will fix.
    hook_failures: tuple[HookFailure, ...] = ()

    @property
    def degraded(self) -> bool:
        """Return whether the answer was produced from an incomplete run."""
        return self.status is RunStatus.PARTIAL

    @property
    def evidence(self) -> tuple[EvidenceEntry, ...]:
        """Return the evidence the run gathered."""
        return tuple(self.session.evidence)

    @property
    def turns(self) -> tuple[Turn, ...]:
        """Return every recorded turn, in order."""
        return tuple(self.session.turns)

    @property
    def iterations(self) -> int:
        """Return how many iterations the loop used."""
        return self.session.iteration

    @property
    def tokens(self) -> TokenCounts:
        """Return the token total across the run."""
        return self.session.usage.tokens


@runtime_checkable
class Runtime(Protocol):
    """What every runtime implements, canonical or not."""

    @property
    def name(self) -> str:
        """Return the identifier this runtime is recorded under."""

    @property
    def is_canonical(self) -> bool:
        """Return whether results from this runtime may be published.

        Exactly one implementation answers ``True``. Everything else is
        experimental by construction, and the benchmark guard reads this.
        """

    async def run(self, request: RunRequest) -> RunResult:
        """Return the outcome of one investigation, degraded rather than raised."""

    async def resume(self, session: Session) -> RunResult:
        """Return the outcome of continuing ``session`` from where it stopped."""

    async def cancel(self, session_id: str) -> None:
        """Ask the run identified by ``session_id`` to stop at its next safe point."""


__all__ = [
    "RunRequest",
    "RunResult",
    "RunStatus",
    "Runtime",
    "SeedCall",
]
