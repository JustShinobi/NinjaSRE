"""Gathering is thin, and the three things it owns are the three tested here.

The request the runtime is given, the provenance every observation carries out
of it, and the window enforcement that keeps a time-bounded call answering the
question this investigation is asking.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from config.constants.investigation import (
    CONTEXT_PLAN,
    CONTEXT_WINDOW_END,
    CONTEXT_WINDOW_START,
)
from core.agent.hooks.types import ALLOW, HookPoint, Rewrite, ToolContext
from core.agent.runtime_port import RunStatus
from core.agent.session import Session
from core.agent.turn import ToolExecution
from core.capability.telemetry import InvocationOutcome
from core.domain.alerts.window import IncidentWindow
from core.domain.correlation.planning import EvidencePlan, PlannedAction
from core.llm.types import ToolCall
from core.pipeline.build import investigation_hooks
from core.pipeline.runtime_bridge import events_for_turns
from core.pipeline.stages.gather_evidence import GatherEvidenceStage
from core.pipeline.stages.window_guard import (
    IncidentWindowGuard,
    clamp_arguments,
    window_of,
)
from core.pipeline.streaming import EventStream, PipelineEventKind, RecordingSink
from core.state.agent_state import AgentState, StateUpdates, apply_state_updates
from core.state.types import OutcomeKind, StageName
from tests.unit.core.pipeline.conftest import (
    AT,
    ScriptedLLM,
    ScriptedRuntime,
    alertmanager_state,
    incident_classification,
    runtime_evidence,
    tool,
    turn,
)
from tests.unit.core.pipeline.stages.test_intake import _stage as intake_stage

pytestmark = pytest.mark.unit

WINDOW = IncidentWindow(
    start=AT - timedelta(minutes=25), end=AT, derivation="from the alert's own start time"
)


async def _prepared() -> AgentState:
    """Return a state that has been through intake."""
    state = alertmanager_state()
    return apply_state_updates(
        state, await intake_stage(ScriptedLLM(structured=[incident_classification()]))(state)
    )


# -- the request --------------------------------------------------------------


async def test_the_runtime_is_told_what_to_investigate_and_inside_which_window() -> None:
    runtime = ScriptedRuntime()
    state = await _prepared()

    await GatherEvidenceStage(runtime=runtime)(state)

    request = runtime.requests[0]
    assert "HighErrorRate" in request.objective
    assert "checkout" in request.objective
    assert request.alert_source == "alertmanager"
    assert request.session_id == "run-1"
    assert CONTEXT_WINDOW_START in request.context
    assert CONTEXT_WINDOW_END in request.context


async def test_a_defaulted_window_is_declared_as_one_in_the_objective() -> None:
    """The loop must not be handed a guess presented as a measurement."""
    runtime = ScriptedRuntime()
    state = await _prepared()
    guessed = apply_state_updates(
        state,
        StateUpdates(
            investigation=replace(
                state.investigation,
                window=IncidentWindow.default_ending_at(AT, derivation="nothing said when"),
            )
        ),
    )

    await GatherEvidenceStage(runtime=runtime)(guessed)

    assert "low confidence" in runtime.requests[0].objective


async def test_the_plan_travels_with_the_request() -> None:
    runtime = ScriptedRuntime()
    state = await _prepared()
    planned = apply_state_updates(
        state,
        StateUpdates(
            investigation=replace(
                state.investigation,
                plan=EvidencePlan(
                    actions=(PlannedAction(capability="datadog_log_statistics", score=4.0),),
                    rationale="the alert names a Datadog monitor",
                ),
            )
        ),
    )

    await GatherEvidenceStage(runtime=runtime)(planned)

    assert runtime.requests[0].context[CONTEXT_PLAN] == "datadog_log_statistics"


async def test_an_empty_plan_carries_no_key_rather_than_an_empty_one() -> None:
    runtime = ScriptedRuntime()

    await GatherEvidenceStage(runtime=runtime)(await _prepared())

    assert CONTEXT_PLAN not in runtime.requests[0].context


async def test_gathering_without_an_alert_raises_rather_than_investigating_nothing() -> None:
    stage = GatherEvidenceStage(runtime=ScriptedRuntime())

    with pytest.raises(ValueError, match="no alert"):
        await stage(alertmanager_state())


# -- provenance ---------------------------------------------------------------


async def test_every_observation_carries_where_it_came_from() -> None:
    runtime = ScriptedRuntime(evidence=(runtime_evidence(),), turns=(turn(),))
    state = await _prepared()

    updates = await GatherEvidenceStage(runtime=runtime)(state)

    assert updates.evidence is not None
    entry = updates.evidence.entries[0]
    assert entry.id == "e1"
    assert entry.capability == "datadog_log_statistics"
    assert entry.source == "datadog"
    assert entry.provenance.runtime == "ninjasre.react"
    assert entry.provenance.session_id == "run-1"
    assert entry.provenance.stage is StageName.GATHER_EVIDENCE
    assert entry.recorded_at.tzinfo is not None


async def test_an_observation_carries_the_arguments_that_produced_it() -> None:
    """A summary with no query behind it cannot be checked by anyone who was
    not there."""
    runtime = ScriptedRuntime(evidence=(runtime_evidence(),), turns=(turn(),))
    state = await _prepared()

    updates = await GatherEvidenceStage(runtime=runtime)(state)

    assert updates.evidence is not None
    assert updates.evidence.entries[0].arguments == {"query": "service:checkout status:error"}


async def test_a_sub_agents_finding_says_a_specialist_reported_it() -> None:
    finding = runtime_evidence("e2", origin="log_analyst", summary="the errors start at 12:04")
    runtime = ScriptedRuntime(evidence=(runtime_evidence(), finding), turns=(turn(),))
    state = await _prepared()

    updates = await GatherEvidenceStage(runtime=runtime)(state)

    assert updates.evidence is not None
    reported = updates.evidence.entries[1]
    assert reported.provenance.from_subagent
    assert "log_analyst" in reported.provenance.describe()


async def test_the_run_is_accounted_for() -> None:
    runtime = ScriptedRuntime(evidence=(runtime_evidence(),), turns=(turn(), turn(2)))
    state = await _prepared()

    updates = await GatherEvidenceStage(runtime=runtime)(state)

    assert updates.accounting is not None
    assert updates.accounting.capability_executions == 2
    assert updates.accounting.runtime == "ninjasre.react"
    assert updates.accounting.status == RunStatus.COMPLETED.value
    assert updates.accounting.llm_calls >= 2


async def test_a_failed_run_still_records_what_it_gathered() -> None:
    """Eleven observations from an investigation that lost its model are eleven
    observations the operator would like."""
    runtime = ScriptedRuntime(
        evidence=(runtime_evidence(),),
        turns=(turn(),),
        status=RunStatus.FAILED,
        answer="",
        failure="the provider stopped answering",
    )
    state = await _prepared()

    updates = await GatherEvidenceStage(runtime=runtime)(state)

    assert updates.evidence is not None
    assert len(updates.evidence.entries) == 1
    assert updates.investigation is not None
    assert updates.investigation.outcome is not None
    assert updates.investigation.outcome.kind is OutcomeKind.FAILED
    assert not updates.investigation.outcome.halts, "a failed run still gets diagnosed"


async def test_what_the_deployment_established_travels_beside_what_the_stage_derived() -> None:
    """The stage builds the run request, so it is the only place this can be lost.

    A composition root knows things about the subject that no alert payload
    carries — which estate resource the alert resolved onto, and therefore
    which vendor holds it. That was measured mattering: a Redis alert resolved
    to Proxmox container 122 on pve01 was diagnosed as container 152 on pve02
    when the loop was handed the objective in prose and left to infer the rest.
    """
    runtime = ScriptedRuntime()
    state = await _prepared()

    await GatherEvidenceStage(runtime=runtime, context={"resource_name": "pve01"})(state)

    context = runtime.requests[0].context
    assert context["resource_name"] == "pve01"
    assert CONTEXT_WINDOW_START in context, "the stage's own context was displaced instead"


async def test_the_stage_keeps_its_own_reading_of_a_key_the_caller_also_named() -> None:
    """Derived from this run's state beats supplied by whoever composed it.

    Not a preference: the stage's values are computed from the state the five
    stages before it wrote, and a caller's copy of one of them is a snapshot
    taken before they ran.
    """
    runtime = ScriptedRuntime()
    state = await _prepared()

    await GatherEvidenceStage(runtime=runtime, context={CONTEXT_PLAN: "supplied"})(state)

    assert runtime.requests[0].context.get(CONTEXT_PLAN) != "supplied"


# -- the event bridge ---------------------------------------------------------


async def test_the_loops_turns_reach_the_pipeline_stream() -> None:
    sink = RecordingSink()
    runtime = ScriptedRuntime(evidence=(runtime_evidence(),), turns=(turn(),))
    state = await _prepared()

    await GatherEvidenceStage(runtime=runtime, stream=EventStream("run-1", (sink,)))(state)

    kinds = [event.kind for event in sink.events]
    assert PipelineEventKind.THOUGHT in kinds
    assert PipelineEventKind.TOOL_START in kinds
    assert PipelineEventKind.TOOL_END in kinds
    assert PipelineEventKind.EVIDENCE in kinds


def test_a_replayed_call_still_emits_its_lifecycle() -> None:
    """A stream that hid cache hits would show a run doing less work than the
    trajectory scorer thinks it did."""
    replayed = turn(
        executions=(
            ToolExecution(
                call_id="c9",
                capability="datadog_log_statistics",
                arguments={"query": "x"},
                replayed=True,
            ),
        )
    )

    events = events_for_turns((replayed,))

    ends = [event for event in events if event.kind is PipelineEventKind.TOOL_END]
    assert len(ends) == 1
    assert "cache" in ends[0].text
    assert not ends[0].failed


def test_a_denied_call_is_emitted_as_a_failure_with_its_reason() -> None:
    denied = turn(
        executions=(
            ToolExecution(
                call_id="c9",
                capability="restart_deployment",
                arguments={},
                outcome=InvocationOutcome.FAILURE,
                denied=True,
                error_message="waiting on human approval",
            ),
        )
    )

    ends = [
        event for event in events_for_turns((denied,)) if event.kind is PipelineEventKind.TOOL_END
    ]

    assert ends[0].failed
    assert "waiting on human approval" in ends[0].text


def test_a_sub_agent_dispatch_becomes_sub_agent_events() -> None:
    dispatch = turn(
        executions=(
            ToolExecution(
                call_id="c3",
                capability="dispatch_subagent",
                arguments={"subagent": "log_analyst", "task": "find when the errors start"},
            ),
        )
    )

    kinds = [event.kind for event in events_for_turns((dispatch,))]

    assert PipelineEventKind.SUBAGENT_START in kinds
    assert PipelineEventKind.SUBAGENT_END in kinds
    assert PipelineEventKind.TOOL_START not in kinds


# -- window enforcement -------------------------------------------------------


def test_a_range_wider_than_the_window_is_narrowed_to_it() -> None:
    arguments = {
        "query": "service:checkout",
        "start_time": (AT - timedelta(days=1)).isoformat(),
        "end_time": (AT + timedelta(hours=3)).isoformat(),
    }

    clamped = clamp_arguments(arguments, WINDOW)

    assert clamped is not None
    assert clamped["start_time"] == WINDOW.start.isoformat()
    assert clamped["end_time"] == WINDOW.end.isoformat()
    assert clamped["query"] == "service:checkout", "everything else is untouched"


def test_a_range_already_inside_the_window_is_left_alone() -> None:
    inside = {"since": (AT - timedelta(minutes=5)).isoformat()}

    assert clamp_arguments(inside, WINDOW) is None


def test_an_argument_that_is_not_a_time_is_left_alone() -> None:
    """The capability knows what it meant; rewriting a value this guard does
    not understand is how it breaks a working call."""
    assert clamp_arguments({"start": "beginning of the deploy"}, WINDOW) is None
    assert clamp_arguments({"until": None}, WINDOW) is None


def test_an_epoch_argument_comes_back_as_an_epoch_in_the_same_unit() -> None:
    seconds = int((AT - timedelta(days=2)).timestamp())
    milliseconds = int((AT - timedelta(days=2)).timestamp() * 1000)

    from_seconds = clamp_arguments({"start": seconds}, WINDOW)
    from_millis = clamp_arguments({"start": milliseconds}, WINDOW)

    assert from_seconds is not None
    assert from_seconds["start"] == int(WINDOW.start.timestamp())
    assert from_millis is not None
    assert from_millis["start"] == int(WINDOW.start.timestamp() * 1000)


def test_a_datetime_argument_comes_back_as_a_datetime() -> None:
    clamped = clamp_arguments({"start": AT - timedelta(days=1)}, WINDOW)

    assert clamped is not None
    assert isinstance(clamped["start"], datetime)
    assert clamped["start"] == WINDOW.start


def _tool_context(context: dict[str, str]) -> ToolContext:
    return ToolContext(
        session=Session(id="run-1", context=context),
        iteration=1,
        registered=tool("datadog_log_statistics"),
    )


async def test_the_guard_rewrites_rather_than_denying() -> None:
    """A denial would teach the model to stop asking for time ranges, which is
    the opposite of what the window is for."""
    guard = IncidentWindowGuard(WINDOW)
    call = ToolCall(
        id="c1",
        name="datadog_log_statistics",
        arguments={"start_time": (AT - timedelta(days=1)).isoformat()},
    )

    decision = await guard(call, _tool_context({}))

    assert isinstance(decision, Rewrite)
    assert decision.arguments["start_time"] == WINDOW.start.isoformat()
    assert WINDOW.start.isoformat() in decision.reason


async def test_the_guard_reads_the_window_from_the_session_it_is_guarding() -> None:
    """One guard instance serves every concurrent run; a captured window would
    be the previous incident's, applied to this one."""
    guard = IncidentWindowGuard()
    context = _tool_context(
        {
            CONTEXT_WINDOW_START: WINDOW.start.isoformat(),
            CONTEXT_WINDOW_END: WINDOW.end.isoformat(),
        }
    )
    call = ToolCall(
        id="c1",
        name="datadog_log_statistics",
        arguments={"start_time": (AT - timedelta(days=1)).isoformat()},
    )

    decision = await guard(call, context)

    assert isinstance(decision, Rewrite)
    assert decision.arguments["start_time"] == WINDOW.start.isoformat()


async def test_a_run_with_no_window_is_not_clamped_at_all() -> None:
    """A sub-agent, or a one-off question from a surface, has no incident to be
    bounded to."""
    guard = IncidentWindowGuard()
    call = ToolCall(id="c1", name="datadog_log_statistics", arguments={"start_time": "1999-01-01"})

    assert await guard(call, _tool_context({})) is ALLOW
    assert window_of({}) is None
    assert window_of({CONTEXT_WINDOW_START: "not a time", CONTEXT_WINDOW_END: "x"}) is None


def test_the_guard_is_attached_at_the_only_point_that_can_change_a_call() -> None:
    registry = investigation_hooks()

    assert len(registry.hooks_at(HookPoint.PRE_TOOL_USE)) == 1
    assert registry.hooks_at(HookPoint.POST_TOOL_USE) == ()
