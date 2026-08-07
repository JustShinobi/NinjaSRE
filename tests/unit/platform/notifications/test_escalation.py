"""Escalating what nobody addressed, and — the whole point — not escalating what resolved."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from config.constants.notifications import ESCALATION_DELAY_SECONDS, MAX_ESCALATION_ROUNDS
from platform.notifications.escalation import EscalationRegistry, EscalationState
from platform.notifications.models import (
    Notification,
    NotificationDecision,
    NotificationSink,
    Severity,
    SinkCall,
    SinkKind,
)
from platform.notifications.policy import NotificationPolicy
from platform.notifications.service import NotificationService, deliveries_of, escalation_severity
from platform.notifications.sinks.pushover import PushoverSink

RAISED = datetime(2026, 3, 1, 3, 0, tzinfo=UTC)
TEAM = "team-payments"


def sink() -> NotificationSink:
    """Return the sink an escalation reaches."""
    return NotificationSink(kind=SinkKind.PUSHOVER, target="user-key", verified=True)


def registry(**overrides: object) -> EscalationRegistry:
    """Return an escalation registry."""
    return EscalationRegistry(**overrides)  # type: ignore[arg-type]


def scheduled(live: EscalationRegistry, item_id: str = "approval-1") -> None:
    """Schedule one escalation for ``item_id``."""
    live.schedule(
        item_id,
        subject="pool-ceiling-change",
        team_node_id=TEAM,
        sink=sink(),
        summary="an approval for raising the pool ceiling",
        run_id="run-1",
        at=RAISED,
    )


# -- T039/FR-019: an unaddressed item escalates ---------------------------------


def test_an_item_nobody_addressed_escalates_after_the_delay() -> None:
    live = registry()
    scheduled(live)

    assert live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS - 1)) == ()

    fired = live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS))

    assert [item.item_id for item in fired] == ["approval-1"]
    assert fired[0].state is EscalationState.FIRED
    assert "nobody has addressed it" in fired[0].describe()


def test_an_escalation_reaches_the_configured_destination() -> None:
    live = registry()
    scheduled(live)

    fired = live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS))

    assert fired[0].sink.kind is SinkKind.PUSHOVER


def test_an_escalation_is_bounded_and_stops() -> None:
    live = registry()
    scheduled(live)
    at = RAISED

    for _ in range(MAX_ESCALATION_ROUNDS):
        at = at + timedelta(seconds=ESCALATION_DELAY_SECONDS)
        assert live.due(at=at)

    at = at + timedelta(seconds=ESCALATION_DELAY_SECONDS)
    assert live.due(at=at) == ()
    assert live.pending == {}


def test_firing_does_not_repeat_on_the_next_tick() -> None:
    live = registry()
    scheduled(live)
    at = RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS)

    assert live.due(at=at)
    assert live.due(at=at) == ()


def test_rescheduling_an_item_replaces_rather_than_adds() -> None:
    live = registry()
    scheduled(live)
    scheduled(live)

    assert len(live.pending) == 1


def test_pending_escalations_are_visible_per_team() -> None:
    live = registry()
    scheduled(live)

    assert [item.item_id for item in live.pending_for(TEAM)] == ["approval-1"]
    assert live.pending_for("team-search") == ()


# -- T040/SC-008: cancellation --------------------------------------------------


def test_an_escalation_is_cancelled_when_the_item_resolves_first() -> None:
    live = registry()
    scheduled(live)

    cancelled = live.resolve("approval-1", reason="approved by somebody at minute nine")

    assert cancelled is not None
    assert cancelled.state is EscalationState.CANCELLED
    assert live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS * 5)) == ()
    assert [item.item_id for item in live.cancelled] == ["approval-1"]


def test_resolving_an_item_nobody_escalated_is_not_an_error() -> None:
    assert registry().resolve("never-scheduled") is None


def test_a_resolution_after_the_first_round_stops_the_second() -> None:
    live = registry()
    scheduled(live)
    live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS))

    live.resolve("approval-1")

    assert live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS * 4)) == ()


def test_cancelling_one_item_leaves_the_others_pending() -> None:
    live = registry()
    scheduled(live, "approval-1")
    scheduled(live, "approval-2")

    live.resolve("approval-1")

    fired = live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS))
    assert [item.item_id for item in fired] == ["approval-2"]


# -- Escalating through the service ---------------------------------------------


class RecordingTransport:
    """Keeps the calls it was sent."""

    def __init__(self) -> None:
        self.calls: list[SinkCall] = []

    async def send(self, call: SinkCall) -> None:
        """Keep ``call``."""
        self.calls.append(call)


def service(live: EscalationRegistry, transport: RecordingTransport) -> NotificationService:
    """Return a service that can send an escalation."""
    return NotificationService(
        policy=NotificationPolicy(sinks=(sink(),)),
        deliveries=deliveries_of((PushoverSink(transport=transport),)),
        escalations=live,
    )


async def test_a_due_escalation_is_sent_and_recorded() -> None:
    live = registry()
    scheduled(live)
    transport = RecordingTransport()

    records = await service(live, transport).escalate_due(
        at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS)
    )

    assert [record.decision for record in records] == [NotificationDecision.SENT]
    assert "Still waiting" in transport.calls[0].payload["title"]


async def test_an_escalation_resolved_first_sends_nothing() -> None:
    live = registry()
    scheduled(live)
    transport = RecordingTransport()
    running = service(live, transport)

    running.resolve("approval-1", reason="approved at minute nine")
    records = await running.escalate_due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS))

    assert records == ()
    assert transport.calls == []


def test_an_escalation_is_more_urgent_than_the_notification_nobody_acted_on() -> None:
    assert escalation_severity(Severity.MEDIUM) is Severity.HIGH
    assert escalation_severity(Severity.HIGH) is Severity.CRITICAL
    assert escalation_severity(Severity.CRITICAL) is Severity.CRITICAL


def test_the_escalation_notification_names_what_is_waiting() -> None:
    live = registry()
    scheduled(live)

    fired = live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS))

    assert "an approval for raising the pool ceiling" in fired[0].describe()


def test_a_notification_built_from_an_escalation_carries_its_run() -> None:
    from platform.notifications.service import _escalation_notification

    live = registry()
    scheduled(live)
    fired = live.due(at=RAISED + timedelta(seconds=ESCALATION_DELAY_SECONDS))

    built: Notification = _escalation_notification(fired[0])

    assert built.run_id == "run-1"
    assert built.team_node_id == TEAM
