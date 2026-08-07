"""Routing a notification, redacting it per sink, sending it, and recording all of it.

The policy decides and the sinks send; this is the one object that does both in
the right order, and the order is where the properties live.

**Redaction happens per sink, after routing.** One notification is built, and
each sink's audience decides what its copy contains. Redacting before routing
would produce one text for every readership, which is the design this feature
exists to not have.

**The cooldown window opens only once something arrived.** ``commit`` runs after
delivery, so a notification that reached no working sink does not open a
fifteen-minute quiet window — otherwise one vendor's outage becomes an outage in
the notification system, silently, for the duration of the window.

**Every decision is recorded, including the sends that failed.** A sink that
refused is a record with a reason on it, and the others still get their copy: one
sink's failure must not decide who else was told.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from platform.notifications.escalation import Escalation, EscalationRegistry
from platform.notifications.models import (
    Notification,
    NotificationDecision,
    NotificationError,
    NotificationRecord,
    NotificationSink,
    Severity,
    SinkKind,
)
from platform.notifications.policy import NotificationPolicy
from platform.notifications.redaction import SinkRedactor
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@runtime_checkable
class SinkDelivery(Protocol):
    """Sends one notification to one configured sink of its kind."""

    @property
    def kind(self) -> SinkKind:
        """Return the sink kind this delivers to."""

    async def deliver(self, notification: Notification, sink: NotificationSink) -> None:
        """Deliver ``notification``, raising ``NotificationError`` if it did not land."""


@runtime_checkable
class NotificationTrace(Protocol):
    """Where a notification decision is written down."""

    async def record_notification(self, record: NotificationRecord) -> None:
        """Record that ``record`` happened."""


@dataclass(slots=True)
class NotificationService:
    """Decides, redacts, sends, and records — in that order."""

    policy: NotificationPolicy
    deliveries: Mapping[SinkKind, SinkDelivery] = field(default_factory=dict)
    redactor: SinkRedactor | None = None
    escalations: EscalationRegistry = field(default_factory=EscalationRegistry)
    trace: NotificationTrace | None = None
    clock: Callable[[], datetime] = _utc_now
    records: list[NotificationRecord] = field(default_factory=list)

    async def notify(
        self, notification: Notification, *, at: datetime | None = None
    ) -> tuple[NotificationRecord, ...]:
        """Send ``notification`` where policy says it goes, and record every decision."""
        moment = at if at is not None else self.clock()
        routing = self.policy.route(notification, at=moment)

        produced = list(routing.records)
        for sink in routing.sinks:
            produced.append(await self._send(notification, sink, moment))

        if any(record.told_somebody for record in produced):
            self.policy.commit(routing, at=moment)

        for record in produced:
            self.records.append(record)
            await self._record(record)
        return tuple(produced)

    async def escalate_due(self, *, at: datetime | None = None) -> tuple[NotificationRecord, ...]:
        """Send every escalation that has come due, and record each one.

        An escalation whose item resolved first is not here at all: ``resolve``
        removed it from the registry, so there is no state in which this method
        has to decide whether to skip one.
        """
        moment = at if at is not None else self.clock()
        produced: list[NotificationRecord] = []
        for escalation in self.escalations.due(at=moment):
            record = await self._send(_escalation_notification(escalation), escalation.sink, moment)
            produced.append(record)
            self.records.append(record)
            await self._record(record)
        return tuple(produced)

    def resolve(self, item_id: str, *, reason: str = "") -> Escalation | None:
        """Cancel ``item_id``'s pending escalation because the item closed."""
        return self.escalations.resolve(item_id, reason=reason)

    def report(self, *, at: datetime | None = None) -> Mapping[str, Any]:
        """Return what an operator is shown about what they were and were not told.

        The suppressions and the rate-limit refusals are the half nobody sees
        otherwise: a notification that arrived is self-evident, and one that did
        not is only visible here.
        """
        moment = at if at is not None else self.clock()
        return {
            "sent": sum(1 for record in self.records if record.told_somebody),
            "suppressed": [suppression.describe() for suppression in self.policy.cooldown.recent()],
            "rate_limits": self.policy.limits.report(at=moment),
            "pending_escalations": len(self.escalations.pending),
        }

    async def _send(
        self, notification: Notification, sink: NotificationSink, at: datetime
    ) -> NotificationRecord:
        """Deliver one copy, redacted for this sink's audience, and return the record."""
        delivery = self.deliveries.get(sink.kind)
        if delivery is None:
            return self._record_for(
                notification,
                sink,
                NotificationDecision.FAILED,
                at,
                reason=f"no delivery is configured for {sink.kind.value}",
            )
        if not sink.verified:
            return self._record_for(
                notification,
                sink,
                NotificationDecision.FAILED,
                at,
                reason=f"{sink.name} has never been verified",
            )

        copy = (
            self.redactor.redact(notification, audience=sink.audience)
            if self.redactor is not None
            else notification
        )
        try:
            await delivery.deliver(copy, sink)
        except NotificationError as failure:
            logger.warning("notifications.sink_failed", sink=sink.name, reason=failure.reason)
            return self._record_for(
                notification, sink, NotificationDecision.FAILED, at, reason=failure.reason
            )
        except Exception as unexpected:  # noqa: BLE001 - one sink's failure, not the run's
            reason = f"{type(unexpected).__name__}: {unexpected}"
            logger.error("notifications.sink_raised", sink=sink.name, error=reason)
            return self._record_for(
                notification, sink, NotificationDecision.FAILED, at, reason=reason
            )
        return self._record_for(notification, sink, NotificationDecision.SENT, at)

    def _record_for(
        self,
        notification: Notification,
        sink: NotificationSink,
        decision: NotificationDecision,
        at: datetime,
        *,
        reason: str = "",
    ) -> NotificationRecord:
        """Return one sink's record."""
        return NotificationRecord(
            subject=notification.subject,
            severity=notification.severity,
            decision=decision,
            sink=sink.name,
            reason=reason,
            team_node_id=notification.team_node_id,
            run_id=notification.run_id,
            at=at,
        )

    async def _record(self, record: NotificationRecord) -> None:
        """Write ``record`` to the trace without letting the write undo the send."""
        if self.trace is None:
            return
        try:
            await self.trace.record_notification(record)
        except Exception as failure:  # noqa: BLE001 - the notification already arrived
            logger.error(
                "notifications.decision_not_traced",
                sink=record.sink,
                decision=record.decision.value,
                error=str(failure),
            )


def _escalation_notification(escalation: Escalation) -> Notification:
    """Return the notification one escalation becomes."""
    return Notification(
        subject=escalation.subject,
        title=f"Still waiting: {escalation.summary or escalation.subject}",
        message=escalation.describe(),
        severity=escalation.severity,
        team_node_id=escalation.team_node_id,
        run_id=escalation.run_id,
    )


def deliveries_of(deliveries: Sequence[SinkDelivery]) -> Mapping[SinkKind, SinkDelivery]:
    """Return ``deliveries`` keyed by the kind each one handles."""
    return {delivery.kind: delivery for delivery in deliveries}


def escalation_severity(severity: Severity) -> Severity:
    """Return the severity an escalation of ``severity`` carries.

    One step up, capped at critical. An escalation that arrives at the same
    severity as the notification nobody acted on is the same notification again,
    and the recipient has already decided how much attention that is worth.
    """
    if severity is Severity.CRITICAL:
        return Severity.CRITICAL
    return Severity(["critical", "high", "medium", "low", "noise"][max(severity.rank - 1, 0)])


__all__ = [
    "NotificationService",
    "NotificationTrace",
    "SinkDelivery",
    "escalation_severity",
    "deliveries_of",
]
