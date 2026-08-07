"""What a notification is, where it can go, and what happened to it.

A notification is not a report. The report is the thing somebody reads; this is
the thing that gets them to it, and it is deliberately small — a subject, a
severity, a sentence, and a link. Everything about its size is a consequence of
where it is read: a phone's lock screen at 03:14.

Two fields deserve their sentence.

**``subject`` is the cooldown key, not a title.** Two notifications about the
same subject inside the window are the same notification arriving twice, and
what makes that judgeable is a stable identifier for what the notification is
*about* — a service, an alert, an approval — rather than the words in it.

**Every decision is recorded, including the ones that sent nothing.** A
suppression that left no record makes "why wasn't I told?" unanswerable, and
that is the question asked after every missed incident.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.notifications import (
    NOTIFICATION_RECORD_DECISION,
    NOTIFICATION_RECORD_REASON,
    NOTIFICATION_RECORD_SEVERITY,
    NOTIFICATION_RECORD_SINK,
    NOTIFICATION_RECORD_SUBJECT,
    NOTIFICATION_SEVERITIES,
    PAGING_SINKS,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_NOISE,
    SINK_CHAT,
    SINK_EMAIL,
    SINK_PAGERDUTY,
    SINK_PUSHOVER,
    SINK_WEBHOOK,
)
from platform.reporting.models import Audience


class Severity(StrEnum):
    """How much of somebody's attention this is worth.

    Ordered, so "at least high" is a comparison rather than a list somebody
    forgets to extend when a sixth level is added.
    """

    CRITICAL = SEVERITY_CRITICAL
    HIGH = SEVERITY_HIGH
    MEDIUM = SEVERITY_MEDIUM
    LOW = SEVERITY_LOW
    NOISE = SEVERITY_NOISE

    @property
    def rank(self) -> int:
        """Return this severity's position, most severe first."""
        return NOTIFICATION_SEVERITIES.index(self.value)

    def at_least(self, other: Severity) -> bool:
        """Return whether this severity is at least as severe as ``other``."""
        return self.rank <= other.rank

    @property
    def pages(self) -> bool:
        """Return whether this severity may wake somebody."""
        return self.at_least(Severity.HIGH)


class Outcome(StrEnum):
    """How the investigation this notification is about ended.

    Separate from severity, because they answer different questions. A critical
    incident that resolved itself and a critical incident nobody has looked at
    are the same severity and very different notifications.
    """

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    NO_CONCLUSION = "no_conclusion"
    NOISE = "noise"


class SinkKind(StrEnum):
    """The five kinds of notification target."""

    PUSHOVER = SINK_PUSHOVER
    EMAIL = SINK_EMAIL
    WEBHOOK = SINK_WEBHOOK
    PAGERDUTY = SINK_PAGERDUTY
    CHAT = SINK_CHAT

    @property
    def pages(self) -> bool:
        """Return whether this kind of sink wakes somebody."""
        return self.value in PAGING_SINKS


class NotificationDecision(StrEnum):
    """What the policy did about one notification."""

    SENT = "sent"
    #: Inside the cooldown for this subject. Recorded, always.
    SUPPRESSED = "suppressed"
    #: The team has had its allowance for this window.
    RATE_LIMITED = "rate_limited"
    #: Quiet hours moved it off the paging sinks; it still went somewhere.
    DIVERTED = "diverted"
    #: The severity routes to no sink this team has configured.
    NO_SINK = "no_sink"
    #: The sink was asked and did not take it.
    FAILED = "failed"


class NotificationError(Exception):
    """Base for everything a notification transport raises."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class NotificationUnavailable(NotificationError):
    """The sink could not be reached, or refused this call."""


@dataclass(frozen=True, slots=True)
class NotificationSink:
    """One configured notification target.

    Carries no credential, for the reason nothing above the credential proxy
    does: the transport holds a tenant-scoped handle and the secret is injected
    at the network edge. What is here — a device key's *name*, a channel, an
    address — is configuration an operator edits and a health report prints.
    """

    kind: SinkKind
    target: str
    audience: Audience = Audience.PRIVATE
    enabled: bool = True
    verified: bool = False
    options: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.target.strip():
            raise ValueError(f"{self.kind.value}: a sink must name a target to notify")
        object.__setattr__(self, "target", self.target.strip())

    @property
    def name(self) -> str:
        """Return the identifier a record, a log line, and a health report use."""
        return f"{self.kind.value}:{self.target}"

    @property
    def pages(self) -> bool:
        """Return whether reaching this sink wakes somebody."""
        return self.kind.pages


@dataclass(frozen=True, slots=True)
class Notification:
    """One thing worth telling somebody, in the size a lock screen shows."""

    subject: str
    title: str
    message: str
    severity: Severity = Severity.MEDIUM
    outcome: Outcome = Outcome.UNRESOLVED
    team_node_id: str = ""
    run_id: str = ""
    link: str = ""

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("a notification must name the subject its cooldown is keyed on")
        if not self.title.strip():
            raise ValueError(f"{self.subject}: a notification must have a title")
        object.__setattr__(self, "subject", self.subject.strip())

    @property
    def fingerprint(self) -> str:
        """Return the key a cooldown window is kept per.

        Team, subject, and severity. Severity is in the key on purpose: an
        incident that was medium an hour ago and is critical now is not the same
        notification, and suppressing the second one because of the first is the
        failure this feature exists to avoid.
        """
        return f"{self.team_node_id}|{self.subject}|{self.severity.value}"

    def with_text(self, *, title: str, message: str) -> Notification:
        """Return this notification with different prose and everything else kept."""
        return Notification(
            subject=self.subject,
            title=title,
            message=message,
            severity=self.severity,
            outcome=self.outcome,
            team_node_id=self.team_node_id,
            run_id=self.run_id,
            link=self.link,
        )


@dataclass(frozen=True, slots=True)
class NotificationRecord:
    """What happened to one notification at one sink.

    Produced for every decision, including the ones that sent nothing. ``sink``
    is empty when the decision was made before any sink was chosen — a
    suppression applies to the whole notification, not to one destination of it.
    """

    subject: str
    severity: Severity
    decision: NotificationDecision
    sink: str = ""
    reason: str = ""
    team_node_id: str = ""
    run_id: str = ""
    at: datetime | None = None

    @property
    def told_somebody(self) -> bool:
        """Return whether this record represents a notification that arrived."""
        return self.decision is NotificationDecision.SENT

    def to_payload(self) -> dict[str, Any]:
        """Return the payload a run-trace event carries."""
        return {
            NOTIFICATION_RECORD_SINK: self.sink,
            NOTIFICATION_RECORD_SUBJECT: self.subject,
            NOTIFICATION_RECORD_SEVERITY: self.severity.value,
            NOTIFICATION_RECORD_DECISION: self.decision.value,
            NOTIFICATION_RECORD_REASON: self.reason,
        }


@dataclass(frozen=True, slots=True)
class SinkCall:
    """One request to a sink's API, built by a sink and carrying no credential.

    Four of the five sinks are HTTP JSON APIs, so one call shape covers them and
    the per-sink part is the path and the payload — which is exactly the part
    that belongs to the sink. A transport that had to know which vendor it was
    carrying for would be a fifth place they differ.
    """

    method: str
    path: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class NotificationTransport(Protocol):
    """Carries one sink call and reports whether it was taken."""

    async def send(self, call: SinkCall) -> None:
        """Send ``call``, raising ``NotificationUnavailable`` if it did not land."""


@runtime_checkable
class ChatNotifier(Protocol):
    """Posts a line into a chat channel somebody is already watching.

    A protocol rather than a chat adapter, because this is tier 3 and the chat
    adapters are an entry point. A deployment hands over whatever it wired for
    chat; nothing here knows which of the four platforms it reached.
    """

    async def notify(self, channel: str, text: str) -> None:
        """Post ``text`` to ``channel``, raising ``NotificationUnavailable`` if it did not."""


__all__ = [
    "ChatNotifier",
    "Notification",
    "NotificationDecision",
    "NotificationError",
    "NotificationRecord",
    "NotificationSink",
    "NotificationTransport",
    "NotificationUnavailable",
    "Outcome",
    "Severity",
    "SinkCall",
    "SinkKind",
]
