"""One decision, published once, closing the request everywhere it was shown.

The failure this prevents is mundane and constant: a change is announced in
Slack, in Discord, and in the console; somebody approves it in the console; the
two chat messages sit there for the rest of the week with live buttons on them.
The next person clicks one, and either they get an error they cannot interpret
or — much worse — the change applies twice.

So there is one event and every surface subscribes to it, rather than per-surface
state each surface has to keep in step. A surface that was offline when the
decision was made asks for the change's state and gets the same answer; a
surface that was subscribed got told.

**Publishing is idempotent.** A decision publishes exactly once, tracked by
change identifier, because a retry of the decision path must not produce a
second "approved" announcement in a channel that already has one. This is the
same property from the other end as the store refusing a second decision.

**A subscriber that fails does not stop the others.** Closing a request on three
surfaces is three independent obligations, and the one that raised must not
leave the other two showing a live button.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from platform.approvals.models import ChangeState, PendingChange
from platform.observability.logging import get_logger

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DecisionEvent:
    """What every surface is told when a change stops waiting.

    Covers expiry as well as approval and rejection. A change that lapsed is one
    a surface has to stop showing a button for just as much as one that was
    approved, and a surface subscribing to "decisions" that missed expiries
    would leave exactly the stalest requests live.
    """

    change_id: str
    change_type: str
    target: str
    state: ChangeState
    decided_at: datetime
    decided_by: str | None = None
    reason: str | None = None
    requester: str = ""

    @classmethod
    def of(cls, change: PendingChange, *, at: datetime) -> DecisionEvent:
        """Return the event ``change`` reaching its current state produces."""
        return cls(
            change_id=change.change_id,
            change_type=change.change_type.value,
            target=str(change.target),
            state=change.state,
            decided_at=change.decision.decided_at if change.decision else at,
            decided_by=change.decision.decided_by if change.decision else None,
            reason=change.decision.reason if change.decision else None,
            requester=change.requester,
        )

    @property
    def closes_the_request(self) -> bool:
        """Return whether surfaces should stop offering to decide this."""
        return self.state.is_decided

    def to_record(self) -> dict[str, Any]:
        """Return the stored form a transport serialises."""
        return {
            "change_id": self.change_id,
            "change_type": self.change_type,
            "target": self.target,
            "state": self.state.value,
            "decided_at": self.decided_at.isoformat(),
            "decided_by": self.decided_by,
            "reason": self.reason,
            "requester": self.requester,
        }


@runtime_checkable
class DecisionSubscriber(Protocol):
    """A surface that showed the request and has to stop showing it."""

    @property
    def name(self) -> str:
        """Return what this surface is called, for the log line when it fails."""

    async def closed(self, event: DecisionEvent) -> None:
        """Close the request this event decides, wherever this surface showed it."""


@dataclass(slots=True)
class ClosurePublisher:
    """Publishes each decision once, to every surface that asked to hear."""

    subscribers: list[DecisionSubscriber] = field(default_factory=list)
    _published: set[str] = field(default_factory=set, init=False)

    def subscribe(self, subscriber: DecisionSubscriber) -> ClosurePublisher:
        """Register ``subscriber``, and return this publisher so calls chain."""
        self.subscribers.append(subscriber)
        return self

    async def publish(self, event: DecisionEvent) -> tuple[str, ...]:
        """Tell every subscriber, once, and return the ones that were told.

        A repeat for a change already published is dropped and logged rather
        than raised: the caller retrying a decision path has not done anything
        wrong, and the thing that must not happen is a second announcement.
        """
        if event.change_id in self._published:
            _LOG.info(
                "approvals.closure_already_published",
                change_id=event.change_id,
                state=event.state.value,
            )
            return ()

        self._published.add(event.change_id)
        told: list[str] = []
        for subscriber in self.subscribers:
            try:
                await subscriber.closed(event)
            except Exception as failure:  # noqa: BLE001 — one surface must not stop the rest
                _LOG.error(
                    "approvals.closure_failed",
                    change_id=event.change_id,
                    surface=subscriber.name,
                    error=str(failure),
                )
            else:
                told.append(subscriber.name)
        return tuple(told)

    async def publish_all(self, events: Sequence[DecisionEvent]) -> None:
        """Publish a batch, which is what an expiry sweep produces."""
        for event in events:
            await self.publish(event)

    def has_published(self, change_id: str) -> bool:
        """Return whether a decision on ``change_id`` has already gone out."""
        return change_id in self._published


__all__ = [
    "ClosurePublisher",
    "DecisionEvent",
    "DecisionSubscriber",
]
