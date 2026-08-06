"""Saying "still working" often enough to be useful and rarely enough to be read.

An investigation that runs for twenty minutes with nothing on the channel is
indistinguishable, to the person who raised the alert, from one that is wedged.
They will either open the console or start investigating in parallel, and the
second is how two people make conflicting changes to the same cluster.

The interval decides when a run is long enough to be worth a word. The cooldown
decides how often that word comes, and it is the half that matters: a run long
enough to need progress reporting is a run long enough to teach everybody to
mute the channel, and a notifier without a cooldown is a notifier that gets
muted before the notification that mattered.

**A run waiting on a human is exempt.** Somebody has already been asked to do
something, on a surface that is already showing it; telling them again that the
run is still going is telling them what their own unanswered question already
says. The attention state is what makes that decidable rather than a guess.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.investigation import (
    PROGRESS_NOTIFICATION_COOLDOWN_SECONDS,
    PROGRESS_NOTIFICATION_INTERVAL_SECONDS,
)
from core.agent.interaction.attention import Attention
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProgressReport:
    """What somebody waiting on a long run is told.

    Deliberately shallow. What the agent currently believes is a half-finished
    hypothesis, and putting one in a channel during an incident is how a wrong
    guess becomes the thing everybody starts working from. Elapsed time,
    iteration count, and what it is doing are facts.
    """

    run_id: str
    objective: str = ""
    elapsed_seconds: float = 0.0
    iterations: int = 0
    evidence_count: int = 0
    activity: str = ""

    def describe(self) -> str:
        """Return the one line a sink shows."""
        minutes = self.elapsed_seconds / 60.0
        return (
            f"Still investigating {self.objective or self.run_id}: {minutes:.0f} minute(s) in, "
            f"{self.iterations} step(s), {self.evidence_count} piece(s) of evidence gathered."
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form a transport serialises."""
        return {
            "run_id": self.run_id,
            "objective": self.objective,
            "elapsed_seconds": self.elapsed_seconds,
            "iterations": self.iterations,
            "evidence_count": self.evidence_count,
            "activity": self.activity,
        }


@runtime_checkable
class ProgressSink(Protocol):
    """Somewhere a progress report is delivered.

    A port rather than a transport. Delivering to a chat thread, a webhook, or a
    console stream is feature 023's job; the runtime needs only "tell whoever is
    waiting", and a sink here that knew about Slack would be this tier reaching
    up into one above it.
    """

    @property
    def name(self) -> str:
        """Return what this sink is called, for the log line when it fails."""

    async def deliver(self, report: ProgressReport) -> None:
        """Tell this sink's audience that the run is still going."""


@dataclass(frozen=True, slots=True)
class ProgressOutcome:
    """Whether a progress check produced a notification, and why it did not."""

    sent: bool = False
    delivered: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    suppressed_reason: str = ""

    @property
    def suppressed(self) -> bool:
        """Return whether a report was withheld rather than never due."""
        return bool(self.suppressed_reason)


@dataclass(slots=True)
class ProgressNotifier:
    """Emits progress on a timer, at most once per cooldown, per run.

    Holds the last-sent instant per run rather than per notifier, so one
    notifier shared by a deployment does not let a chatty run's cooldown
    suppress a quiet one's first report.
    """

    sinks: tuple[ProgressSink, ...] = ()
    interval_seconds: float = PROGRESS_NOTIFICATION_INTERVAL_SECONDS
    cooldown_seconds: float = PROGRESS_NOTIFICATION_COOLDOWN_SECONDS
    clock: Callable[[], float] = time.monotonic
    _last_sent: dict[str, float] = field(default_factory=dict, repr=False)

    def is_due(self, report: ProgressReport) -> bool:
        """Return whether ``report`` has run long enough to be worth sending."""
        return report.elapsed_seconds >= self.interval_seconds

    def in_cooldown(self, run_id: str) -> bool:
        """Return whether this run reported recently enough to stay quiet."""
        last = self._last_sent.get(run_id)
        return last is not None and (self.clock() - last) < self.cooldown_seconds

    async def report(
        self, report: ProgressReport, *, attention: Attention | None = None
    ) -> ProgressOutcome:
        """Send ``report`` if it is due and nothing suppresses it.

        Three suppressions, in the order they are cheapest to decide: the run is
        not old enough yet, somebody is already being waited on, or one went out
        inside the cooldown. Each returns a reason rather than a bare false, so
        a test and an operator can both tell "nothing to say" from "said it
        recently".
        """
        if not self.is_due(report):
            return ProgressOutcome(suppressed_reason="")

        if attention is not None and attention.needs_attention:
            return ProgressOutcome(
                suppressed_reason=(
                    "the run is already waiting on a human, who is looking at a surface "
                    "that is already showing it"
                )
            )

        if self.in_cooldown(report.run_id):
            return ProgressOutcome(
                suppressed_reason=(
                    f"a progress notification for this run went out less than "
                    f"{self.cooldown_seconds:.0f} seconds ago"
                )
            )

        self._last_sent[report.run_id] = self.clock()
        delivered: list[str] = []
        failed: list[str] = []
        for sink in self.sinks:
            try:
                await sink.deliver(report)
            except Exception as failure:  # noqa: BLE001 — one sink must not stop the rest
                failed.append(sink.name)
                logger.error(
                    "agent.progress_not_delivered",
                    run_id=report.run_id,
                    sink=sink.name,
                    error=str(failure),
                )
            else:
                delivered.append(sink.name)

        logger.info(
            "agent.progress_reported",
            run_id=report.run_id,
            elapsed_seconds=report.elapsed_seconds,
            iterations=report.iterations,
            sinks=delivered,
        )
        return ProgressOutcome(sent=True, delivered=tuple(delivered), failed=tuple(failed))

    def forget(self, run_id: str) -> None:
        """Drop a finished run's cooldown, so the map does not grow forever."""
        self._last_sent.pop(run_id, None)


__all__ = [
    "ProgressNotifier",
    "ProgressOutcome",
    "ProgressReport",
    "ProgressSink",
]
