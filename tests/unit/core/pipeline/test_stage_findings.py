"""What each stage says it did, and what it spent while doing it.

A trace grouped by stage is only worth more than a flat list of turns if each
group says something. Two of the six stages never produce a turn at all —
intake and diagnosis each make one model call of their own and hand back a
value — so a section for either of them would otherwise be a heading over
nothing, and the flat list it replaced was at least honest about that.

The line comes from the slice the stage owns, in the state the stage just
produced. Nothing here asks a model for a summary and nothing paraphrases the
report: a stage that established a countable fact says the count, and a stage
that established a sentence hands the sentence over.

The second half is the accounting delta, and it is the reason the run's
recorded token cost stops being a floor. Only the gathering stage produces
turns, so a total summed over turns silently leaves out both of the other
model calls the run made.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from config.constants.runs import (
    STAGE_DETAIL_COMPLETION_TOKENS,
    STAGE_DETAIL_FINDING,
    STAGE_DETAIL_LLM_CALLS,
    STAGE_DETAIL_PROMPT_TOKENS,
)
from core.capability.metadata import EvidenceType
from core.domain.correlation.fingerprint import IncidentLink
from core.domain.diagnosis.result import Claim, DeliveryAttempt, DeliveryOutcome, Diagnosis
from core.llm.usage import TokenCounts
from core.pipeline.findings import finding_for
from core.pipeline.lifecycle import Pipeline
from core.pipeline.streaming import EventStream, PipelineEventKind, RecordingSink
from core.state.agent_state import AgentState, StateUpdates
from core.state.catalogue import ResolvedCapabilities
from core.state.evidence import EvidenceEntry
from core.state.slices import EvidenceSlice
from core.state.types import (
    IntakeClassification,
    InvestigationOutcome,
    OutcomeKind,
    StageName,
)
from tests.unit.core.pipeline.conftest import alertmanager_state

pytestmark = pytest.mark.unit


def _with(state: AgentState, **investigation: object) -> AgentState:
    """Return ``state`` with the named investigation fields replaced."""
    return replace(state, investigation=replace(state.investigation, **investigation))


def _observation(identifier: str, summary: str) -> EvidenceEntry:
    """Return one observation the run holds."""
    return EvidenceEntry(
        id=identifier,
        capability="proxmox_quorum_status",
        source="proxmox",
        evidence_type=EvidenceType.METRIC,
        summary=summary,
    )


class TestEachStageSaysWhatItEstablished:
    def test_resolving_says_how_many_capabilities_the_team_can_call(self) -> None:
        state = _with(
            alertmanager_state(),
            catalogue=ResolvedCapabilities(available=("a", "b", "c")),
        )

        assert (
            finding_for(StageName.RESOLVE_INTEGRATIONS, state)
            == "3 capabilities available on this team"
        )

    def test_resolving_says_so_when_the_team_can_call_nothing(self) -> None:
        assert (
            finding_for(StageName.RESOLVE_INTEGRATIONS, alertmanager_state())
            == "No capability on this team can serve this alert"
        )

    def test_intake_says_this_is_a_new_incident(self) -> None:
        state = _with(
            alertmanager_state(),
            classification=IntakeClassification(is_incident=True, confidence=0.95, reason="fires"),
        )

        assert (
            finding_for(StageName.INTAKE, state)
            == "A new incident, not a repeat of one already open"
        )

    def test_intake_names_the_incident_a_repeat_was_attached_to(self) -> None:
        state = _with(
            alertmanager_state(),
            classification=IntakeClassification(is_incident=True, confidence=0.9, reason="fires"),
            link=IncidentLink(incident_id="inc-7", fingerprint="fp"),
        )

        assert finding_for(StageName.INTAKE, state) == "Attached to incident inc-7, already open"

    def test_intake_repeats_its_own_reason_for_calling_something_noise(self) -> None:
        state = _with(
            alertmanager_state(),
            classification=IntakeClassification(
                is_incident=False, confidence=0.96, reason="a greeting, not a report"
            ),
        )

        assert finding_for(StageName.INTAKE, state) == "Not an incident: a greeting, not a report"

    def test_gathering_counts_the_observations_rather_than_paraphrasing_the_report(self) -> None:
        # Never a sentence lifted out of the conclusion. The report opens on a
        # heading and the run's own one-line summary is already at the top of
        # the card; a stage line that cut prose out of either would be the
        # console's headline a second time, one section down.
        state = replace(
            _with(alertmanager_state(), conclusion="# Root cause\n\nThe guest was stopped."),
            evidence=EvidenceSlice(
                entries=(_observation("e1", "quorate"), _observation("e2", "stopped"))
            ),
        )

        assert finding_for(StageName.GATHER_EVIDENCE, state) == "2 observations gathered"

    def test_gathering_says_what_went_wrong_rather_than_counting_nothing(self) -> None:
        state = _with(
            alertmanager_state(),
            outcome=InvestigationOutcome(
                kind=OutcomeKind.FAILED, headline="The runtime produced nothing usable"
            ),
        )

        assert (
            finding_for(StageName.GATHER_EVIDENCE, state) == "The runtime produced nothing usable"
        )

    def test_diagnosis_counts_the_claims_an_observation_actually_backs(self) -> None:
        state = _with(
            alertmanager_state(),
            diagnosis=Diagnosis(
                validated_claims=(
                    Claim(statement="the guest is stopped", evidence_ids=("e1",)),
                    Claim(statement="a person stopped it", evidence_ids=("e2",)),
                ),
                non_validated_claims=(Claim(statement="nobody noticed"),),
            ),
        )

        assert (
            finding_for(StageName.DIAGNOSE, state)
            == "2 of 3 claims tied to an observation the run holds"
        )

    def test_delivery_hands_over_the_sentence_it_already_wrote(self) -> None:
        # The delivering stage is the one stage that already writes a sentence
        # saying where the report went, so this reads it rather than composing
        # a second one that could disagree with it.
        state = _with(
            alertmanager_state(),
            delivery=DeliveryOutcome(
                attempts=(DeliveryAttempt(destination="slack", delivered=True),)
            ),
            outcome=InvestigationOutcome(
                kind=OutcomeKind.DIAGNOSED, headline="h", detail="Delivered to slack."
            ),
        )

        assert finding_for(StageName.DELIVER, state) == "Delivered to slack."

    def test_a_stage_that_established_nothing_says_nothing(self) -> None:
        assert finding_for(StageName.DIAGNOSE, alertmanager_state()) == ""


class _Stage:
    """A stage that returns what a test told it to."""

    def __init__(self, name: StageName, updates: StateUpdates | None = None) -> None:
        self.name = name
        self._updates = updates if updates is not None else StateUpdates()

    async def __call__(self, state: AgentState) -> StateUpdates:
        return self._updates


class TestTheStreamCarriesTheFindingAndTheSpend:
    async def test_a_stage_end_carries_the_line_that_stage_wrote(self) -> None:
        sink = RecordingSink()
        state = alertmanager_state()
        pipeline = Pipeline(
            (
                _Stage(
                    StageName.RESOLVE_INTEGRATIONS,
                    StateUpdates(
                        investigation=replace(
                            state.investigation,
                            catalogue=ResolvedCapabilities(available=("a", "b")),
                        )
                    ),
                ),
            ),
            stream=EventStream("run-1", (sink,)),
        )

        await pipeline.run(state)

        ended = next(event for event in sink.events if event.kind is PipelineEventKind.STAGE_END)
        assert ended.detail[STAGE_DETAIL_FINDING] == "2 capabilities available on this team"

    async def test_a_stage_end_carries_what_that_stage_spent_and_not_the_run_so_far(self) -> None:
        # The delta, never the running total. Both intake and diagnosis add to
        # the same ledger, and a stage that reported the ledger would report
        # the previous stages' spend as its own.
        sink = RecordingSink()
        state = alertmanager_state()
        spent = replace(
            state.accounting,
            tokens=TokenCounts(input_tokens=900, output_tokens=120),
            llm_calls=1,
        )
        already = replace(state, accounting=spent)
        pipeline = Pipeline(
            (
                _Stage(
                    StageName.INTAKE,
                    StateUpdates(
                        accounting=replace(
                            spent,
                            tokens=spent.tokens + TokenCounts(input_tokens=300, output_tokens=40),
                            llm_calls=2,
                        )
                    ),
                ),
            ),
            stream=EventStream("run-1", (sink,)),
        )

        await pipeline.run(already)

        ended = next(event for event in sink.events if event.kind is PipelineEventKind.STAGE_END)
        assert ended.detail[STAGE_DETAIL_PROMPT_TOKENS] == "300"
        assert ended.detail[STAGE_DETAIL_COMPLETION_TOKENS] == "40"
        assert ended.detail[STAGE_DETAIL_LLM_CALLS] == "1"
