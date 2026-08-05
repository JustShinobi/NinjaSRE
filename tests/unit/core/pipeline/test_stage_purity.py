"""No stage writes outside the fields the ownership table gives it.

Pure-function stages are only pure if nothing writes outside its declared
slice, and convention does not survive twenty contributors — the third time
somebody needs one more field, "it was convenient" wins. So the table is data
and this is the test that reads it.

Each of the six stages is run against a state prepared far enough for it to do
its work, and what it actually changed is compared against what it declared.
The comparison is at ``slice.field`` granularity, because "the intake stage
writes the investigation slice" would be true of five of the six and would
enforce nothing.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.capability.metadata import CapabilityKind, ExcludedCapability
from core.domain.diagnosis.result import Diagnosis
from core.domain.diagnosis.taxonomy import RootCauseCategory
from core.pipeline.ownership import STAGE_WRITES, owners_of, violations, writes_of
from core.pipeline.ports import DeliveryPayload, FixedCatalogueResolver, StaticCatalogue
from core.pipeline.stage import Stage
from core.pipeline.stages.deliver import DeliverStage
from core.pipeline.stages.diagnose.node import DiagnoseStage
from core.pipeline.stages.gather_evidence import GatherEvidenceStage
from core.pipeline.stages.intake.node import IntakeStage
from core.pipeline.stages.plan_evidence import PlanEvidenceStage
from core.pipeline.stages.resolve_integrations import ResolveIntegrationsStage
from core.state.agent_state import AgentState, apply_state_updates, changed_paths
from core.state.types import STAGE_ORDER, SliceName, StageName
from tests.unit.core.pipeline.conftest import (
    ScriptedLLM,
    ScriptedRuntime,
    alertmanager_state,
    incident_classification,
    runtime_evidence,
    tool,
    turn,
)

pytestmark = pytest.mark.unit


class _Destination:
    """A destination that always accepts."""

    name = "slack"

    async def deliver(self, payload: DeliveryPayload) -> str:
        return "https://slack.example/message/1"


def _catalogue() -> StaticCatalogue:
    found = tool("datadog_log_statistics")
    return StaticCatalogue(
        tools=(found,),
        declarations=(found.metadata,),
        excluded=(
            ExcludedCapability(
                name="kubernetes_pod_events", kind=CapabilityKind.TOOL, unmet=("kubernetes",)
            ),
        ),
    )


def _diagnosis() -> Diagnosis:
    return Diagnosis(
        root_cause="the checkout container exceeded its memory limit",
        root_cause_category=RootCauseCategory.RESOURCE_EXHAUSTION,
        confidence=0.8,
    )


async def _through(stages: list[Stage], state: AgentState) -> AgentState:
    """Return ``state`` after every stage in ``stages`` has run and merged."""
    for stage in stages:
        state = apply_state_updates(state, await stage(state))
    return state


def _stages() -> dict[StageName, Stage]:
    return {
        StageName.RESOLVE_INTEGRATIONS: ResolveIntegrationsStage(
            FixedCatalogueResolver(_catalogue())
        ),
        StageName.INTAKE: IntakeStage(llm=ScriptedLLM(structured=[incident_classification()])),
        StageName.PLAN_EVIDENCE: PlanEvidenceStage(),
        StageName.GATHER_EVIDENCE: GatherEvidenceStage(
            runtime=ScriptedRuntime(evidence=(runtime_evidence(),), turns=(turn(),))
        ),
        StageName.DIAGNOSE: DiagnoseStage(
            llm=ScriptedLLM(
                structured=[
                    {
                        "root_cause": "the checkout container exceeded its memory limit",
                        "root_cause_category": "resource_exhaustion",
                        "summary": "OOM-killed",
                        "causal_chain": ["limit reached"],
                        "claims": [
                            {"statement": "the container was OOM-killed", "evidence_ids": ["e1"]}
                        ],
                        "remediation_steps": ["raise the limit"],
                        "confidence": 0.8,
                    }
                ]
            )
        ),
        StageName.DELIVER: DeliverStage(destinations=(_Destination(),)),
    }


async def _prepared_for(name: StageName) -> tuple[Stage, AgentState]:
    """Return the stage and a state prepared by everything that runs before it."""
    stages = _stages()
    preceding = [stages[earlier] for earlier in STAGE_ORDER[: STAGE_ORDER.index(name)]]
    state = await _through(preceding, alertmanager_state())

    if name is StageName.DELIVER:
        state = replace(state, investigation=replace(state.investigation, diagnosis=_diagnosis()))
    return stages[name], state


# -- the table itself ---------------------------------------------------------


def test_every_stage_declares_what_it_writes() -> None:
    assert set(STAGE_WRITES) == set(STAGE_ORDER)


def test_no_declared_path_names_a_slice_that_does_not_exist() -> None:
    slices = {member.value for member in SliceName}

    for stage, paths in STAGE_WRITES.items():
        for path in paths:
            head, _, field = path.partition(".")
            assert head in slices, f"{stage.value} declares an unknown slice in {path!r}"
            assert field, f"{stage.value} declares {path!r} without a field"


def test_the_diagnosis_has_exactly_one_writer() -> None:
    """The whole point of the partition: nothing but ``diagnose`` may write the
    conclusion the report is built from."""
    assert owners_of("investigation.diagnosis") == (StageName.DIAGNOSE,)
    assert owners_of("evidence.entries") == (StageName.GATHER_EVIDENCE,)


def test_the_approval_and_memory_slices_have_no_writer_yet() -> None:
    """Declared now because the shape has to settle before the features that
    fill them land; a writer that does not exist would permit a write nobody
    makes."""
    assert owners_of("approvals.requests") == ()
    assert owners_of("memory.episode_id") == ()


# -- the property -------------------------------------------------------------


@pytest.mark.parametrize("name", list(STAGE_ORDER), ids=lambda name: name.value)
async def test_a_stage_writes_only_what_it_declared(name: StageName) -> None:
    stage, state = await _prepared_for(name)

    merged = apply_state_updates(state, await stage(state))
    changed = changed_paths(state, merged)

    assert violations(name, changed) == (), (
        f"{name.value} wrote outside its declared slice; either the write is a "
        f"defect or {name.value}'s entry in the ownership table needs the field"
    )


@pytest.mark.parametrize("name", list(STAGE_ORDER), ids=lambda name: name.value)
async def test_a_stage_does_something(name: StageName) -> None:
    """A purity test passes trivially for a stage that writes nothing at all."""
    stage, state = await _prepared_for(name)

    merged = apply_state_updates(state, await stage(state))

    assert changed_paths(state, merged), f"{name.value} changed nothing"


async def test_the_check_catches_a_stage_that_strays() -> None:
    """The control case. Without it this suite proves only that the six stages
    happen to behave, not that the check would notice if one stopped."""
    stage, state = await _prepared_for(StageName.DIAGNOSE)
    honest = await stage(state)

    straying = replace(
        honest, evidence=state.evidence.extended((state.evidence.entries[0].cite(),))
    )
    merged = apply_state_updates(state, straying)

    assert violations(StageName.DIAGNOSE, changed_paths(state, merged)) == ("evidence.entries",)


def test_the_accounting_fields_are_shared_by_the_stages_that_spend() -> None:
    """A run that accounted only for the loop's tokens would under-report its
    own cost, which is the number an operator decides on."""
    spenders = owners_of("accounting.llm_calls")

    assert set(spenders) == {
        StageName.INTAKE,
        StageName.GATHER_EVIDENCE,
        StageName.DIAGNOSE,
    }
    assert "accounting.iterations" not in writes_of(StageName.INTAKE)
