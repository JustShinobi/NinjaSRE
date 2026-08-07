"""SC-001: one report, thirteen destinations, each rendering correctly.

Driven against *recorded* destination responses rather than live vendors: each
row below carries the constraints that destination actually imposes — the body
limit it enforces and the fields its API refuses a call without — taken from its
published contract. A transport that accepts a body its real counterpart would
reject is a transport that passes this suite and fails at 03:00, so the checking
happens here rather than in a mock that says yes to everything.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from config.constants.notifications import (
    DESTINATION_SIZE_LIMITS,
    REPORT_DESTINATIONS,
    REPORT_SUMMARY_NOTICE,
)
from platform.reporting.delivery.dispatcher import (
    DeliveryDispatcher,
    DeliveryStatus,
    PermanentDeliveryFailure,
)
from platform.reporting.models import (
    Destination,
    DestinationClass,
    EvidenceReference,
    FormattedReport,
    Horizon,
    RecommendedAction,
    Report,
    ReportClaim,
    ReportMetadata,
    RuledOut,
)
from platform.reporting.registry import render

RUN_LINK = "https://ninjasre.invalid/runs/run-1"

#: A plausible target per destination, so the delivery key and the recorded
#: response are the shapes each vendor actually addresses.
TARGETS: dict[str, str] = {
    "slack": "#incidents",
    "microsoft_teams": "19:meeting@thread.tacv2",
    "telegram": "-1001234567890",
    "discord": "1189234567890123456",
    "jira": "OPS",
    "github": "acme/checkout",
    "gitlab": "acme/checkout",
    "confluence": "SRE/postmortems",
    "notion": "8a1f2c3d4e5f6070",
    "google_docs": "1AbCdEfGhIjKlMnOp",
    "pagerduty": "R0UT1NGK3Y",
    "local_markdown": "/var/lib/ninjasre/reports",
    "email": "oncall@example.invalid",
}


@dataclass(frozen=True, slots=True)
class RecordedDestination:
    """What one destination's API accepts, as it is documented to."""

    kind: str
    #: The reference shape the vendor answers with, so a caller can go and look.
    reference: str

    @property
    def limit(self) -> int:
        """Return the body size this destination enforces."""
        return DESTINATION_SIZE_LIMITS[self.kind]


RECORDED: tuple[RecordedDestination, ...] = (
    RecordedDestination("slack", "1709258040.000100"),
    RecordedDestination("microsoft_teams", "1:activity:0f1e2d3c"),
    RecordedDestination("telegram", "4471"),
    RecordedDestination("discord", "1189234567890123999"),
    RecordedDestination("jira", "OPS-4471"),
    RecordedDestination("github", "https://github.invalid/acme/checkout/issues/4471"),
    RecordedDestination("gitlab", "https://gitlab.invalid/acme/checkout/-/issues/4471"),
    RecordedDestination("confluence", "https://confluence.invalid/pages/4471"),
    RecordedDestination("notion", "8a1f2c3d-4e5f-6070-8191-a2b3c4d5e6f7"),
    RecordedDestination("google_docs", "https://docs.invalid/document/d/1AbCdEfGhIjKlMnOp"),
    RecordedDestination("pagerduty", "Q1W2E3R4T5Y6U7"),
    RecordedDestination("local_markdown", "/var/lib/ninjasre/reports/run-1/report.md"),
    RecordedDestination("email", "<4471@ninjasre.invalid>"),
)


class RecordedTransport:
    """A transport that answers as the recorded vendor would — including refusing.

    The refusals are the point. A body over the destination's limit, an empty
    title, or an empty body are all things the real API rejects, and a stub that
    accepted them would prove nothing about whether the formatter works.
    """

    def __init__(self, recorded: RecordedDestination) -> None:
        self.recorded = recorded
        self.accepted: list[FormattedReport] = []
        self.keys: list[str] = []

    async def deliver(
        self, formatted: FormattedReport, destination: Destination, *, delivery_key: str
    ) -> str:
        """Accept the delivery if the recorded vendor would, and refuse if it would not."""
        if not formatted.title.strip():
            raise PermanentDeliveryFailure(f"{self.recorded.kind} refuses a call with no title")
        if not formatted.body.strip():
            raise PermanentDeliveryFailure(f"{self.recorded.kind} refuses an empty body")
        if len(formatted.body) > self.recorded.limit:
            raise PermanentDeliveryFailure(
                f"{self.recorded.kind} refuses a body of {len(formatted.body)} characters; "
                f"its limit is {self.recorded.limit}"
            )
        if formatted.destination_class is DestinationClass.EMAIL and not formatted.plain_body:
            raise PermanentDeliveryFailure("email refuses a message with no plain-text part")
        self.accepted.append(formatted)
        self.keys.append(delivery_key)
        return self.recorded.reference


def report(**overrides: object) -> Report:
    """Return a full report with every section populated."""
    reference = EvidenceReference(
        evidence_id="ev-1",
        capability="metrics-query",
        source="datadog",
        summary="error rate rose to 12% at 03:02",
        reference="https://datadog.invalid/q/1",
    )
    fields: dict[str, object] = {
        "run_id": "run-1",
        "title": "Checkout latency",
        "summary": "Checkout latency rose after a deploy narrowed the connection pool.",
        "root_cause": "The 14:02 deploy lowered the pool ceiling below peak concurrency.",
        "confidence_score": 0.82,
        "causal_chain": ("deploy at 14:02", "pool ceiling 10", "requests queue"),
        "validated_claims": (
            ReportClaim(statement="The pool ceiling is 10", evidence=(reference,)),
        ),
        "non_validated_claims": (ReportClaim(statement="The cache may be cold"),),
        "ruled_out": (RuledOut(hypothesis="database saturation", reason="CPU flat at 20%"),),
        "recommended_actions": (
            RecommendedAction(action="Raise the pool ceiling", horizon=Horizon.IMMEDIATE),
            RecommendedAction(action="Add a saturation alert", horizon=Horizon.PREVENTIVE),
        ),
        "metadata": ReportMetadata(
            run_id="run-1",
            run_link=RUN_LINK,
            capabilities_used=("logs-search", "metrics-query"),
            duration_seconds=242.0,
            cost_usd=0.19,
        ),
    }
    fields.update(overrides)
    return Report(**fields)  # type: ignore[arg-type]


def destination_for(recorded: RecordedDestination) -> Destination:
    """Return the verified destination ``recorded`` stands for."""
    return Destination(kind=recorded.kind, target=TARGETS[recorded.kind], verified=True)


pytestmark = pytest.mark.contract


def test_the_recorded_set_covers_every_destination_the_platform_declares() -> None:
    assert {item.kind for item in RECORDED} == set(REPORT_DESTINATIONS)
    assert len(RECORDED) == 13


@pytest.mark.parametrize("recorded", RECORDED, ids=lambda item: item.kind)
async def test_a_report_is_accepted_by_every_destination(
    recorded: RecordedDestination,
) -> None:
    transport = RecordedTransport(recorded)
    destination = destination_for(recorded)

    records = await DeliveryDispatcher(transports={recorded.kind: transport}).deliver(
        report(), (destination,)
    )

    assert records[0].status is DeliveryStatus.DELIVERED, records[0].reason
    assert records[0].reference == recorded.reference
    assert len(transport.accepted) == 1


@pytest.mark.parametrize("recorded", RECORDED, ids=lambda item: item.kind)
def test_every_destination_renders_the_conclusion_and_the_actions(
    recorded: RecordedDestination,
) -> None:
    formatted = render(report(), destination_for(recorded))

    assert "The 14:02 deploy lowered the pool ceiling" in formatted.body
    assert "Raise the pool ceiling" in formatted.body


@pytest.mark.parametrize("recorded", RECORDED, ids=lambda item: item.kind)
def test_a_destination_with_room_renders_every_section(
    recorded: RecordedDestination,
) -> None:
    formatted = render(report(), destination_for(recorded))

    if formatted.summarised:
        pytest.skip(f"{recorded.kind} summarises a full report; covered by SC-007")
    for fragment in (
        "Checkout latency rose after a deploy",
        "pool ceiling 10",
        "The pool ceiling is 10",
        "ev-1",
        "The cache may be cold",
        "database saturation",
        "Add a saturation alert",
        "metrics-query",
        RUN_LINK,
    ):
        assert fragment in formatted.body, f"{recorded.kind} dropped {fragment!r}"


@pytest.mark.parametrize("recorded", RECORDED, ids=lambda item: item.kind)
async def test_an_oversized_report_is_still_accepted_because_it_is_summarised(
    recorded: RecordedDestination,
) -> None:
    transport = RecordedTransport(recorded)
    huge = report(causal_chain=tuple(f"step {index} " + "x" * 500 for index in range(400)))

    records = await DeliveryDispatcher(transports={recorded.kind: transport}).deliver(
        huge, (destination_for(recorded),)
    )

    assert records[0].status is DeliveryStatus.DELIVERED, records[0].reason
    delivered = transport.accepted[0]
    if delivered.summarised:
        assert REPORT_SUMMARY_NOTICE in delivered.body
        assert RUN_LINK in delivered.body


async def test_one_destination_failing_leaves_the_other_twelve_delivered() -> None:
    class Refusing:
        async def deliver(
            self, formatted: FormattedReport, destination: Destination, *, delivery_key: str
        ) -> str:
            raise PermanentDeliveryFailure("the project was archived")

    transports: dict[str, object] = {
        item.kind: RecordedTransport(item) for item in RECORDED if item.kind != "jira"
    }
    transports["jira"] = Refusing()

    records = await DeliveryDispatcher(transports=transports).deliver(  # type: ignore[arg-type]
        report(), tuple(destination_for(item) for item in RECORDED)
    )

    by_kind = {record.destination.split(":")[0]: record for record in records}
    assert by_kind["jira"].status is DeliveryStatus.REFUSED
    assert sum(1 for record in records if record.succeeded) == 12
