"""What a report is required to carry, and what it refuses to be built without."""

from __future__ import annotations

import pytest

from config.constants.notifications import (
    DESTINATION_CLASS_OF,
    DESTINATION_SIZE_LIMITS,
    REPORT_DESTINATIONS,
)
from platform.reporting.models import (
    Audience,
    Confidence,
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


def reference(identifier: str = "ev-1") -> EvidenceReference:
    """Return an evidence reference a claim can cite."""
    return EvidenceReference(
        evidence_id=identifier,
        capability="metrics-query",
        source="datadog",
        summary="error rate rose to 12% at 03:02",
        reference="https://example.invalid/q/1",
    )


def report(**overrides: object) -> Report:
    """Return a report with every required section populated."""
    fields: dict[str, object] = {
        "run_id": "run-1",
        "title": "checkout latency",
        "summary": "Checkout latency rose after a deploy narrowed the connection pool.",
        "root_cause": "The 14:02 deploy lowered the pool ceiling below peak concurrency.",
        "confidence_score": 0.82,
        "causal_chain": ("deploy at 14:02", "pool ceiling 10", "requests queue", "latency"),
        "validated_claims": (
            ReportClaim(statement="The pool ceiling is 10", evidence=(reference(),)),
        ),
        "non_validated_claims": (ReportClaim(statement="The cache may be cold"),),
        "ruled_out": (RuledOut(hypothesis="database saturation", reason="CPU flat at 20%"),),
        "recommended_actions": (
            RecommendedAction(action="Raise the pool ceiling", horizon=Horizon.IMMEDIATE),
            RecommendedAction(action="Add a pool-saturation alert", horizon=Horizon.PREVENTIVE),
        ),
        "metadata": ReportMetadata(
            run_id="run-1",
            run_link="https://ninjasre.invalid/runs/run-1",
            capabilities_used=("metrics-query", "logs-search"),
            duration_seconds=42.5,
            cost_usd=0.19,
        ),
    }
    fields.update(overrides)
    return Report(**fields)  # type: ignore[arg-type]


# -- FR-001: every section is present ------------------------------------------


def test_a_report_carries_every_section_the_requirement_names() -> None:
    built = report()

    assert built.summary
    assert built.root_cause
    assert built.confidence is Confidence.HIGH
    assert built.causal_chain
    assert built.validated_claims
    assert built.non_validated_claims
    assert built.recommended_actions
    assert built.ruled_out
    assert built.metadata.capabilities_used == ("metrics-query", "logs-search")
    assert built.metadata.duration_seconds == 42.5
    assert built.metadata.cost_usd == 0.19


def test_every_section_survives_a_round_trip_through_a_record() -> None:
    restored = Report.from_record(report().to_record())

    assert restored == report()


# -- FR-003: a validated claim without evidence is not representable ------------


def test_a_validated_claim_must_carry_an_evidence_reference() -> None:
    with pytest.raises(ValueError, match="evidence"):
        report(validated_claims=(ReportClaim(statement="The pool ceiling is 10"),))


def test_a_claim_is_validated_exactly_when_it_cites_something() -> None:
    assert ReportClaim(statement="x", evidence=(reference(),)).is_validated
    assert not ReportClaim(statement="x").is_validated


def test_a_claim_with_no_statement_is_refused() -> None:
    with pytest.raises(ValueError, match="say something"):
        ReportClaim(statement="   ", evidence=(reference(),))


# -- FR-002: the no-conclusion case is a property of the report, not a phrasing --


def test_a_report_with_no_root_cause_says_it_reached_no_conclusion() -> None:
    inconclusive = report(root_cause="", confidence_score=0.0, validated_claims=())

    assert not inconclusive.has_conclusion
    assert inconclusive.confidence is Confidence.NONE


def test_a_report_with_a_root_cause_but_no_confidence_reached_no_conclusion() -> None:
    assert not report(confidence_score=0.0).has_conclusion


def test_confidence_bands_are_derived_from_the_score_not_asserted() -> None:
    assert report(confidence_score=0.9).confidence is Confidence.HIGH
    assert report(confidence_score=0.6).confidence is Confidence.MEDIUM
    assert report(confidence_score=0.2).confidence is Confidence.LOW
    assert report(confidence_score=0.0).confidence is Confidence.NONE


def test_a_score_outside_the_unit_interval_is_refused() -> None:
    with pytest.raises(ValueError, match="between"):
        report(confidence_score=1.4)


# -- Recommended actions are grouped by horizon --------------------------------


def test_recommended_actions_are_readable_by_horizon() -> None:
    built = report()

    assert [action.action for action in built.actions_for(Horizon.IMMEDIATE)] == [
        "Raise the pool ceiling"
    ]
    assert [action.action for action in built.actions_for(Horizon.PREVENTIVE)] == [
        "Add a pool-saturation alert"
    ]
    assert built.actions_for(Horizon.SHORT_TERM) == ()


# -- Destinations: thirteen, five classes --------------------------------------


def test_the_thirteen_destinations_are_all_classified() -> None:
    assert len(REPORT_DESTINATIONS) == 13
    assert set(DESTINATION_CLASS_OF) == set(REPORT_DESTINATIONS)
    assert {DestinationClass(value) for value in DESTINATION_CLASS_OF.values()} == set(
        DestinationClass
    )


def test_every_destination_declares_a_size_limit() -> None:
    assert set(DESTINATION_SIZE_LIMITS) == set(REPORT_DESTINATIONS)
    assert all(limit > 0 for limit in DESTINATION_SIZE_LIMITS.values())


def test_a_destination_knows_its_class_and_its_limit() -> None:
    destination = Destination(kind="slack", target="#incidents")

    assert destination.destination_class is DestinationClass.CHAT
    assert destination.size_limit == DESTINATION_SIZE_LIMITS["slack"]


def test_a_destination_nothing_renders_is_refused() -> None:
    with pytest.raises(ValueError, match="carrier-pigeon"):
        Destination(kind="carrier-pigeon", target="loft")


def test_a_destination_with_no_target_is_refused() -> None:
    with pytest.raises(ValueError, match="target"):
        Destination(kind="slack", target="  ")


def test_only_a_private_audience_may_see_restored_identifiers() -> None:
    assert Audience.PRIVATE.restores_identifiers
    assert not Audience.TEAM.restores_identifiers
    assert not Audience.PUBLIC.restores_identifiers


def test_a_public_audience_may_not_carry_evidence_bodies() -> None:
    assert Audience.PRIVATE.carries_evidence
    assert Audience.TEAM.carries_evidence
    assert not Audience.PUBLIC.carries_evidence


def test_a_delivery_key_is_stable_per_run_and_destination() -> None:
    first = Destination(kind="slack", target="#incidents")
    second = Destination(kind="slack", target="#incidents")
    other = Destination(kind="slack", target="#platform")

    assert first.delivery_key("run-1") == second.delivery_key("run-1")
    assert first.delivery_key("run-1") != other.delivery_key("run-1")
    assert first.delivery_key("run-1") != first.delivery_key("run-2")
