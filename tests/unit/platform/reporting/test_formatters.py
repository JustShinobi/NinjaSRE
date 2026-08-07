"""Five formatters, thirteen destinations, and the sections none of them may drop."""

from __future__ import annotations

import pytest

from config.constants.notifications import (
    REPORT_DESTINATIONS,
    REPORT_SUMMARY_NOTICE,
)
from platform.reporting.formatters.chat import ChatFormatter
from platform.reporting.formatters.document import DocumentFormatter
from platform.reporting.formatters.email import EmailFormatter
from platform.reporting.formatters.markdown import MarkdownFormatter
from platform.reporting.formatters.ticket import TicketFormatter
from platform.reporting.models import (
    NO_CONCLUSION_STATEMENT,
    Audience,
    Destination,
    DestinationClass,
    EvidenceReference,
    Horizon,
    RecommendedAction,
    Report,
    ReportClaim,
    ReportMetadata,
    RuledOut,
)
from platform.reporting.registry import FORMATTERS, formatter_for, render
from platform.reporting.sizing import fit_to_destination

EVIDENCE_SUMMARY = "error rate rose to 12% at 03:02"


def reference() -> EvidenceReference:
    """Return an evidence reference a claim cites."""
    return EvidenceReference(
        evidence_id="ev-1",
        capability="metrics-query",
        source="datadog",
        summary=EVIDENCE_SUMMARY,
        reference="https://example.invalid/q/1",
    )


def report(**overrides: object) -> Report:
    """Return a fully populated report."""
    fields: dict[str, object] = {
        "run_id": "run-1",
        "title": "checkout latency",
        "summary": "Checkout latency rose after a deploy narrowed the connection pool.",
        "root_cause": "The 14:02 deploy lowered the pool ceiling below peak concurrency.",
        "confidence_score": 0.82,
        "causal_chain": ("deploy at 14:02", "pool ceiling 10", "requests queue"),
        "validated_claims": (
            ReportClaim(statement="The pool ceiling is 10", evidence=(reference(),)),
        ),
        "non_validated_claims": (ReportClaim(statement="The cache may be cold"),),
        "ruled_out": (RuledOut(hypothesis="database saturation", reason="CPU flat at 20%"),),
        "recommended_actions": (
            RecommendedAction(action="Raise the pool ceiling", horizon=Horizon.IMMEDIATE),
            RecommendedAction(action="Backfill the dashboards", horizon=Horizon.SHORT_TERM),
            RecommendedAction(action="Add a saturation alert", horizon=Horizon.PREVENTIVE),
        ),
        "metadata": ReportMetadata(
            run_id="run-1",
            run_link="https://ninjasre.invalid/runs/run-1",
            capabilities_used=("logs-search", "metrics-query"),
            duration_seconds=242.0,
            cost_usd=0.19,
            prompt_tokens=1_200,
            completion_tokens=300,
        ),
    }
    fields.update(overrides)
    return Report(**fields)  # type: ignore[arg-type]


ALL_FORMATTERS = (
    ChatFormatter(),
    TicketFormatter(),
    DocumentFormatter(),
    MarkdownFormatter(),
    EmailFormatter(),
)

DESTINATION_FOR_CLASS = {
    DestinationClass.CHAT: Destination(kind="slack", target="#incidents"),
    DestinationClass.TICKET: Destination(kind="jira", target="OPS"),
    DestinationClass.DOCUMENT: Destination(kind="confluence", target="SRE/postmortems"),
    DestinationClass.MARKDOWN: Destination(kind="local_markdown", target="/var/reports"),
    DestinationClass.EMAIL: Destination(kind="email", target="oncall@example.invalid"),
}


# -- T013-T017: every formatter renders every section --------------------------


@pytest.mark.parametrize("formatter", ALL_FORMATTERS, ids=lambda f: type(f).__name__)
def test_every_formatter_renders_every_section(formatter: object) -> None:
    destination = DESTINATION_FOR_CLASS[formatter.destination_class]  # type: ignore[attr-defined]

    formatted = formatter.format(report(), destination)  # type: ignore[attr-defined]

    body = formatted.body
    assert "Checkout latency rose after a deploy" in body
    assert "The 14:02 deploy lowered the pool ceiling" in body
    assert "high" in body.lower()
    assert "pool ceiling 10" in body
    assert "The pool ceiling is 10" in body
    assert "ev-1" in body
    assert "The cache may be cold" in body
    assert "database saturation" in body
    assert "CPU flat at 20%" in body
    assert "Raise the pool ceiling" in body
    assert "Backfill the dashboards" in body
    assert "Add a saturation alert" in body
    assert "metrics-query" in body
    assert "https://ninjasre.invalid/runs/run-1" in body


@pytest.mark.parametrize("formatter", ALL_FORMATTERS, ids=lambda f: type(f).__name__)
def test_every_formatter_titles_the_report(formatter: object) -> None:
    destination = DESTINATION_FOR_CLASS[formatter.destination_class]  # type: ignore[attr-defined]

    formatted = formatter.format(report(), destination)  # type: ignore[attr-defined]

    assert "checkout latency" in formatted.title
    assert formatted.destination == destination.name
    assert formatted.destination_class is formatter.destination_class  # type: ignore[attr-defined]
    assert not formatted.summarised


@pytest.mark.parametrize("formatter", ALL_FORMATTERS, ids=lambda f: type(f).__name__)
def test_every_formatter_states_a_missing_conclusion_plainly(formatter: object) -> None:
    destination = DESTINATION_FOR_CLASS[formatter.destination_class]  # type: ignore[attr-defined]
    inconclusive = report(
        root_cause="",
        confidence_score=0.0,
        validated_claims=(),
        summary=NO_CONCLUSION_STATEMENT,
    )

    formatted = formatter.format(inconclusive, destination)  # type: ignore[attr-defined]

    assert NO_CONCLUSION_STATEMENT in formatted.body
    assert "database saturation" in formatted.body


@pytest.mark.parametrize("formatter", ALL_FORMATTERS, ids=lambda f: type(f).__name__)
def test_a_public_audience_never_sees_an_evidence_body(formatter: object) -> None:
    destination = DESTINATION_FOR_CLASS[formatter.destination_class]  # type: ignore[attr-defined]
    public = Destination(kind=destination.kind, target=destination.target, audience=Audience.PUBLIC)

    formatted = formatter.format(report(), public)  # type: ignore[attr-defined]

    assert EVIDENCE_SUMMARY not in formatted.body
    assert "The pool ceiling is 10" in formatted.body


# -- Per-formatter shapes -------------------------------------------------------


def test_the_markdown_formatter_produces_a_document_with_headings() -> None:
    formatted = MarkdownFormatter().format(
        report(), DESTINATION_FOR_CLASS[DestinationClass.MARKDOWN]
    )

    assert formatted.body.startswith("# ")
    assert "## Root cause" in formatted.body
    assert "## Ruled out" in formatted.body


def test_the_email_formatter_produces_html_and_a_plain_text_alternative() -> None:
    formatted = EmailFormatter().format(report(), DESTINATION_FOR_CLASS[DestinationClass.EMAIL])

    assert formatted.body.lstrip().startswith("<")
    assert "<h2>" in formatted.body
    assert formatted.plain_body
    assert "<" not in formatted.plain_body
    assert "Raise the pool ceiling" in formatted.plain_body


def test_the_email_formatter_escapes_markup_that_arrived_in_the_content() -> None:
    formatted = EmailFormatter().format(
        report(title="<script>alert(1)</script>"),
        DESTINATION_FOR_CLASS[DestinationClass.EMAIL],
    )

    assert "<script>" not in formatted.body
    assert "&lt;script&gt;" in formatted.body


def test_the_ticket_formatter_leads_with_the_actions_a_ticket_is_opened_for() -> None:
    formatted = TicketFormatter().format(report(), DESTINATION_FOR_CLASS[DestinationClass.TICKET])

    body = formatted.body
    assert body.index("Raise the pool ceiling") < body.index("database saturation")


def test_the_chat_formatter_leads_with_the_one_line_a_reader_needs() -> None:
    formatted = ChatFormatter().format(report(), DESTINATION_FOR_CLASS[DestinationClass.CHAT])

    first = formatted.body.splitlines()[0]
    assert "The 14:02 deploy lowered the pool ceiling" in first


def test_the_document_formatter_is_shaped_like_a_postmortem() -> None:
    formatted = DocumentFormatter().format(
        report(), DESTINATION_FOR_CLASS[DestinationClass.DOCUMENT]
    )

    body = formatted.body
    for heading in ("Summary", "Root cause", "Timeline", "What we ruled out", "Follow-up"):
        assert heading in body


# -- T018: the registry ---------------------------------------------------------


def test_every_destination_class_has_a_formatter() -> None:
    assert set(FORMATTERS) == set(DestinationClass)


def test_every_one_of_the_thirteen_destinations_resolves_to_a_formatter() -> None:
    for kind in REPORT_DESTINATIONS:
        destination = Destination(kind=kind, target="somewhere")
        assert formatter_for(destination).destination_class is destination.destination_class


def test_rendering_goes_through_the_registry_and_fits_the_destination() -> None:
    formatted = render(report(), Destination(kind="slack", target="#incidents"))

    assert formatted.destination_class is DestinationClass.CHAT
    assert formatted.length <= Destination(kind="slack", target="#incidents").size_limit


# -- T019/SC-007: oversize is summarised with a link, never truncated -----------


def long_report() -> Report:
    """Return a report far larger than the smallest destination accepts."""
    return report(causal_chain=tuple(f"step {index} " + "x" * 200 for index in range(60)))


def test_an_oversized_report_is_summarised_with_a_link_rather_than_cut() -> None:
    destination = Destination(kind="discord", target="#incidents")
    full = MarkdownFormatter().format(long_report(), destination)

    fitted = fit_to_destination(full, destination, link="https://ninjasre.invalid/runs/run-1")

    assert fitted.summarised
    assert fitted.length <= destination.size_limit
    assert REPORT_SUMMARY_NOTICE in fitted.body
    assert "https://ninjasre.invalid/runs/run-1" in fitted.body
    assert not fitted.body.endswith("xxx")


def test_a_summarised_delivery_still_carries_the_conclusion_and_the_actions() -> None:
    destination = Destination(kind="discord", target="#incidents")
    full = MarkdownFormatter().format(long_report(), destination)

    fitted = fit_to_destination(full, destination, link="https://ninjasre.invalid/runs/run-1")

    assert "The 14:02 deploy lowered the pool ceiling" in fitted.body
    assert "Raise the pool ceiling" in fitted.body


def test_a_report_inside_the_limit_is_delivered_whole() -> None:
    destination = Destination(kind="local_markdown", target="/var/reports")
    full = MarkdownFormatter().format(report(), destination)

    fitted = fit_to_destination(full, destination, link="https://ninjasre.invalid/runs/run-1")

    assert fitted == full
    assert not fitted.summarised


def test_a_summary_that_still_does_not_fit_falls_back_to_the_link_alone() -> None:
    destination = Destination(kind="pagerduty", target="service-1", size_limit_override=140)
    full = MarkdownFormatter().format(long_report(), destination)

    fitted = fit_to_destination(full, destination, link="https://ninjasre.invalid/runs/run-1")

    assert fitted.summarised
    assert fitted.length <= 140
    assert "https://ninjasre.invalid/runs/run-1" in fitted.body


def test_rendering_an_oversized_report_through_the_registry_summarises_it() -> None:
    destination = Destination(kind="discord", target="#incidents")

    formatted = render(long_report(), destination)

    assert formatted.summarised
    assert formatted.length <= destination.size_limit
    assert "https://ninjasre.invalid/runs/run-1" in formatted.body
