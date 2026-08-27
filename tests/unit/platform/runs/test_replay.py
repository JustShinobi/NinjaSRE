"""Reading a finished investigation back, including one whose tools are gone."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

import pytest
from conftest import PRINCIPAL, TEAM

from config.constants.runs import (
    MAX_REPLAY_RESULT_BYTES,
    TRIGGER_ALERT,
    TRUNCATION_MARKER_KEY,
    TURN_PAYLOAD_STAGE,
)
from core.state.types import StageName
from platform.persistence.ports import RunStatus, ToolCallStatus, UnitOfWork
from platform.runs.cursor import Cursor
from platform.runs.events import TraceEventKind
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder
from platform.runs.replay import ReplayedCall, bounded_result, replay_run
from platform.runs.stream import RunEventBroker, RunStream


class Catalogue:
    """A capability catalogue holding whatever the test says it holds."""

    def __init__(self, **descriptions: str) -> None:
        self._descriptions = descriptions

    def describe(self, name: str) -> str | None:
        """Return the current description of ``name``, or ``None``."""
        return self._descriptions.get(name.replace(".", "_"))


async def investigate(
    uow: UnitOfWork, clock: Callable[[], datetime], *, broker: RunEventBroker | None = None
) -> str:
    """Record a two-turn investigation and return its run id."""
    counter = iter(range(10_000))
    writer = RunRecorder(
        store=uow.run_traces,
        clock=clock,
        ids=lambda: f"id-{next(counter):04d}",
        broker=broker,
    )
    run = await writer.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, alert_id="alert-9"
    )
    first = await writer.record_turn(
        RecordedTurn(
            run_id=run.run_id,
            index=0,
            model="claude-opus-5",
            prompt_tokens=1_000,
            completion_tokens=200,
            cost=0.03,
            selection_rationale="the alert names a Kubernetes workload",
            offered_capabilities=("kubernetes.list_pods",),
        )
    )
    await writer.record_call(
        RecordedCall(
            run_id=run.run_id,
            turn_id=first.turn_id,
            name="kubernetes.list_pods",
            arguments={"namespace": "payments"},
            result={"pods": ["checkout-1"]},
            duration_ms=140,
        )
    )
    await writer.record_evidence(
        run_id=run.run_id, source="kubernetes", evidence_type="observation", body={"restarts": 7}
    )
    await writer.record_turn(
        RecordedTurn(
            run_id=run.run_id,
            index=1,
            model="claude-opus-5",
            prompt_tokens=1_400,
            completion_tokens=310,
            cost=0.05,
            selection_rationale="the pods restarted; look at their logs",
        )
    )
    await writer.complete_run(
        run.run_id, status=RunStatus.COMPLETED, summary="OOMKill from a memory leak."
    )
    return run.run_id


async def test_a_replayed_run_carries_every_turn_call_and_event(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    run_id = await investigate(uow, clock)

    replayed = await replay_run(uow.run_traces, run_id)

    assert [turn.index for turn in replayed.turns] == [0, 1]
    assert [call.name for turn in replayed.turns for call in turn.calls] == ["kubernetes.list_pods"]
    assert replayed.run.summary == "OOMKill from a memory leak."
    assert TraceEventKind.RUN_FINISHED in {event.kind for event in replayed.events}


async def test_the_replayed_view_matches_what_a_live_client_observed(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # The completeness criterion, asserted directly: whatever the broker
    # delivered while the run happened is what the log replays afterwards.
    broker = RunEventBroker()
    observed: list[tuple[str, int]] = []

    run_id = "run-observed"
    subscription = broker.attach(run_id)
    await investigate_with_id(uow, clock, run_id=run_id, broker=broker)
    async for event in subscription.drain():
        observed.append((event.kind.value, event.sequence))

    replayed = await replay_run(uow.run_traces, run_id)
    stored = [(event.kind.value, event.sequence) for event in replayed.events]

    assert observed == stored


async def investigate_with_id(
    uow: UnitOfWork,
    clock: Callable[[], datetime],
    *,
    run_id: str,
    broker: RunEventBroker,
) -> None:
    """Record an investigation under a chosen run id."""
    counter = iter(range(10_000))
    writer = RunRecorder(
        store=uow.run_traces,
        clock=clock,
        ids=lambda: f"id-{next(counter):04d}",
        broker=broker,
    )
    await writer.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=run_id
    )
    turn = await writer.record_turn(RecordedTurn(run_id=run_id, index=0, model="m"))
    await writer.record_call(RecordedCall(run_id=run_id, turn_id=turn.turn_id, name="loki.query"))
    await writer.complete_run(run_id, status=RunStatus.COMPLETED, summary="done")


async def test_replay_exposes_the_selection_rationale_of_each_turn(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # The half of a decision the call list does not record: not what was
    # chosen, but why those capabilities were the ones on offer.
    run_id = await investigate(uow, clock)

    replayed = await replay_run(uow.run_traces, run_id)

    assert replayed.turns[0].selection_rationale == "the alert names a Kubernetes workload"
    assert replayed.turns[0].offered_capabilities == ("kubernetes.list_pods",)


async def test_replay_survives_a_capability_the_catalogue_has_lost(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # A replay that refused to render a removed tool would fail on exactly the
    # runs worth reviewing months later.
    run_id = await investigate(uow, clock)

    replayed = await replay_run(uow.run_traces, run_id, catalogue=Catalogue())

    call = replayed.turns[0].calls[0]
    assert call.degraded
    assert call.name == "kubernetes.list_pods"
    assert call.arguments == {"namespace": "payments"}
    assert call.result == {"pods": ["checkout-1"]}
    assert replayed.degraded_calls == (call,)


async def test_a_capability_the_catalogue_still_knows_is_described(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    run_id = await investigate(uow, clock)

    replayed = await replay_run(
        uow.run_traces, run_id, catalogue=Catalogue(kubernetes_list_pods="Lists pods.")
    )

    assert replayed.turns[0].calls[0].available
    assert replayed.turns[0].calls[0].description == "Lists pods."


async def test_replay_totals_the_cost_and_tokens_of_a_run(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    run_id = await investigate(uow, clock)

    replayed = await replay_run(uow.run_traces, run_id)

    assert replayed.total_cost == pytest.approx(0.08)
    assert replayed.total_tokens == 2_910


async def test_an_interrupted_run_replays_into_a_usable_record(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    counter = iter(range(10_000))
    writer = RunRecorder(store=uow.run_traces, clock=clock, ids=lambda: f"id-{next(counter):04d}")
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    turn = await writer.record_turn(RecordedTurn(run_id=run.run_id, index=0, model="m"))
    await writer.record_call(
        RecordedCall(
            run_id=run.run_id,
            turn_id=turn.turn_id,
            name="loki.query",
            status=ToolCallStatus.SUCCEEDED,
            result={"lines": 12},
        )
    )
    await writer.mark_interrupted(run.run_id, reason="the replica was killed")

    replayed = await replay_run(uow.run_traces, run.run_id)

    assert replayed.is_interrupted
    assert len(replayed.turns) == 1
    assert replayed.turns[0].calls[0].result == {"lines": 12}


async def test_a_stream_snapshot_and_a_replay_agree_on_the_log(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    run_id = await investigate(uow, clock)
    stream = RunStream(store=uow.run_traces, broker=RunEventBroker())

    snapshot = await stream.snapshot(run_id)
    replayed = await replay_run(uow.run_traces, run_id)

    assert snapshot == replayed.events
    assert await stream.replay_from(Cursor.start_of(run_id)) == snapshot


async def test_a_recorded_result_inside_the_bound_reaches_a_reader_untouched(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # The projection has to be a no-op on the ordinary case, or a console
    # reading one would have to guess whether a small result had been edited.
    run_id = await investigate(uow, clock)
    replayed = await replay_run(uow.run_traces, run_id)

    served, truncated = bounded_result(replayed.turns[0].calls[0])

    assert served == {"pods": ["checkout-1"]}
    assert truncated is False


def test_a_result_too_large_for_a_replay_is_cut_and_says_it_was() -> None:
    # A replay carries every call of a run in one response, so the recorder's
    # per-row ceiling multiplied by a run's call count is a page nothing can
    # hold. Cutting is fine here for the same reason it is fine on the way in;
    # cutting silently is not.
    call = ReplayedCall(
        call_id="c",
        turn_id="t",
        name="loki.query",
        status=ToolCallStatus.SUCCEEDED,
        result={"statement": "the probe failed", "lines": ["x" * 900 for _ in range(400)]},
    )

    served, truncated = bounded_result(call)

    assert truncated is True
    assert len(json.dumps(served).encode("utf-8")) <= MAX_REPLAY_RESULT_BYTES
    assert TRUNCATION_MARKER_KEY in served
    # The small field survives: shedding drops the largest first, so what a
    # reader can still state about the call is what is left standing.
    assert served["statement"] == "the probe failed"


async def test_a_result_the_recorder_shed_whole_is_still_declared_as_cut(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # The recorder's byte ceiling drops an oversized field wholesale, so the
    # stored body has no ``result`` left at all — only the marker beside it.
    # Reading truncation out of the result would find an empty mapping here and
    # report a call that returned nothing, which is not what happened.
    writer = RunRecorder(store=uow.run_traces, clock=clock, ids=lambda: "id-0")
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    turn = await writer.record_turn(RecordedTurn(run_id=run.run_id, index=0, model="m"))
    await writer.record_call(
        RecordedCall(
            run_id=run.run_id,
            turn_id=turn.turn_id,
            name="loki.query",
            result={"lines": ["x" * 900 for _ in range(400)]},
        )
    )

    replayed = await replay_run(uow.run_traces, run.run_id)

    call = replayed.turns[0].calls[0]
    assert call.result_truncated is True
    assert bounded_result(call)[1] is True


# --- the six stages, and the tokens a turn-only total leaves out ----------------


def _writer(uow: UnitOfWork, clock: Callable[[], datetime]) -> RunRecorder:
    """Return a recorder whose records each get an identifier of their own."""
    counter = iter(range(10_000))
    return RunRecorder(store=uow.run_traces, clock=clock, ids=lambda: f"id-{next(counter):04d}")


async def _stage(
    writer: RunRecorder,
    run_id: str,
    stage: StageName,
    *,
    finding: str = "",
    duration_ms: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    llm_calls: int = 0,
    failed: bool = False,
) -> None:
    """Record one stage of ``run_id`` as the recording hook writes it."""
    await writer.record_stage(
        run_id,
        stage=stage.value,
        finding=finding,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        llm_calls=llm_calls,
        failed=failed,
    )


async def test_a_replay_reassembles_the_stages_in_the_order_the_pipeline_runs_them(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # Written out of order on purpose. The pipeline order is a property of the
    # pipeline, not of whichever page of the event log came back first.
    writer = _writer(uow, clock)
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    await _stage(writer, run.run_id, StageName.DIAGNOSE, finding="4 of 4 claims")
    await _stage(writer, run.run_id, StageName.INTAKE, finding="a new incident")

    replayed = await replay_run(uow.run_traces, run.run_id)

    assert [stage.stage for stage in replayed.stages] == [StageName.INTAKE, StageName.DIAGNOSE]
    assert replayed.stages[0].finding == "a new incident"


async def test_a_stage_that_produced_no_turn_holds_no_turns_rather_than_borrowing_one(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = _writer(uow, clock)
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    await writer.record_turn(
        RecordedTurn(
            run_id=run.run_id,
            index=0,
            model="m",
            payload={TURN_PAYLOAD_STAGE: StageName.GATHER_EVIDENCE.value},
        )
    )
    await _stage(writer, run.run_id, StageName.GATHER_EVIDENCE)
    await _stage(writer, run.run_id, StageName.DIAGNOSE, llm_calls=1)

    replayed = await replay_run(uow.run_traces, run.run_id)

    by_name = {stage.stage: stage for stage in replayed.stages}
    assert [turn.index for turn in by_name[StageName.GATHER_EVIDENCE].turns] == [0]
    assert by_name[StageName.DIAGNOSE].turns == ()
    assert by_name[StageName.DIAGNOSE].llm_calls == 1


async def test_the_token_total_counts_the_model_calls_that_left_no_turn(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # Intake and diagnosis each call a model and produce no loop turn, so a
    # total summed over turns is a floor. Summed over the stages it is the run.
    writer = _writer(uow, clock)
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    await writer.record_turn(
        RecordedTurn(
            run_id=run.run_id,
            index=0,
            model="m",
            prompt_tokens=1_000,
            completion_tokens=200,
            payload={TURN_PAYLOAD_STAGE: StageName.GATHER_EVIDENCE.value},
        )
    )
    await _stage(
        writer,
        run.run_id,
        StageName.INTAKE,
        prompt_tokens=800,
        completion_tokens=90,
        llm_calls=1,
    )
    await _stage(
        writer,
        run.run_id,
        StageName.GATHER_EVIDENCE,
        prompt_tokens=1_000,
        completion_tokens=200,
        llm_calls=1,
    )
    await _stage(
        writer,
        run.run_id,
        StageName.DIAGNOSE,
        prompt_tokens=600,
        completion_tokens=110,
        llm_calls=1,
    )

    replayed = await replay_run(uow.run_traces, run.run_id)

    assert replayed.turn_tokens == 1_200
    assert replayed.total_tokens == 2_800


async def test_a_trace_with_no_stages_recorded_still_totals_its_turns(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # Every run recorded before the stages reached the trace, and every run a
    # caller drove without a pipeline. The number is a floor there and the
    # absent stage list is what says so.
    writer = RunRecorder(store=uow.run_traces, clock=clock, ids=lambda: "id-0")
    run = await writer.start_run(trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM)
    await writer.record_turn(
        RecordedTurn(run_id=run.run_id, index=0, model="m", prompt_tokens=10, completion_tokens=5)
    )

    replayed = await replay_run(uow.run_traces, run.run_id)

    assert replayed.stages == ()
    assert replayed.total_tokens == 15
