"""What each sink actually sends, and what it never sends."""

from __future__ import annotations

import pytest

from config.constants.notifications import (
    PUSHOVER_MAX_MESSAGE_CHARS,
    PUSHOVER_MAX_TITLE_CHARS,
    PUSHOVER_PRIORITY_EMERGENCY,
    PUSHOVER_PRIORITY_HIGH,
    PUSHOVER_PRIORITY_LOW,
    PUSHOVER_PRIORITY_NORMAL,
    PUSHOVER_SOUND_DEFAULT,
    PUSHOVER_SOUND_PAGING,
)
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import GuardrailAction, GuardrailRule, Ruleset
from platform.guardrails.sinks import SinkGuard
from platform.masking.context import MaskingContext
from platform.notifications.models import (
    Notification,
    NotificationSink,
    NotificationUnavailable,
    Outcome,
    Severity,
    SinkCall,
    SinkKind,
)
from platform.notifications.redaction import SinkRedactor
from platform.notifications.sinks.chat import ChatSink
from platform.notifications.sinks.email import EmailSink
from platform.notifications.sinks.pagerduty import PagerDutySink
from platform.notifications.sinks.pushover import PushoverSink
from platform.notifications.sinks.webhook import WebhookSink
from platform.reporting.models import Audience

LINK = "https://ninjasre.invalid/runs/run-1"


class RecordingTransport:
    """Remembers the calls it was asked to send."""

    def __init__(self) -> None:
        self.calls: list[SinkCall] = []

    async def send(self, call: SinkCall) -> None:
        """Keep ``call``."""
        self.calls.append(call)


class FailingTransport:
    """Refuses everything, saying why."""

    async def send(self, call: SinkCall) -> None:
        """Refuse."""
        raise NotificationUnavailable("the vendor answered 401")


def notification(**overrides: object) -> Notification:
    """Return a notification to send."""
    fields: dict[str, object] = {
        "subject": "checkout-latency",
        "title": "Checkout latency: connection pool exhausted",
        "message": "The 14:02 deploy narrowed the pool.",
        "severity": Severity.CRITICAL,
        "outcome": Outcome.UNRESOLVED,
        "team_node_id": "team-payments",
        "run_id": "run-1",
        "link": LINK,
    }
    fields.update(overrides)
    return Notification(**fields)  # type: ignore[arg-type]


def sink(kind: SinkKind, target: str, **overrides: object) -> NotificationSink:
    """Return a verified sink."""
    return NotificationSink(kind=kind, target=target, verified=True, **overrides)  # type: ignore[arg-type]


# -- T026/SC-003: Pushover ------------------------------------------------------


async def test_pushover_sends_a_title_message_priority_sound_and_link() -> None:
    transport = RecordingTransport()

    await PushoverSink(transport=transport).deliver(
        notification(), sink(SinkKind.PUSHOVER, "user-key")
    )

    payload = transport.calls[0].payload
    assert payload["user"] == "user-key"
    assert payload["title"] == "Checkout latency: connection pool exhausted"
    assert payload["message"] == "The 14:02 deploy narrowed the pool."
    assert payload["priority"] == PUSHOVER_PRIORITY_EMERGENCY
    assert payload["sound"] == PUSHOVER_SOUND_PAGING
    assert payload["url"] == LINK
    assert payload["url_title"]


@pytest.mark.parametrize(
    ("severity", "priority"),
    [
        (Severity.CRITICAL, PUSHOVER_PRIORITY_EMERGENCY),
        (Severity.HIGH, PUSHOVER_PRIORITY_HIGH),
        (Severity.MEDIUM, PUSHOVER_PRIORITY_NORMAL),
        (Severity.LOW, PUSHOVER_PRIORITY_LOW),
    ],
)
async def test_pushover_priority_follows_the_severity(severity: Severity, priority: int) -> None:
    transport = RecordingTransport()

    await PushoverSink(transport=transport).deliver(
        notification(severity=severity), sink(SinkKind.PUSHOVER, "user-key")
    )

    assert transport.calls[0].payload["priority"] == priority


async def test_a_non_paging_severity_does_not_get_the_loud_sound() -> None:
    transport = RecordingTransport()

    await PushoverSink(transport=transport).deliver(
        notification(severity=Severity.LOW), sink(SinkKind.PUSHOVER, "user-key")
    )

    assert transport.calls[0].payload["sound"] == PUSHOVER_SOUND_DEFAULT


async def test_a_teams_own_sound_wins() -> None:
    transport = RecordingTransport()

    await PushoverSink(transport=transport).deliver(
        notification(),
        sink(SinkKind.PUSHOVER, "user-key", options={"sound": "siren"}),
    )

    assert transport.calls[0].payload["sound"] == "siren"


async def test_a_notification_longer_than_pushover_accepts_is_marked_when_shortened() -> None:
    transport = RecordingTransport()

    await PushoverSink(transport=transport).deliver(
        notification(title="t" * 400, message="m" * 4_000),
        sink(SinkKind.PUSHOVER, "user-key"),
    )

    payload = transport.calls[0].payload
    assert len(payload["title"]) == PUSHOVER_MAX_TITLE_CHARS
    assert len(payload["message"]) == PUSHOVER_MAX_MESSAGE_CHARS
    assert payload["title"].endswith("…")
    assert payload["message"].endswith("…")
    assert payload["url"] == LINK


async def test_a_device_is_addressed_when_the_team_named_one() -> None:
    transport = RecordingTransport()

    await PushoverSink(transport=transport).deliver(
        notification(), sink(SinkKind.PUSHOVER, "user-key", options={"device": "phone"})
    )

    assert transport.calls[0].payload["device"] == "phone"


async def test_a_pushover_failure_is_raised_for_the_caller_to_record() -> None:
    with pytest.raises(NotificationUnavailable):
        await PushoverSink(transport=FailingTransport()).deliver(
            notification(), sink(SinkKind.PUSHOVER, "user-key")
        )


def test_a_pushover_call_can_be_inspected_without_sending_it() -> None:
    call = PushoverSink(transport=RecordingTransport()).call_for(
        notification(), sink(SinkKind.PUSHOVER, "user-key")
    )

    assert call.method == "POST"
    assert call.path.endswith("messages.json")


# -- T027-T029: email, webhook, PagerDuty ---------------------------------------


async def test_email_sends_both_a_plain_and_an_html_alternative() -> None:
    transport = RecordingTransport()

    await EmailSink(transport=transport, sender="ninjasre@example.invalid").deliver(
        notification(), sink(SinkKind.EMAIL, "oncall@example.invalid")
    )

    payload = transport.calls[0].payload
    assert payload["to"] == "oncall@example.invalid"
    assert payload["from"] == "ninjasre@example.invalid"
    assert payload["subject"] == "Checkout latency: connection pool exhausted"
    assert "<" not in payload["text"]
    assert LINK in payload["text"]
    assert "<h1>" in payload["html"]


async def test_email_escapes_markup_that_arrived_in_the_content() -> None:
    transport = RecordingTransport()

    await EmailSink(transport=transport).deliver(
        notification(title="<script>alert(1)</script>"),
        sink(SinkKind.EMAIL, "oncall@example.invalid"),
    )

    assert "<script>" not in transport.calls[0].payload["html"]
    assert "&lt;script&gt;" in transport.calls[0].payload["html"]


async def test_a_webhook_receives_the_fields_rather_than_a_sentence() -> None:
    transport = RecordingTransport()

    await WebhookSink(transport=transport).deliver(
        notification(), sink(SinkKind.WEBHOOK, "https://example.invalid/hook")
    )

    call = transport.calls[0]
    assert call.path == "https://example.invalid/hook"
    assert call.payload["severity"] == "critical"
    assert call.payload["outcome"] == "unresolved"
    assert call.payload["subject"] == "checkout-latency"
    assert call.payload["run_id"] == "run-1"
    assert call.payload["version"]


async def test_pagerduty_triggers_an_incident_keyed_on_the_fingerprint() -> None:
    transport = RecordingTransport()

    await PagerDutySink(transport=transport).deliver(
        notification(), sink(SinkKind.PAGERDUTY, "routing-key")
    )

    payload = transport.calls[0].payload
    assert payload["event_action"] == "trigger"
    assert payload["routing_key"] == "routing-key"
    assert payload["dedup_key"] == notification().fingerprint
    assert payload["payload"]["severity"] == "critical"
    assert payload["links"][0]["href"] == LINK


async def test_pagerduty_resolves_rather_than_triggers_for_a_resolved_outcome() -> None:
    transport = RecordingTransport()

    await PagerDutySink(transport=transport).deliver(
        notification(outcome=Outcome.RESOLVED), sink(SinkKind.PAGERDUTY, "routing-key")
    )

    payload = transport.calls[0].payload
    assert payload["event_action"] == "resolve"
    assert "payload" not in payload


# -- T030: chat delegates ------------------------------------------------------


class RecordingNotifier:
    """Keeps the lines it was asked to post."""

    def __init__(self) -> None:
        self.posted: list[tuple[str, str]] = []

    async def notify(self, channel: str, text: str) -> None:
        """Keep ``text``."""
        self.posted.append((channel, text))


async def test_chat_posts_one_line_with_the_severity_and_the_link() -> None:
    notifier = RecordingNotifier()

    await ChatSink(notifier=notifier).deliver(notification(), sink(SinkKind.CHAT, "#incidents"))

    channel, text = notifier.posted[0]
    assert channel == "#incidents"
    assert text.startswith("[critical]")
    assert "Checkout latency" in text
    assert LINK in text


# -- T031/T032/SC-006: redaction at the sink -----------------------------------


def secret_guard(masking: MaskingContext | None = None) -> SinkGuard:
    """Return a guard whose ruleset redacts a token shape."""
    import re

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
    return SinkGuard(engine=GuardrailEngine(ruleset=ruleset), masking=masking)


@pytest.mark.parametrize("audience", list(Audience))
def test_no_audience_ever_sees_a_secret(audience: Audience) -> None:
    redactor = SinkRedactor(guard=secret_guard())

    redacted = redactor.redact(
        notification(title="tok_abcdef123456 leaked", message="in tok_abcdef123456"),
        audience=audience,
    )

    assert "tok_abcdef123456" not in redacted.title
    assert "tok_abcdef123456" not in redacted.message
    assert "[REDACTED]" in redacted.title


def test_a_private_audience_sees_masked_identifiers_restored() -> None:
    masking = MaskingContext()
    token = masking.mapping.token_for("POD", "checkout-7f9dd-x7gr9")
    redactor = SinkRedactor(guard=secret_guard(masking))

    redacted = redactor.redact(
        notification(message=f"{token} is OOMKilling"), audience=Audience.PRIVATE
    )

    assert "checkout-7f9dd-x7gr9" in redacted.message


@pytest.mark.parametrize("audience", [Audience.TEAM, Audience.PUBLIC])
def test_an_unauthorised_audience_keeps_the_token(audience: Audience) -> None:
    masking = MaskingContext()
    token = masking.mapping.token_for("POD", "checkout-7f9dd-x7gr9")
    redactor = SinkRedactor(guard=secret_guard(masking))

    redacted = redactor.redact(notification(message=f"{token} is OOMKilling"), audience=audience)

    assert "checkout-7f9dd-x7gr9" not in redacted.message
    assert token in redacted.message


def test_the_link_is_never_redacted() -> None:
    redactor = SinkRedactor(guard=secret_guard())

    redacted = redactor.redact(notification(), audience=Audience.PUBLIC)

    assert redacted.link == LINK
