"""An investigation concludes at 03:14 and exactly the right people find out.

The primary story, end to end: a diagnosis and its evidence become a report, the
report reaches chat, a ticket, a document, and the disk, a Pushover notification
reaches the on-call engineer's phone with the one-line root cause and a working
link, and nobody else is woken.

Every collaborator here is the real one — the real builder, the real guardrail
engine, the real registry, the real dispatcher, the real policy — except the four
transports, which stand in for vendors and are the only thing a socket would add.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from core.capability.metadata import EvidenceType
from core.domain.diagnosis.result import Claim, Diagnosis, RootCauseCategory
from core.state.evidence import EvidenceEntry
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.sinks import SinkGuard
from platform.notifications.models import (
    Notification,
    NotificationDecision,
    NotificationSink,
    Outcome,
    Severity,
    SinkCall,
    SinkKind,
)
from platform.notifications.policy import NotificationPolicy, QuietHours
from platform.notifications.redaction import SinkRedactor
from platform.notifications.service import NotificationService, deliveries_of
from platform.notifications.sinks.chat import ChatSink
from platform.notifications.sinks.pushover import PushoverSink
from platform.reporting.builder import build_report, metadata_of, screened
from platform.reporting.delivery.dispatcher import DeliveryDispatcher, DeliveryStatus
from platform.reporting.formatters.markdown import REPORT_FILENAME
from platform.reporting.models import Destination, FormattedReport, Report

STARTED = datetime(2026, 3, 1, 3, 10, tzinfo=UTC)
CONCLUDED = datetime(2026, 3, 1, 3, 14, tzinfo=UTC)
RUN_LINK = "https://ninjasre.invalid/runs/run-1"
TEAM = "team-payments"


def evidence() -> tuple[EvidenceEntry, ...]:
    """Return what the investigation observed."""
    return (
        EvidenceEntry(
            id="ev-1",
            capability="metrics-query",
            source="datadog",
            evidence_type=EvidenceType.METRIC,
            summary="checkout p99 rose from 240ms to 4.1s at 03:02",
            reference="https://datadog.invalid/q/1",
            recorded_at=STARTED,
        ),
        EvidenceEntry(
            id="ev-2",
            capability="kubernetes-describe",
            source="kubernetes",
            evidence_type=EvidenceType.CONFIGURATION,
            summary="the checkout deployment sets DB_POOL_MAX=10",
            reference="https://k8s.invalid/deploy/checkout",
            recorded_at=STARTED,
        ),
    )


def diagnosis() -> Diagnosis:
    """Return the conclusion the investigation reached."""
    return Diagnosis(
        root_cause="The 03:02 deploy lowered the connection-pool ceiling to 10.",
        root_cause_category=RootCauseCategory.CONFIGURATION_ERROR,
        causal_chain=(
            "deploy at 03:02 set DB_POOL_MAX=10",
            "peak concurrency is 40",
            "requests queue for a connection",
            "checkout p99 rises to 4.1s",
        ),
        validated_claims=(
            Claim(statement="The pool ceiling is 10", evidence_ids=("ev-2",)),
            Claim(statement="Checkout p99 rose at 03:02", evidence_ids=("ev-1",)),
        ),
        non_validated_claims=(Claim(statement="The cache may also be cold"),),
        remediation_steps=("Raise DB_POOL_MAX to 40 and redeploy",),
        confidence=0.86,
        summary="Checkout latency rose after a deploy narrowed the connection pool.",
    )


class RecordingDeliveryTransport:
    """Stands in for one vendor, keeping what it was given."""

    def __init__(self, reference: str) -> None:
        self.reference = reference
        self.bodies: list[str] = []

    async def deliver(
        self, formatted: FormattedReport, destination: Destination, *, delivery_key: str
    ) -> str:
        """Accept the report and answer with a reference."""
        self.bodies.append(formatted.body)
        return self.reference


class DiskTransport:
    """Writes the Markdown report to the operator's own filesystem."""

    def __init__(self, root: Path) -> None:
        self.root = root

    async def deliver(
        self, formatted: FormattedReport, destination: Destination, *, delivery_key: str
    ) -> str:
        """Write ``report.md`` under the destination's directory and return its path."""
        run_id = delivery_key.split("/", 1)[0]
        directory = self.root / destination.target.lstrip("/") / run_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / REPORT_FILENAME
        path.write_text(formatted.body, encoding="utf-8")
        return str(path)


class RecordingNotificationTransport:
    """Stands in for Pushover, keeping the calls it was sent."""

    def __init__(self) -> None:
        self.calls: list[SinkCall] = []

    async def send(self, call: SinkCall) -> None:
        """Keep ``call``."""
        self.calls.append(call)


class RecordingNotifier:
    """Stands in for the chat adapter, keeping what was posted."""

    def __init__(self) -> None:
        self.posted: list[tuple[str, str]] = []

    async def notify(self, channel: str, text: str) -> None:
        """Keep ``text``."""
        self.posted.append((channel, text))


def report_of() -> Report:
    """Return the report this investigation produces, screened."""
    built = build_report(
        diagnosis(),
        run_id="run-1",
        title="Checkout latency",
        evidence=evidence(),
        metadata=metadata_of(
            evidence(),
            run_id="run-1",
            run_link=RUN_LINK,
            started_at=STARTED,
            finished_at=CONCLUDED,
            cost_usd=0.21,
            prompt_tokens=8_400,
            completion_tokens=1_100,
            model_id="a-model",
            team_node_id=TEAM,
        ),
    )
    return screened(built, engine=GuardrailEngine())


async def test_a_concluded_investigation_reaches_chat_a_ticket_a_document_and_disk(
    tmp_path: Path,
) -> None:
    chat = RecordingDeliveryTransport("1709258040.000100")
    ticket = RecordingDeliveryTransport("OPS-4471")
    document = RecordingDeliveryTransport("https://confluence.invalid/pages/4471")
    disk = DiskTransport(tmp_path)

    records = await DeliveryDispatcher(
        transports={
            "slack": chat,
            "jira": ticket,
            "confluence": document,
            "local_markdown": disk,
        }
    ).deliver(
        report_of(),
        (
            Destination(kind="slack", target="#incidents", verified=True),
            Destination(kind="jira", target="OPS", verified=True),
            Destination(kind="confluence", target="SRE/postmortems", verified=True),
            Destination(kind="local_markdown", target="/reports", verified=True),
        ),
    )

    assert [record.status for record in records] == [DeliveryStatus.DELIVERED] * 4

    on_disk = (tmp_path / "reports" / "run-1" / REPORT_FILENAME).read_text(encoding="utf-8")
    assert "# Checkout latency" in on_disk
    assert "The 03:02 deploy lowered the connection-pool ceiling to 10." in on_disk
    assert "ev-2" in on_disk
    assert "Raise DB_POOL_MAX to 40 and redeploy" in on_disk
    assert RUN_LINK in on_disk

    for transport in (chat, ticket, document):
        assert "The 03:02 deploy lowered the connection-pool ceiling to 10." in transport.bodies[0]


async def test_a_pushover_notification_reaches_the_phone_with_a_working_link() -> None:
    push = RecordingNotificationTransport()
    notifier = RecordingNotifier()
    report = report_of()
    service = NotificationService(
        policy=NotificationPolicy(
            sinks=(
                NotificationSink(kind=SinkKind.PUSHOVER, target="user-key", verified=True),
                NotificationSink(kind=SinkKind.CHAT, target="#incidents", verified=True),
            ),
            quiet_hours=QuietHours(),
        ),
        deliveries=deliveries_of((PushoverSink(transport=push), ChatSink(notifier=notifier))),
        redactor=SinkRedactor(guard=SinkGuard(engine=GuardrailEngine())),
    )

    records = await service.notify(
        Notification(
            subject="checkout-latency",
            title=report.title,
            message=report.root_cause,
            severity=Severity.CRITICAL,
            outcome=Outcome.UNRESOLVED,
            team_node_id=TEAM,
            run_id="run-1",
            link=RUN_LINK,
        ),
        at=CONCLUDED,
    )

    assert all(record.decision is NotificationDecision.SENT for record in records)
    payload = push.calls[0].payload
    assert payload["title"] == "Checkout latency"
    assert payload["message"] == "The 03:02 deploy lowered the connection-pool ceiling to 10."
    assert payload["priority"] == 2
    assert payload["sound"]
    assert payload["url"] == RUN_LINK
    assert payload["url_title"]


async def test_nobody_else_is_woken_by_the_same_incident() -> None:
    push = RecordingNotificationTransport()
    notifier = RecordingNotifier()
    service = NotificationService(
        policy=NotificationPolicy(
            sinks=(
                NotificationSink(kind=SinkKind.PUSHOVER, target="user-key", verified=True),
                NotificationSink(kind=SinkKind.CHAT, target="#incidents", verified=True),
            ),
            quiet_hours=QuietHours(),
        ),
        deliveries=deliveries_of((PushoverSink(transport=push), ChatSink(notifier=notifier))),
    )

    def about(severity: Severity) -> Notification:
        return Notification(
            subject="checkout-latency",
            title="Checkout latency",
            message="still degraded",
            severity=severity,
            team_node_id=TEAM,
            run_id="run-1",
            link=RUN_LINK,
        )

    await service.notify(about(Severity.CRITICAL), at=CONCLUDED)
    repeat = await service.notify(about(Severity.CRITICAL), at=CONCLUDED)
    followup = await service.notify(about(Severity.MEDIUM), at=CONCLUDED)

    # The repeat is suppressed by the cooldown, and the medium follow-up reaches
    # chat rather than the phone: one incident, one page.
    assert repeat[0].decision is NotificationDecision.SUPPRESSED
    assert [record.sink for record in followup] == ["chat:#incidents"]
    assert len(push.calls) == 1
    assert service.report(at=CONCLUDED)["suppressed"]


async def test_a_report_that_reached_no_conclusion_still_says_what_was_ruled_out(
    tmp_path: Path,
) -> None:
    inconclusive = build_report(
        Diagnosis(
            root_cause="",
            confidence=0.0,
            non_validated_claims=(
                Claim(statement="The database saturated", evidence_ids=("ev-1",)),
            ),
            summary="",
        ),
        run_id="run-2",
        title="Checkout latency",
        evidence=evidence(),
        metadata=metadata_of(evidence(), run_id="run-2", run_link=RUN_LINK),
    )
    disk = DiskTransport(tmp_path)

    await DeliveryDispatcher(transports={"local_markdown": disk}).deliver(
        inconclusive, (Destination(kind="local_markdown", target="/reports", verified=True),)
    )

    written = (tmp_path / "reports" / "run-2" / REPORT_FILENAME).read_text(encoding="utf-8")
    assert "No confident root cause was established" in written
    assert "## Ruled out" in written
    assert "The database saturated" in written
