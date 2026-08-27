"""Carrying the stage from the pipeline's stream onto the run's own trace.

The two halves of an investigation were written down on different channels and
neither knew about the other. The pipeline announces ``stage_start`` and
``stage_end`` on its ``EventStream``; the recorder writes turns and calls from
the loop's ``on_turn_end``. So the trace held sixteen numbered turns and no
answer at all to "which part of the investigation was this".

The seam asserted here is the recording hook subscribing to that stream. A
pipeline runs its stages strictly in order over one run, so the stage that is
open when a turn ends *is* the stage the turn belonged to — read, not guessed
at, and it is the only correlation that would still be true if the stage list
changed.

Two facts this suite refuses to paper over.

**Only the gathering stage runs the loop.** Intake and diagnosis each make one
model call of their own and produce no turn, so they leave no turn record. A
stage record is written for them anyway, saying what they established and what
they spent — which is the honest alternative to inventing a turn so the section
has something in it.

**A run that stops inside a stage leaves that stage unrecorded**, because the
record is written when the stage ends. It is asserted rather than left to be
discovered: the trace says what finished, not what was attempted.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from conftest import PRINCIPAL, TEAM

from config.constants.runs import (
    STAGE_DETAIL_COMPLETION_TOKENS,
    STAGE_DETAIL_FINDING,
    STAGE_DETAIL_LLM_CALLS,
    STAGE_DETAIL_PROMPT_TOKENS,
    STAGE_EVENT_DURATION_MS,
    STAGE_EVENT_FAILED,
    STAGE_EVENT_NAME,
    TRIGGER_ALERT,
    TURN_PAYLOAD_STAGE,
)
from core.agent.session import Session
from core.agent.turn import Turn
from core.pipeline.streaming import EventStream
from core.state.types import StageName
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.runs.events import TraceEventKind
from platform.runs.recorder import RunRecorder
from platform.runs.recording import RunTraceRecordingHook

pytestmark = pytest.mark.unit


async def _seed_run(
    gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime], run_id: str
) -> None:
    async with gateway.begin(scope) as uow:
        await RunRecorder(store=uow.run_traces, clock=clock).start_run(
            trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=run_id
        )


def _stream(hook: RunTraceRecordingHook, run_id: str = "run-1") -> EventStream:
    """Return the pipeline stream this hook is listening to."""
    return EventStream(run_id, (hook,))


async def _stage_events(
    gateway: PersistenceGateway, scope: TenantScope, run_id: str = "run-1"
) -> tuple[dict[str, object], ...]:
    async with gateway.begin(scope) as uow:
        events = await uow.run_traces.events_for_run(run_id, limit=200)
    return tuple(
        dict(event.payload)
        for event in events
        if event.kind == TraceEventKind.STAGE_COMPLETED.value
    )


class TestATurnCarriesTheStageItHappenedIn:
    async def test_a_turn_that_ended_inside_a_stage_names_that_stage(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        stream = _stream(hook)

        await stream.stage_start(StageName.GATHER_EVIDENCE)
        await hook.on_turn_end(Session(id="run-1", objective="disk"), Turn(index=0))

        async with gateway.begin(scope) as uow:
            turns = await uow.run_traces.turns_for_run("run-1")

        assert turns[0].payload[TURN_PAYLOAD_STAGE] == StageName.GATHER_EVIDENCE.value

    async def test_a_turn_recorded_with_no_stage_open_claims_none(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        # A loop driven outside the pipeline — a sub-agent's own run, a
        # deployment that composed no stream — still records its turns. What it
        # must not do is stamp one of the six stages onto a turn that ran under
        # none of them.
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")

        await hook.on_turn_end(Session(id="run-1", objective="disk"), Turn(index=0))

        async with gateway.begin(scope) as uow:
            turns = await uow.run_traces.turns_for_run("run-1")

        assert turns[0].payload.get(TURN_PAYLOAD_STAGE, "") == ""

    async def test_a_turn_after_a_stage_ended_does_not_keep_claiming_it(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        stream = _stream(hook)

        await stream.stage_start(StageName.GATHER_EVIDENCE)
        await stream.stage_end(StageName.GATHER_EVIDENCE)
        await hook.on_turn_end(Session(id="run-1", objective="disk"), Turn(index=0))

        async with gateway.begin(scope) as uow:
            turns = await uow.run_traces.turns_for_run("run-1")

        assert turns[0].payload.get(TURN_PAYLOAD_STAGE, "") == ""


class TestAStageLeavesItsOwnRecord:
    async def test_a_stage_that_ended_is_written_with_its_finding_and_its_duration(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        stream = EventStream("run-1", (hook,), clock=clock)

        await stream.stage_start(StageName.INTAKE)
        await stream.stage_end(
            StageName.INTAKE,
            detail={
                STAGE_DETAIL_FINDING: "A new incident, not a repeat of one already open",
                STAGE_DETAIL_PROMPT_TOKENS: "820",
                STAGE_DETAIL_COMPLETION_TOKENS: "96",
                STAGE_DETAIL_LLM_CALLS: "1",
            },
        )

        recorded = await _stage_events(gateway, scope)
        assert len(recorded) == 1
        assert recorded[0][STAGE_EVENT_NAME] == StageName.INTAKE.value
        assert recorded[0][STAGE_DETAIL_FINDING] == (
            "A new incident, not a repeat of one already open"
        )
        # The clock in this suite advances a second per reading, and the two
        # stream events read it once each.
        assert recorded[0][STAGE_EVENT_DURATION_MS] == 1_000
        assert recorded[0][STAGE_DETAIL_PROMPT_TOKENS] == 820
        assert recorded[0][STAGE_DETAIL_COMPLETION_TOKENS] == 96
        assert recorded[0][STAGE_EVENT_FAILED] is False

    async def test_a_stage_that_produced_no_turn_is_still_recorded(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        # The whole reason the stage record is not derived from the turns.
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        stream = _stream(hook)

        await stream.stage_start(StageName.DIAGNOSE)
        await stream.stage_end(
            StageName.DIAGNOSE,
            detail={STAGE_DETAIL_FINDING: "4 of 4 claims tied to an observation the run holds"},
        )

        async with gateway.begin(scope) as uow:
            turns = await uow.run_traces.turns_for_run("run-1")
        recorded = await _stage_events(gateway, scope)

        assert turns == ()
        assert [entry[STAGE_EVENT_NAME] for entry in recorded] == [StageName.DIAGNOSE.value]

    async def test_a_stage_that_raised_is_recorded_as_failed(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        stream = _stream(hook)

        await stream.stage_start(StageName.GATHER_EVIDENCE)
        await stream.error(StageName.GATHER_EVIDENCE, "TimeoutError: the provider never answered")

        recorded = await _stage_events(gateway, scope)
        assert len(recorded) == 1
        assert recorded[0][STAGE_EVENT_FAILED] is True
        assert recorded[0][STAGE_DETAIL_FINDING] == "TimeoutError: the provider never answered"

    async def test_a_stage_still_running_when_the_run_stopped_leaves_no_record(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        # Stated rather than discovered. The record is written when the stage
        # ends, so a replica that died mid-gather leaves a trace that says which
        # stages finished — never one that claims a stage completed because it
        # was seen to start.
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        stream = _stream(hook)

        await stream.stage_start(StageName.GATHER_EVIDENCE)

        assert await _stage_events(gateway, scope) == ()
