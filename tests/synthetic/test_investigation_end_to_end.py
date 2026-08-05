"""The whole pipeline over the canonical runtime, scored against an answer key.

Only the provider and the vendor backends are doubles. The loop, its execution
path, its evidence recording, the merge, the stream, and all six stages are the
real ones — a harness that stubbed the runtime too would prove the stages call
each other and nothing about whether an investigation works.

Three properties live here. A scenario produces a diagnosis whose category
matches its answer key; every validated claim, across the whole corpus,
references evidence the run actually holds; and replaying the persisted events
reconstructs the investigation.
"""

from __future__ import annotations

import pytest

from capabilities.registry.planning import CatalogueRanker
from core.agent.react_loop import ReActLoop
from core.domain.diagnosis.alignment import aligned, misalignment_note
from core.domain.diagnosis.taxonomy import TAXONOMY_VERSION, RootCauseCategory
from core.pipeline.build import build_pipeline, investigation_hooks
from core.pipeline.lifecycle import CollectingEndHook, PipelineRun
from core.pipeline.ports import FixedCatalogueResolver, InMemoryIncidentIndex
from core.pipeline.state_factory import initial_state
from core.pipeline.streaming import EventStream, PipelineEventKind, RecordingSink, replay
from core.state.types import STAGE_ORDER, OutcomeKind, StageName
from tests.synthetic.conftest import (
    CHATTER,
    CORPUS,
    DEPLOY_REGRESSION,
    OOM_KILL,
    RecordingDestination,
    Scenario,
)

pytestmark = pytest.mark.synthetic


async def _investigate(
    scenario: Scenario,
    *,
    destinations: tuple[RecordingDestination, ...] = (),
    sink: RecordingSink | None = None,
    end_hook: CollectingEndHook | None = None,
) -> PipelineRun:
    """Return the finished investigation of ``scenario``."""
    llm = scenario.llm()
    recorder = sink if sink is not None else RecordingSink()
    stream = EventStream("run-synthetic", (recorder,))

    pipeline = build_pipeline(
        llm=llm,
        runtime=ReActLoop(llm=llm, tools=scenario.tools, hooks=investigation_hooks()),
        resolver=FixedCatalogueResolver(scenario.catalogue()),
        ranker=CatalogueRanker(),
        incidents=InMemoryIncidentIndex(),
        destinations=destinations,
        stream=stream,
        end_hooks=(end_hook,) if end_hook is not None else (),
        strict=True,
    )
    return await pipeline.run(
        initial_state(scenario.raw, scenario.team, run_id=f"run-{scenario.key}")
    )


# -- the diagnosis matches the answer key -------------------------------------


@pytest.mark.parametrize(
    "scenario", [OOM_KILL, DEPLOY_REGRESSION], ids=lambda scenario: scenario.key
)
async def test_a_scenario_produces_the_category_its_answer_key_names(scenario: Scenario) -> None:
    run = await _investigate(scenario)

    diagnosis = run.state.investigation.diagnosis
    assert diagnosis is not None
    assert aligned(diagnosis.root_cause_category, scenario.expected_category), misalignment_note(
        diagnosis.root_cause_category, scenario.expected_category
    )
    assert diagnosis.taxonomy_version == TAXONOMY_VERSION
    assert not diagnosis.fallback_used


async def test_the_run_goes_through_every_stage() -> None:
    run = await _investigate(OOM_KILL)

    assert run.stages_run == STAGE_ORDER
    assert run.succeeded
    assert not run.halted_early


async def test_the_loop_actually_called_a_backend() -> None:
    """The evidence has to come from somewhere the run went and asked."""
    run = await _investigate(OOM_KILL)

    assert len(run.state.evidence) == 1
    entry = run.state.evidence.entries[0]
    assert entry.capability == "kubernetes_pod_events"
    assert entry.source == "kubernetes"
    assert entry.provenance.runtime == "ninjasre.react"
    assert entry.arguments["query"] == "pod=checkout-7f4c"


async def test_the_incident_window_was_enforced_on_the_backend_call() -> None:
    """Window enforcement end to end: the loop asked for a day and got the window."""
    run = await _investigate(OOM_KILL)

    window = run.state.investigation.window
    assert window is not None
    start = run.state.evidence.entries[0].arguments["start_time"]
    assert start == window.start.isoformat(), (
        "the loop asked for the last 24 hours; the guard should have narrowed it"
    )


async def test_the_plan_shortlisted_the_capability_the_loop_used() -> None:
    run = await _investigate(OOM_KILL)

    plan = run.state.investigation.plan
    assert "kubernetes_pod_events" in plan.capabilities
    assert plan.rationale


async def test_the_run_accounts_for_every_call_it_made() -> None:
    run = await _investigate(OOM_KILL)

    accounting = run.state.accounting
    assert accounting.capability_executions == 1
    assert accounting.llm_calls >= 4, "intake, two loop turns, and diagnosis"
    assert accounting.tokens.total_tokens > 0
    assert accounting.runtime == "ninjasre.react"


# -- every validated claim is backed, across the corpus -----------------------


@pytest.mark.parametrize("scenario", list(CORPUS), ids=lambda scenario: scenario.key)
async def test_every_validated_claim_references_evidence_the_run_holds(
    scenario: Scenario,
) -> None:
    run = await _investigate(scenario)
    diagnosis = run.state.investigation.diagnosis

    if diagnosis is None:
        assert not scenario.expects_investigation
        return

    held = run.state.evidence.ids
    for claim in diagnosis.validated_claims:
        assert claim.backed_by(held), (
            f"{scenario.key}: {claim.statement!r} is marked validated and cites "
            f"{claim.evidence_ids}, none of which the run holds ({sorted(held)})"
        )


async def test_an_unsupported_claim_is_kept_and_demoted() -> None:
    run = await _investigate(OOM_KILL)
    diagnosis = run.state.investigation.diagnosis

    assert diagnosis is not None
    assert [claim.statement for claim in diagnosis.non_validated_claims] == [
        "the growth is probably a leak in the cart serialiser"
    ]
    assert diagnosis.validity_score == pytest.approx(0.5)


# -- noise costs nothing ------------------------------------------------------


async def test_chatter_stops_before_a_single_capability_runs() -> None:
    run = await _investigate(CHATTER)

    assert run.outcome is not None
    assert run.outcome.kind is OutcomeKind.NOISE
    assert run.stages_run == (StageName.RESOLVE_INTEGRATIONS, StageName.INTAKE)
    assert len(run.state.evidence) == 0
    assert run.state.accounting.capability_executions == 0
    assert run.state.accounting.llm_calls == 1
    assert run.state.investigation.diagnosis is None


# -- the stream reconstructs the investigation --------------------------------


async def test_replaying_the_persisted_events_reconstructs_the_run() -> None:
    sink = RecordingSink()

    run = await _investigate(OOM_KILL, sink=sink)

    view = replay(
        [type(event).from_record(record) for event, record in zip(sink.events, sink.records())]
    )

    assert [found.stage for found in view.stages] == list(STAGE_ORDER)
    assert all(found.completed for found in view.stages)
    assert [call.capability for call in view.tool_calls] == ["kubernetes_pod_events"]
    assert view.evidence_ids == tuple(entry.id for entry in run.state.evidence.entries)
    assert view.result == run.outcome.headline  # type: ignore[union-attr]
    assert not view.failed


async def test_the_stream_carries_the_loops_reasoning() -> None:
    sink = RecordingSink()

    await _investigate(OOM_KILL, sink=sink)

    kinds = {event.kind for event in sink.events}
    assert PipelineEventKind.TOOL_START in kinds
    assert PipelineEventKind.TOOL_END in kinds
    assert PipelineEventKind.EVIDENCE in kinds


# -- delivery and the run-end hook --------------------------------------------


async def test_the_report_reaches_the_teams_destination() -> None:
    slack = RecordingDestination("slack")

    run = await _investigate(OOM_KILL, destinations=(slack,))

    assert len(slack.received) == 1
    assert slack.received[0].diagnosis.root_cause_category is RootCauseCategory.RESOURCE_EXHAUSTION
    assert run.state.investigation.delivery is not None
    assert run.state.investigation.delivery.complete


async def test_one_unreachable_destination_does_not_lose_the_investigation() -> None:
    broken = RecordingDestination("pagerduty", fails=True)
    good = RecordingDestination("slack")

    run = await _investigate(OOM_KILL, destinations=(broken, good))

    assert len(good.received) == 1
    delivery = run.state.investigation.delivery
    assert delivery is not None
    assert delivery.failed == ("pagerduty",)
    assert run.succeeded


@pytest.mark.parametrize("scenario", list(CORPUS), ids=lambda scenario: scenario.key)
async def test_the_run_end_hook_fires_once_per_investigation(scenario: Scenario) -> None:
    hook = CollectingEndHook()

    await _investigate(scenario, end_hook=hook)

    assert len(hook.runs) == 1
    assert hook.runs[0].state.investigation.outcome is not None


async def test_the_finished_state_round_trips_through_a_record() -> None:
    """A trace that cannot be written down and read back is a summary of an
    investigation rather than evidence of one."""
    import json

    from core.state.agent_state import AgentState

    run = await _investigate(OOM_KILL)

    restored = AgentState.from_record(json.loads(json.dumps(run.state.to_record())))

    assert restored.investigation.diagnosis == run.state.investigation.diagnosis
    assert restored.evidence.ids == run.state.evidence.ids
    assert restored.accounting.tokens.total_tokens == run.state.accounting.tokens.total_tokens
