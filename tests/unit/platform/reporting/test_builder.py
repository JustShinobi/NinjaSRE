"""Turning a diagnosis and the run's evidence into a report a person can act on."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from config.constants.notifications import REPORT_SUMMARY_NOTICE
from core.capability.metadata import EvidenceType
from core.domain.diagnosis.result import Claim, Diagnosis, RootCauseCategory
from core.state.evidence import EvidenceEntry
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.rules import GuardrailAction, GuardrailRule, Ruleset
from platform.reporting.builder import build_report, metadata_of, screened
from platform.reporting.models import (
    NO_CONCLUSION_STATEMENT,
    Confidence,
    Horizon,
    RecommendedAction,
    ReportMetadata,
    RuledOut,
)

STARTED = datetime(2026, 3, 1, 3, 10, tzinfo=UTC)
FINISHED = datetime(2026, 3, 1, 3, 14, tzinfo=UTC)


def entry(identifier: str, capability: str = "metrics-query") -> EvidenceEntry:
    """Return one observation the run holds."""
    return EvidenceEntry(
        id=identifier,
        capability=capability,
        source="datadog",
        evidence_type=EvidenceType.METRIC,
        summary=f"observation {identifier}",
        reference=f"https://example.invalid/{identifier}",
        recorded_at=STARTED,
    )


def diagnosis(**overrides: object) -> Diagnosis:
    """Return a diagnosis with a root cause the evidence supports."""
    fields: dict[str, object] = {
        "root_cause": "The deploy lowered the connection-pool ceiling.",
        "root_cause_category": RootCauseCategory.CONFIGURATION_ERROR,
        "causal_chain": ("deploy", "pool ceiling 10", "queueing", "latency"),
        "validated_claims": (Claim(statement="The pool ceiling is 10", evidence_ids=("ev-1",)),),
        "non_validated_claims": (Claim(statement="The cache may be cold"),),
        "remediation_steps": ("Raise the pool ceiling to 40",),
        "confidence": 0.82,
        "summary": "Latency rose after a deploy narrowed the pool.",
    }
    fields.update(overrides)
    return Diagnosis(**fields)  # type: ignore[arg-type]


# -- T008/T009: the report is assembled, and every validated claim cites evidence --


def test_a_report_is_assembled_from_the_diagnosis_and_the_run_evidence() -> None:
    report = build_report(
        diagnosis(),
        run_id="run-1",
        title="checkout latency",
        evidence=(entry("ev-1"), entry("ev-2", "logs-search")),
    )

    assert report.run_id == "run-1"
    assert report.title == "checkout latency"
    assert report.summary == "Latency rose after a deploy narrowed the pool."
    assert report.root_cause.startswith("The deploy lowered")
    assert report.confidence is Confidence.HIGH
    assert report.causal_chain == ("deploy", "pool ceiling 10", "queueing", "latency")
    assert report.has_conclusion


def test_every_validated_claim_carries_the_evidence_behind_it() -> None:
    report = build_report(
        diagnosis(), run_id="run-1", title="t", evidence=(entry("ev-1"), entry("ev-2"))
    )

    assert len(report.validated_claims) == 1
    cited = report.validated_claims[0].evidence
    assert [item.evidence_id for item in cited] == ["ev-1"]
    assert cited[0].source == "datadog"
    assert cited[0].reference == "https://example.invalid/ev-1"
    assert cited[0].capability == "metrics-query"


def test_a_claim_citing_an_identifier_the_run_does_not_hold_is_demoted() -> None:
    invented = diagnosis(
        validated_claims=(Claim(statement="Invented", evidence_ids=("ev-99",)),),
        non_validated_claims=(),
    )

    report = build_report(invented, run_id="run-1", title="t", evidence=(entry("ev-1"),))

    assert report.validated_claims == ()
    assert [claim.statement for claim in report.non_validated_claims] == ["Invented"]


def test_a_claim_citing_one_held_and_one_invented_identifier_keeps_only_the_held_one() -> None:
    mixed = diagnosis(
        validated_claims=(Claim(statement="Partly cited", evidence_ids=("ev-1", "ev-99")),),
    )

    report = build_report(mixed, run_id="run-1", title="t", evidence=(entry("ev-1"),))

    assert [item.evidence_id for item in report.validated_claims[0].evidence] == ["ev-1"]


# -- T010: the no-conclusion path ------------------------------------------------


def test_a_report_with_no_conclusion_says_so_plainly() -> None:
    report = build_report(
        diagnosis(root_cause="", confidence=0.0, validated_claims=()),
        run_id="run-1",
        title="t",
        evidence=(entry("ev-1"),),
    )

    assert not report.has_conclusion
    assert NO_CONCLUSION_STATEMENT in report.summary


def test_a_no_conclusion_report_presents_what_was_ruled_out() -> None:
    report = build_report(
        diagnosis(root_cause="", confidence=0.0, validated_claims=()),
        run_id="run-1",
        title="t",
        evidence=(entry("ev-1"),),
        ruled_out=(RuledOut(hypothesis="database saturation", reason="CPU flat at 20%"),),
    )

    assert [item.hypothesis for item in report.ruled_out] == ["database saturation"]


def test_a_hypothesis_the_cited_evidence_did_not_support_becomes_a_ruled_out_entry() -> None:
    tested = diagnosis(
        root_cause="",
        confidence=0.0,
        validated_claims=(),
        non_validated_claims=(
            Claim(statement="The database saturated", evidence_ids=("ev-1",)),
            Claim(statement="Something about the cache"),
        ),
    )

    report = build_report(tested, run_id="run-1", title="t", evidence=(entry("ev-1"),))

    # Only the hypothesis that was actually looked at is reported as eliminated.
    # One nobody gathered evidence for was not ruled out; it was not examined.
    assert [item.hypothesis for item in report.ruled_out] == ["The database saturated"]
    assert [item.evidence_id for item in report.ruled_out[0].evidence] == ["ev-1"]
    assert [claim.statement for claim in report.non_validated_claims] == [
        "The database saturated",
        "Something about the cache",
    ]


def test_a_caller_supplied_ruled_out_list_is_not_overwritten_by_the_derived_one() -> None:
    tested = diagnosis(
        root_cause="",
        confidence=0.0,
        validated_claims=(),
        non_validated_claims=(Claim(statement="The database saturated", evidence_ids=("ev-1",)),),
    )

    report = build_report(
        tested,
        run_id="run-1",
        title="t",
        evidence=(entry("ev-1"),),
        ruled_out=(RuledOut(hypothesis="a network partition", reason="both sides saw each other"),),
    )

    assert [item.hypothesis for item in report.ruled_out] == ["a network partition"]


# -- T011: metadata --------------------------------------------------------------


def test_metadata_records_the_capabilities_used_the_duration_and_the_cost() -> None:
    metadata = metadata_of(
        (entry("ev-1"), entry("ev-2", "logs-search"), entry("ev-3", "metrics-query")),
        run_id="run-1",
        run_link="https://ninjasre.invalid/runs/run-1",
        started_at=STARTED,
        finished_at=FINISHED,
        cost_usd=0.19,
        prompt_tokens=1_200,
        completion_tokens=300,
        model_id="a-model",
        team_node_id="team-payments",
    )

    assert metadata.capabilities_used == ("logs-search", "metrics-query")
    assert metadata.duration_seconds == 240.0
    assert metadata.cost_usd == 0.19
    assert metadata.total_tokens == 1_500
    assert metadata.run_link == "https://ninjasre.invalid/runs/run-1"
    assert metadata.model_id == "a-model"
    assert metadata.team_node_id == "team-payments"


def test_metadata_reaches_the_report() -> None:
    metadata = ReportMetadata(run_id="run-1", run_link="https://ninjasre.invalid/runs/run-1")

    report = build_report(
        diagnosis(), run_id="run-1", title="t", evidence=(entry("ev-1"),), metadata=metadata
    )

    assert report.metadata.run_link == "https://ninjasre.invalid/runs/run-1"


def test_remediation_steps_become_immediate_recommended_actions() -> None:
    report = build_report(diagnosis(), run_id="run-1", title="t", evidence=(entry("ev-1"),))

    assert [action.action for action in report.actions_for(Horizon.IMMEDIATE)] == [
        "Raise the pool ceiling to 40"
    ]


def test_a_caller_may_classify_actions_by_horizon_itself() -> None:
    report = build_report(
        diagnosis(),
        run_id="run-1",
        title="t",
        evidence=(entry("ev-1"),),
        actions=(RecommendedAction(action="Add an alert", horizon=Horizon.PREVENTIVE),),
    )

    assert report.actions_for(Horizon.IMMEDIATE) == ()
    assert [action.action for action in report.actions_for(Horizon.PREVENTIVE)] == ["Add an alert"]


# -- T012/FR-005: guardrails before any formatting -------------------------------


def secret_ruleset() -> Ruleset:
    """Return a ruleset that redacts a token shape."""
    return Ruleset(
        rules=(
            GuardrailRule(
                name="test-token",
                patterns=(re.compile(r"tok_[A-Za-z0-9]{6,}"),),
                action=GuardrailAction.REDACT,
                replacement="[REDACTED]",
            ),
        )
    )


def test_a_report_is_screened_before_anything_formats_it() -> None:
    leaking = build_report(
        diagnosis(
            root_cause="The service used tok_abcdef123456 in a query string.",
            summary="Something leaked tok_abcdef123456 into the logs.",
            causal_chain=("tok_abcdef123456 was logged",),
            validated_claims=(
                Claim(statement="tok_abcdef123456 appears in the log", evidence_ids=("ev-1",)),
            ),
            remediation_steps=("Rotate tok_abcdef123456",),
        ),
        run_id="run-1",
        title="tok_abcdef123456 leaked",
        evidence=(entry("ev-1"),),
        ruled_out=(RuledOut(hypothesis="tok_abcdef123456 rotation", reason="tok_abcdef123456"),),
    )

    clean = screened(leaking, engine=GuardrailEngine(ruleset=secret_ruleset()))

    rendered = str(clean.to_record())
    assert "tok_abcdef123456" not in rendered
    assert "[REDACTED]" in clean.root_cause
    assert "[REDACTED]" in clean.summary
    assert "[REDACTED]" in clean.title
    assert "[REDACTED]" in clean.causal_chain[0]
    assert "[REDACTED]" in clean.validated_claims[0].statement
    assert "[REDACTED]" in clean.recommended_actions[0].action
    assert "[REDACTED]" in clean.ruled_out[0].hypothesis


def test_screening_a_clean_report_changes_nothing() -> None:
    report = build_report(diagnosis(), run_id="run-1", title="t", evidence=(entry("ev-1"),))

    assert screened(report, engine=GuardrailEngine(ruleset=secret_ruleset())) == report


def test_screening_keeps_the_evidence_citation_intact() -> None:
    report = build_report(diagnosis(), run_id="run-1", title="t", evidence=(entry("ev-1"),))

    clean = screened(report, engine=GuardrailEngine(ruleset=secret_ruleset()))

    assert [item.evidence_id for item in clean.validated_claims[0].evidence] == ["ev-1"]


def test_the_summary_notice_is_not_part_of_an_unsummarised_report() -> None:
    report = build_report(diagnosis(), run_id="run-1", title="t", evidence=(entry("ev-1"),))

    assert REPORT_SUMMARY_NOTICE not in report.summary
