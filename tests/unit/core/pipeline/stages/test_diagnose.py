"""Diagnosis is where Article I stops being a principle and becomes a check.

A claim citing evidence the run does not hold is demoted, whichever path
produced it — the structured call or the fallback parser. The taxonomy version
travels on every result, so a corpus scored against two versions is visibly
scored against two versions.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.capability.metadata import EvidenceType
from core.domain.diagnosis.result import Claim, Diagnosis
from core.domain.diagnosis.taxonomy import TAXONOMY_VERSION, RootCauseCategory
from core.llm.failures import FailureClass
from core.pipeline.stages.diagnose.fallback import classify, parse_conclusion
from core.pipeline.stages.diagnose.models import DIAGNOSIS_SCHEMA, diagnosis_from_structured
from core.pipeline.stages.diagnose.node import DiagnoseStage, describe_evidence
from core.pipeline.stages.diagnose.validation import (
    unbacked_citations,
    uncited_evidence,
    validate,
)
from core.state.agent_state import AgentState, StateUpdates, apply_state_updates
from core.state.evidence import EvidenceEntry, Provenance
from core.state.slices import EvidenceSlice
from core.state.types import StageName
from tests.unit.core.pipeline.conftest import AT, ScriptedLLM, alertmanager_state

pytestmark = pytest.mark.unit

CONCLUSION = (
    "The checkout container exceeded its 512Mi memory limit and was OOM-killed [e1]. "
    "The restart loop began at 12:04 [e2]."
)


def _entry(identifier: str, summary: str = "412 errors in checkout") -> EvidenceEntry:
    return EvidenceEntry(
        id=identifier,
        capability="datadog_log_statistics",
        source="datadog",
        evidence_type=EvidenceType.LOG,
        summary=summary,
        payload="status=500 count=412",
        reference="query:abc",
        recorded_at=AT,
        provenance=Provenance(stage=StageName.GATHER_EVIDENCE),
    )


def _structured(**overrides: object) -> dict[str, object]:
    answer: dict[str, object] = {
        "root_cause": "the checkout container exceeded its memory limit",
        "root_cause_category": "resource_exhaustion",
        "summary": "The container was OOM-killed and restarted repeatedly.",
        "causal_chain": ["memory limit reached", "container killed", "requests failed"],
        "claims": [
            {"statement": "the container was OOM-killed", "evidence_ids": ["e1"]},
            {"statement": "the restart loop began at 12:04", "evidence_ids": ["e2"]},
        ],
        "remediation_steps": ["raise the memory limit to 1Gi", "profile the allocation growth"],
        "confidence": 0.82,
    }
    answer.update(overrides)
    return answer


def _state(*entries: EvidenceEntry, conclusion: str = CONCLUSION) -> AgentState:
    base = alertmanager_state()
    return apply_state_updates(
        base,
        StateUpdates(
            evidence=EvidenceSlice(entries=entries),
            investigation=replace(base.investigation, conclusion=conclusion),
        ),
    )


# -- the structured call ------------------------------------------------------


async def test_the_conclusion_becomes_a_structured_diagnosis() -> None:
    llm = ScriptedLLM(structured=[_structured()])

    updates = await DiagnoseStage(llm)(_state(_entry("e1"), _entry("e2")))

    diagnosis = updates.investigation.diagnosis  # type: ignore[union-attr]
    assert diagnosis is not None
    assert diagnosis.root_cause_category is RootCauseCategory.RESOURCE_EXHAUSTION
    assert len(diagnosis.causal_chain) == 3
    assert len(diagnosis.validated_claims) == 2
    assert diagnosis.remediation_steps
    assert diagnosis.confidence == pytest.approx(0.82)
    assert not diagnosis.fallback_used


async def test_the_taxonomy_version_is_recorded_on_every_diagnosis() -> None:
    """Answer keys reference the vocabulary, so a corpus scored against two
    versions has to be visibly scored against two versions."""
    llm = ScriptedLLM(structured=[_structured()])

    updates = await DiagnoseStage(llm)(_state(_entry("e1")))

    assert updates.investigation.diagnosis.taxonomy_version == TAXONOMY_VERSION  # type: ignore[union-attr]


async def test_a_category_outside_the_taxonomy_becomes_unknown() -> None:
    llm = ScriptedLLM(structured=[_structured(root_cause_category="thundering_herd")])

    updates = await DiagnoseStage(llm)(_state(_entry("e1")))

    assert updates.investigation.diagnosis.root_cause_category is RootCauseCategory.UNKNOWN  # type: ignore[union-attr]


async def test_the_call_sees_the_evidence_identifiers_it_is_asked_to_cite() -> None:
    llm = ScriptedLLM(structured=[_structured()])

    await DiagnoseStage(llm)(_state(_entry("e1"), _entry("e2")))

    request = llm.requests[0].messages[0].text
    assert "[e1]" in request
    assert "[e2]" in request
    assert "resource_exhaustion" in request, "the closed taxonomy travels with the call"


async def test_the_schema_bounds_every_list_it_asks_for() -> None:
    for field in ("causal_chain", "claims", "remediation_steps"):
        assert "maxItems" in DIAGNOSIS_SCHEMA["properties"][field]  # type: ignore[index]


async def test_the_call_is_accounted_for() -> None:
    llm = ScriptedLLM(structured=[_structured()])

    updates = await DiagnoseStage(llm)(_state(_entry("e1")))

    assert updates.accounting is not None
    assert updates.accounting.llm_calls == 1


def test_the_stage_names_itself() -> None:
    assert DiagnoseStage(ScriptedLLM()).name is StageName.DIAGNOSE


# -- claim validation ---------------------------------------------------------


async def test_a_claim_citing_evidence_the_run_does_not_hold_is_demoted() -> None:
    """The sentence reads exactly like a finding and is a hypothesis."""
    llm = ScriptedLLM(
        structured=[
            _structured(
                claims=[
                    {"statement": "the container was OOM-killed", "evidence_ids": ["e1"]},
                    {"statement": "a deploy went out at 12:00", "evidence_ids": ["e7"]},
                ]
            )
        ]
    )

    updates = await DiagnoseStage(llm)(_state(_entry("e1")))

    diagnosis = updates.investigation.diagnosis  # type: ignore[union-attr]
    assert diagnosis is not None
    assert [claim.statement for claim in diagnosis.validated_claims] == [
        "the container was OOM-killed"
    ]
    assert [claim.statement for claim in diagnosis.non_validated_claims] == [
        "a deploy went out at 12:00"
    ]


async def test_a_claim_citing_nothing_is_demoted() -> None:
    llm = ScriptedLLM(
        structured=[
            _structured(claims=[{"statement": "the cluster is under pressure", "evidence_ids": []}])
        ]
    )

    updates = await DiagnoseStage(llm)(_state(_entry("e1")))

    diagnosis = updates.investigation.diagnosis  # type: ignore[union-attr]
    assert diagnosis is not None
    assert diagnosis.validated_claims == ()
    assert len(diagnosis.non_validated_claims) == 1


async def test_a_demoted_claim_is_kept_rather_than_dropped() -> None:
    """It is what the investigation believed and could not show, which is often
    the most interesting thing in the report."""
    llm = ScriptedLLM(
        structured=[_structured(claims=[{"statement": "probably a leak", "evidence_ids": []}])]
    )

    updates = await DiagnoseStage(llm)(_state())

    diagnosis = updates.investigation.diagnosis  # type: ignore[union-attr]
    assert diagnosis is not None
    assert "probably a leak" in [claim.statement for claim in diagnosis.claims]


def test_the_validity_score_is_arithmetic_over_the_split() -> None:
    diagnosis = Diagnosis(
        validated_claims=(Claim(statement="a", evidence_ids=("e1",)),),
        non_validated_claims=(
            Claim(statement="b"),
            Claim(statement="c"),
        ),
    )

    assert diagnosis.validity_score == pytest.approx(1 / 3)


def test_a_diagnosis_that_asserted_nothing_scores_zero() -> None:
    assert Diagnosis().validity_score == 0.0


def test_a_well_supported_claim_the_model_filed_as_unvalidated_is_promoted() -> None:
    diagnosis = Diagnosis(
        non_validated_claims=(Claim(statement="the pod restarted", evidence_ids=("e1",)),)
    )

    validated = validate(diagnosis, EvidenceSlice(entries=(_entry("e1"),)))

    assert len(validated.validated_claims) == 1
    assert validated.non_validated_claims == ()


def test_an_invented_identifier_is_reported_separately_from_an_uncited_claim() -> None:
    diagnosis = Diagnosis(
        validated_claims=(
            Claim(statement="a", evidence_ids=("e1", "e9")),
            Claim(statement="b"),
        )
    )
    evidence = EvidenceSlice(entries=(_entry("e1"), _entry("e2")))

    assert unbacked_citations(diagnosis, evidence) == ("e9",)
    assert uncited_evidence(diagnosis, evidence) == ("e2",)


# -- the fallback -------------------------------------------------------------


async def test_a_structured_output_failure_still_yields_a_usable_diagnosis() -> None:
    """An investigation that gathered eleven observations and then reported
    nothing has thrown away the expensive part to protect the cheap part."""
    llm = ScriptedLLM(
        structured=[None],
        failure=FailureClass.SCHEMA_REJECTED,
        failure_message="the model returned prose",
    )

    updates = await DiagnoseStage(llm)(_state(_entry("e1"), _entry("e2")))

    diagnosis = updates.investigation.diagnosis  # type: ignore[union-attr]
    assert diagnosis is not None
    assert diagnosis.fallback_used
    assert diagnosis.root_cause
    assert "fallback parser" in diagnosis.summary
    assert len(diagnosis.validated_claims) == 2, "citations in the prose were recovered"


async def test_the_fallbacks_claims_are_validated_too() -> None:
    """The fallback's citations are exactly as unverified as the model's."""
    llm = ScriptedLLM(structured=[None], failure=FailureClass.SCHEMA_REJECTED)

    updates = await DiagnoseStage(llm)(_state(_entry("e1")))

    diagnosis = updates.investigation.diagnosis  # type: ignore[union-attr]
    assert diagnosis is not None
    assert [claim.evidence_ids for claim in diagnosis.validated_claims] == [("e1",)]
    assert [claim.evidence_ids for claim in diagnosis.non_validated_claims] == [("e2",)]


def test_the_fallback_reads_an_explicit_root_cause_heading() -> None:
    parsed = parse_conclusion(
        "Investigation notes follow.\n"
        "Root cause: the checkout pod exceeded its memory limit.\n"
        "Remediation:\n- raise the limit\n- profile the allocations\n"
    )

    assert parsed.root_cause == "the checkout pod exceeded its memory limit."
    assert parsed.remediation_steps == ("raise the limit", "profile the allocations")
    assert parsed.fallback_used


def test_the_fallback_classifies_on_the_categories_own_vocabulary() -> None:
    assert (
        classify("The container ran out of memory and its connection pool slots were exhausted.")
        is RootCauseCategory.RESOURCE_EXHAUSTION
    )
    assert (
        classify("A DNS resolution failure between the load balancer and the service.")
        is RootCauseCategory.NETWORK_FAILURE
    )


def test_the_fallback_answers_unknown_rather_than_guessing() -> None:
    """A conclusion that matches nothing has not identified a category, and
    guessing is the mistake the closed taxonomy exists to make visible."""
    assert classify("Something went wrong somewhere.") is RootCauseCategory.UNKNOWN


def test_an_empty_conclusion_still_produces_a_marked_diagnosis() -> None:
    parsed = parse_conclusion("", note="structured output was unavailable")

    assert parsed.fallback_used
    assert parsed.root_cause_category is RootCauseCategory.UNKNOWN
    assert parsed.summary == "structured output was unavailable"


def test_the_fallback_confidence_is_zero() -> None:
    """A parser that recovered a sentence has no basis for a confidence."""
    assert parse_conclusion(CONCLUSION).confidence == 0.0


# -- prompt construction ------------------------------------------------------


def test_the_evidence_listing_leads_with_the_identifier() -> None:
    listing = describe_evidence(EvidenceSlice(entries=(_entry("e1"),)))

    assert listing.startswith("[e1]")
    assert "datadog" in listing


def test_a_run_with_no_evidence_says_so_and_says_what_follows() -> None:
    listing = describe_evidence(EvidenceSlice())

    assert "unvalidated" in listing


def test_a_malformed_structured_answer_yields_a_diagnosis_rather_than_raising() -> None:
    diagnosis = diagnosis_from_structured(
        {"root_cause": "x", "claims": ["not an object", {"statement": ""}], "confidence": "high"}
    )

    assert diagnosis.root_cause == "x"
    assert diagnosis.validated_claims == ()
    assert diagnosis.confidence == 0.0
