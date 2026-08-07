"""Routing, redacting, sending, and recording — and what happens when a sink fails."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import GuardrailAction, GuardrailRule, Ruleset
from platform.guardrails.sinks import SinkGuard
from platform.notifications.cooldown import Cooldown
from platform.notifications.limits import RateLimiter
from platform.notifications.models import (
    Notification,
    NotificationDecision,
    NotificationRecord,
    NotificationSink,
    NotificationUnavailable,
    Outcome,
    Severity,
    SinkCall,
    SinkKind,
)
from platform.notifications.policy import NotificationPolicy
from platform.notifications.redaction import SinkRedactor
from platform.notifications.service import NotificationService, deliveries_of
from platform.notifications.sinks.chat import ChatSink
from platform.notifications.sinks.pushover import PushoverSink
from platform.reporting.models import Audience

NOW = datetime(2026, 3, 1, 14, 0, tzinfo=UTC)
TEAM = "team-payments"


class RecordingTransport:
    """Keeps the calls it was sent."""

    def __init__(self) -> None:
        self.calls: list[SinkCall] = []

    async def send(self, call: SinkCall) -> None:
        """Keep ``call``."""
        self.calls.append(call)


class FailingTransport:
    """Refuses everything."""

    async def send(self, call: SinkCall) -> None:
        """Refuse."""
        raise NotificationUnavailable("the vendor answered 401")


class RecordingNotifier:
    """Keeps the chat lines it was asked to post."""

    def __init__(self) -> None:
        self.posted: list[tuple[str, str]] = []

    async def notify(self, channel: str, text: str) -> None:
        """Keep ``text``."""
        self.posted.append((channel, text))


def notification(**overrides: object) -> Notification:
    """Return a notification to send."""
    fields: dict[str, object] = {
        "subject": "checkout-latency",
        "title": "Checkout latency",
        "message": "The deploy narrowed the pool.",
        "severity": Severity.HIGH,
        "outcome": Outcome.UNRESOLVED,
        "team_node_id": TEAM,
        "run_id": "run-1",
        "link": "https://ninjasre.invalid/runs/run-1",
    }
    fields.update(overrides)
    return Notification(**fields)  # type: ignore[arg-type]


def pushover(**overrides: object) -> NotificationSink:
    """Return a verified Pushover sink."""
    return NotificationSink(kind=SinkKind.PUSHOVER, target="user-key", verified=True, **overrides)  # type: ignore[arg-type]


def chat(**overrides: object) -> NotificationSink:
    """Return a verified chat sink."""
    return NotificationSink(kind=SinkKind.CHAT, target="#incidents", verified=True, **overrides)  # type: ignore[arg-type]


# -- Delivering to every routed sink --------------------------------------------


async def test_a_notification_reaches_every_sink_its_severity_routes_to() -> None:
    push, notifier = RecordingTransport(), RecordingNotifier()
    service = NotificationService(
        policy=NotificationPolicy(sinks=(pushover(), chat())),
        deliveries=deliveries_of((PushoverSink(transport=push), ChatSink(notifier=notifier))),
    )

    records = await service.notify(notification(), at=NOW)

    assert [record.decision for record in records] == [
        NotificationDecision.SENT,
        NotificationDecision.SENT,
    ]
    assert len(push.calls) == 1
    assert len(notifier.posted) == 1


async def test_one_sink_failing_does_not_stop_the_others() -> None:
    notifier = RecordingNotifier()
    service = NotificationService(
        policy=NotificationPolicy(sinks=(pushover(), chat())),
        deliveries=deliveries_of(
            (PushoverSink(transport=FailingTransport()), ChatSink(notifier=notifier))
        ),
    )

    records = await service.notify(notification(), at=NOW)

    by_sink = {record.sink: record for record in records}
    assert by_sink["pushover:user-key"].decision is NotificationDecision.FAILED
    assert by_sink["pushover:user-key"].reason == "the vendor answered 401"
    assert by_sink["chat:#incidents"].decision is NotificationDecision.SENT
    assert len(notifier.posted) == 1


async def test_an_unverified_sink_is_not_delivered_to() -> None:
    push = RecordingTransport()
    unverified = NotificationSink(kind=SinkKind.PUSHOVER, target="user-key")
    service = NotificationService(
        policy=NotificationPolicy(sinks=(unverified,)),
        deliveries=deliveries_of((PushoverSink(transport=push),)),
    )

    records = await service.notify(notification(), at=NOW)

    assert records[0].decision is NotificationDecision.FAILED
    assert "never been verified" in records[0].reason
    assert push.calls == []


async def test_a_sink_with_no_delivery_configured_is_recorded() -> None:
    service = NotificationService(policy=NotificationPolicy(sinks=(pushover(),)), deliveries={})

    records = await service.notify(notification(), at=NOW)

    assert records[0].decision is NotificationDecision.FAILED
    assert "no delivery is configured" in records[0].reason


# -- The cooldown opens only once something arrived -----------------------------


async def test_the_cooldown_window_opens_when_a_notification_arrived() -> None:
    cooldown = Cooldown()
    service = NotificationService(
        policy=NotificationPolicy(sinks=(chat(),), cooldown=cooldown),
        deliveries=deliveries_of((ChatSink(notifier=RecordingNotifier()),)),
    )

    await service.notify(notification(), at=NOW)
    second = await service.notify(notification(), at=NOW + timedelta(seconds=60))

    assert second[0].decision is NotificationDecision.SUPPRESSED


async def test_a_notification_that_reached_nobody_does_not_open_a_quiet_window() -> None:
    cooldown = Cooldown()
    service = NotificationService(
        policy=NotificationPolicy(sinks=(chat(),), cooldown=cooldown),
        deliveries=deliveries_of((ChatSink(notifier=_alwaysFailingNotifier()),)),
    )

    await service.notify(notification(), at=NOW)

    assert cooldown.sent == {}


def _alwaysFailingNotifier() -> object:
    """Return a chat notifier that always refuses."""

    class Refusing:
        async def notify(self, channel: str, text: str) -> None:
            raise NotificationUnavailable("the workspace is gone")

    return Refusing()


async def test_a_notification_that_reached_nobody_does_not_spend_the_rate_limit() -> None:
    limits = RateLimiter()
    service = NotificationService(
        policy=NotificationPolicy(sinks=(chat(),), limits=limits),
        deliveries=deliveries_of((ChatSink(notifier=_alwaysFailingNotifier()),)),
    )

    await service.notify(notification(), at=NOW)

    assert limits.report(at=NOW)["used"] == {}


# -- T031: each sink's copy is redacted for its own audience --------------------


def guard() -> SinkGuard:
    """Return a guard that redacts a token shape."""
    ruleset = Ruleset(
        rules=(
            GuardrailRule(
                name="test-token",
                patterns=(re.compile(r"tok_[A-Za-z0-9]{6,}"),),
                action=GuardrailAction.REDACT,
                replacement="[REDACTED]",
            ),
        )
    )
    return SinkGuard(engine=GuardrailEngine(ruleset=ruleset))


async def test_no_sink_receives_unfiltered_content() -> None:
    push, notifier = RecordingTransport(), RecordingNotifier()
    service = NotificationService(
        policy=NotificationPolicy(sinks=(pushover(), chat(audience=Audience.PUBLIC))),
        deliveries=deliveries_of((PushoverSink(transport=push), ChatSink(notifier=notifier))),
        redactor=SinkRedactor(guard=guard()),
    )

    await service.notify(notification(message="leaked tok_abcdef123456"), at=NOW)

    assert "tok_abcdef123456" not in push.calls[0].payload["message"]
    assert "tok_abcdef123456" not in notifier.posted[0][1]


# -- T037: what an operator is shown --------------------------------------------


async def test_the_report_shows_what_a_team_was_not_told() -> None:
    service = NotificationService(
        policy=NotificationPolicy(sinks=(chat(),)),
        deliveries=deliveries_of((ChatSink(notifier=RecordingNotifier()),)),
    )
    await service.notify(notification(), at=NOW)
    await service.notify(notification(), at=NOW + timedelta(seconds=60))

    report = service.report(at=NOW)

    assert report["sent"] == 1
    assert len(report["suppressed"]) == 1
    assert "checkout-latency" in report["suppressed"][0]
    assert report["pending_escalations"] == 0


# -- The trace ------------------------------------------------------------------


class CollectingTrace:
    """Keeps the notification records it was handed."""

    def __init__(self) -> None:
        self.records: list[NotificationRecord] = []

    async def record_notification(self, record: NotificationRecord) -> None:
        """Keep ``record``."""
        self.records.append(record)


async def test_every_decision_reaches_the_trace_including_the_ones_that_sent_nothing() -> None:
    trace = CollectingTrace()
    service = NotificationService(
        policy=NotificationPolicy(sinks=(chat(),)),
        deliveries=deliveries_of((ChatSink(notifier=RecordingNotifier()),)),
        trace=trace,
    )

    await service.notify(notification(), at=NOW)
    await service.notify(notification(), at=NOW + timedelta(seconds=60))

    assert [record.decision for record in trace.records] == [
        NotificationDecision.SENT,
        NotificationDecision.SUPPRESSED,
    ]


async def test_a_trace_that_fails_does_not_undo_the_notification() -> None:
    class BrokenTrace:
        async def record_notification(self, record: NotificationRecord) -> None:
            raise RuntimeError("the store is down")

    notifier = RecordingNotifier()
    service = NotificationService(
        policy=NotificationPolicy(sinks=(chat(),)),
        deliveries=deliveries_of((ChatSink(notifier=notifier),)),
        trace=BrokenTrace(),
    )

    records = await service.notify(notification(), at=NOW)

    assert records[0].decision is NotificationDecision.SENT
    assert len(notifier.posted) == 1


def test_a_notification_record_renders_the_payload_a_trace_stores() -> None:
    payload = NotificationRecord(
        subject="checkout-latency",
        severity=Severity.HIGH,
        decision=NotificationDecision.SUPPRESSED,
        sink="chat:#incidents",
        reason="within the cooldown",
    ).to_payload()

    assert payload["subject"] == "checkout-latency"
    assert payload["severity"] == "high"
    assert payload["decision"] == "suppressed"
    assert payload["reason"] == "within the cooldown"
