"""State changes through one function, and that function's answers are checkable.

Two properties are load-bearing for the whole feature. The merge replaces whole
slices, so a stage's write is a value rather than a side effect; and
``changed_paths`` names what moved at the granularity the ownership table
declares in, because a coarser answer would make the purity test vacuous.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from core.capability.metadata import EvidenceType
from core.domain.alerts.normalisation import NormalisedAlert, RawAlert, Severity
from core.domain.alerts.sources import AlertSource
from core.domain.alerts.window import IncidentWindow
from core.domain.correlation.planning import EvidencePlan, PlannedAction
from core.domain.diagnosis.result import Claim, Diagnosis
from core.domain.diagnosis.taxonomy import RootCauseCategory
from core.llm.usage import TokenCounts
from core.state.agent_state import (
    NO_UPDATES,
    AgentState,
    StateUpdates,
    apply_state_updates,
    changed_paths,
)
from core.state.evidence import EvidenceEntry, Provenance
from core.state.slices import (
    AccountingSlice,
    ChatSlice,
    EvidenceSlice,
    InvestigationSlice,
)
from core.state.types import ChatMessage, SliceName, StageName, TeamContext

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _state() -> AgentState:
    return AgentState(
        run_id="run-1",
        team=TeamContext(team_id="payments", integrations=("datadog",)),
        raw=RawAlert(text="checkout is erroring", received_at=AT),
        started_at=AT,
    )


def _entry(identifier: str = "e1") -> EvidenceEntry:
    return EvidenceEntry(
        id=identifier,
        capability="datadog_log_statistics",
        source="datadog",
        evidence_type=EvidenceType.LOG,
        summary="412 errors in checkout",
        arguments={"query": "service:checkout status:error"},
        payload="status=500 count=412",
        recorded_at=AT,
        provenance=Provenance(stage=StageName.GATHER_EVIDENCE, session_id="s1", iteration=2),
    )


def test_a_new_state_carries_its_input_and_nothing_else() -> None:
    state = _state()

    assert state.investigation.alert is None
    assert state.investigation.plan.actions == ()
    assert len(state.evidence) == 0
    assert state.raw.text == "checkout is erroring"


def test_empty_updates_return_the_same_state() -> None:
    state = _state()

    assert apply_state_updates(state, NO_UPDATES) is state
    assert not NO_UPDATES


def test_a_merge_replaces_only_the_slices_the_update_names() -> None:
    state = _state()
    updates = StateUpdates(evidence=EvidenceSlice(entries=(_entry(),)))

    merged = apply_state_updates(state, updates)

    assert len(merged.evidence) == 1
    assert merged.chat is state.chat
    assert merged.investigation is state.investigation
    assert len(state.evidence) == 0, "the original state must not be mutated"


def test_slices_touched_reports_every_named_slice() -> None:
    updates = StateUpdates(chat=ChatSlice(), accounting=AccountingSlice())

    assert updates.slices_touched() == frozenset({SliceName.CHAT, SliceName.ACCOUNTING})
    assert bool(updates)


def test_changed_paths_names_the_field_that_moved_not_the_slice() -> None:
    state = _state()
    window = IncidentWindow(start=AT, end=AT, derivation="from the alert")
    merged = apply_state_updates(
        state, StateUpdates(investigation=replace(state.investigation, window=window))
    )

    assert changed_paths(state, merged) == frozenset({"investigation.window"})


def test_changed_paths_reports_nothing_when_a_slice_is_rebuilt_identically() -> None:
    """A stage that put the same values back has written nothing observable, and
    reporting that as a write would fail the purity test on a stage that behaved."""
    state = _state()
    rebuilt = apply_state_updates(state, StateUpdates(investigation=InvestigationSlice()))

    assert changed_paths(state, rebuilt) == frozenset()


def test_changed_paths_spans_several_slices() -> None:
    state = _state()
    merged = apply_state_updates(
        state,
        StateUpdates(
            evidence=EvidenceSlice(entries=(_entry(),)),
            accounting=AccountingSlice(llm_calls=2, iterations=3),
        ),
    )

    assert changed_paths(state, merged) == frozenset(
        {"evidence.entries", "accounting.llm_calls", "accounting.iterations"}
    )


def test_state_round_trips_through_json() -> None:
    state = apply_state_updates(
        _state(),
        StateUpdates(
            chat=ChatSlice(
                messages=(ChatMessage(author="erik", text="is checkout down?", at=AT),),
                channel="#incidents",
            ),
            investigation=InvestigationSlice(
                alert=NormalisedAlert(
                    alert_source=AlertSource.ALERTMANAGER,
                    alert_name="HighErrorRate",
                    severity=Severity.CRITICAL,
                    summary="error rate above 5%",
                    components=("checkout",),
                    started_at=AT,
                    labels={"severity": "critical"},
                ),
                window=IncidentWindow(start=AT, end=AT, derivation="from startsAt"),
                plan=EvidencePlan(
                    actions=(PlannedAction(capability="datadog_log_statistics", score=4.0),),
                    rationale="the alert names a Datadog monitor",
                ),
                conclusion="the checkout pod was OOM-killed",
                diagnosis=Diagnosis(
                    root_cause="the checkout container exceeded its memory limit",
                    root_cause_category=RootCauseCategory.RESOURCE_EXHAUSTION,
                    validated_claims=(Claim(statement="the pod restarted", evidence_ids=("e1",)),),
                    confidence=0.8,
                ),
            ),
            evidence=EvidenceSlice(entries=(_entry(),)),
            accounting=AccountingSlice(
                tokens=TokenCounts(input_tokens=100, output_tokens=20),
                llm_calls=2,
                iterations=4,
                runtime="ninjasre.react",
                status="completed",
            ),
        ),
    )

    restored = AgentState.from_record(json.loads(json.dumps(state.to_record())))

    assert restored == state


def test_a_run_must_be_identified() -> None:
    with pytest.raises(ValueError, match="identifier"):
        AgentState(run_id="  ")
