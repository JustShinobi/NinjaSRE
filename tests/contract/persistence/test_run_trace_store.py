"""Contract: the trace, and whether it can be replayed."""

from __future__ import annotations

import pytest
from conftest import at

from config.constants.persistence import MAX_JSONB_PAYLOAD_BYTES
from platform.persistence.errors import DuplicateRecord, PayloadTooLarge, RecordNotFound
from platform.persistence.ports import (
    AgentRun,
    EvidenceRecord,
    PersistenceGateway,
    RunStatus,
    TenantScope,
    ToolCallRecord,
    TraceEventRecord,
    TurnRecord,
)

pytestmark = pytest.mark.contract


def run(run_id: str = "run-1", *, minutes: float = 0.0) -> AgentRun:
    """Return a started run."""
    return AgentRun(
        run_id=run_id,
        trigger="alert",
        alert_id="alert-9",
        started_at=at(minutes),
        runtime="canonical",
    )


async def test_a_run_is_started_once(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())

        with pytest.raises(DuplicateRecord):
            await uow.run_traces.start_run(run())


async def test_completing_a_run_records_its_terminal_status(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        closed = await uow.run_traces.complete_run(
            "run-1",
            status=RunStatus.COMPLETED,
            finished_at=at(5),
            summary="Connection pool exhaustion in checkout.",
        )

    assert closed.status is RunStatus.COMPLETED
    assert closed.summary is not None


async def test_a_turn_for_an_unknown_run_is_refused(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await uow.run_traces.record_turn(TurnRecord(turn_id="t-1", run_id="ghost", index=0))


async def test_replay_assembles_the_whole_trace_in_order(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        # Written out of order on purpose: index orders turns, not arrival.
        await uow.run_traces.record_turn(TurnRecord(turn_id="t-2", run_id="run-1", index=1))
        await uow.run_traces.record_turn(TurnRecord(turn_id="t-1", run_id="run-1", index=0))
        await uow.run_traces.record_tool_call(
            ToolCallRecord(
                call_id="c-1",
                run_id="run-1",
                turn_id="t-1",
                tool_name="kubernetes.list_pods",
                evidence_ids=("e-1",),
            )
        )
        await uow.run_traces.record_evidence(
            EvidenceRecord(
                evidence_id="e-1",
                run_id="run-1",
                source="kubernetes",
                evidence_type="observation",
                observed_at=at(1),
            )
        )

        trace = await uow.run_traces.replay("run-1")

    assert [turn.turn_id for turn in trace.turns] == ["t-1", "t-2"]
    assert [call.call_id for call in trace.tool_calls] == ["c-1"]
    assert [item.evidence_id for item in trace.evidence] == ["e-1"]


async def test_replaying_a_run_that_does_not_exist_raises(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # An empty trace and a missing run are different facts. An ablation reading
    # the second as the first would score a missing corpus as a bad one.
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await uow.run_traces.replay("ghost")


async def test_citing_evidence_is_recorded(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        await uow.run_traces.record_evidence(
            EvidenceRecord(evidence_id="e-1", run_id="run-1", source="loki", evidence_type="log")
        )

        assert await uow.run_traces.mark_cited("e-1") is True
        assert await uow.run_traces.mark_cited("no-such-evidence") is False

        trace = await uow.run_traces.replay("run-1")

    assert trace.evidence[0].cited is True


async def test_runs_are_listed_most_recent_first_and_filtered(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run("run-1", minutes=0))
        await uow.run_traces.start_run(run("run-2", minutes=5))
        await uow.run_traces.complete_run("run-2", status=RunStatus.FAILED, finished_at=at(6))

        assert [r.run_id for r in await uow.run_traces.list_runs()] == ["run-2", "run-1"]
        listed = await uow.run_traces.list_runs(status=RunStatus.FAILED)

    assert [r.run_id for r in listed] == ["run-2"]


async def test_an_oversized_body_is_refused_rather_than_stored(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The edge case the spec calls out: a tool that returns forty megabytes of
    # logs stores a reference and a summary, not the lot.
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())

        with pytest.raises(PayloadTooLarge):
            await uow.run_traces.record_evidence(
                EvidenceRecord(
                    evidence_id="e-1",
                    run_id="run-1",
                    source="loki",
                    evidence_type="log",
                    body={"lines": "x" * (MAX_JSONB_PAYLOAD_BYTES + 1)},
                )
            )


async def test_events_are_appended_with_a_monotonic_cursor(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The cursor is what a reconnecting client presents, so it has to be
    # assigned by the store rather than by whoever happened to write the event.
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        first = await uow.run_traces.record_event(
            TraceEventRecord(event_id="ev-1", run_id="run-1", kind="run_started")
        )
        second = await uow.run_traces.record_event(
            TraceEventRecord(event_id="ev-2", run_id="run-1", kind="guardrail_action")
        )

    assert first.sequence < second.sequence


async def test_events_are_read_back_after_a_cursor(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        recorded = [
            await uow.run_traces.record_event(
                TraceEventRecord(event_id=f"ev-{index}", run_id="run-1", kind="turn_completed")
            )
            for index in range(4)
        ]

        missed = await uow.run_traces.events_for_run("run-1", after=recorded[1].sequence)

    assert [event.event_id for event in missed] == ["ev-2", "ev-3"]


async def test_an_event_for_an_unknown_run_is_refused(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await uow.run_traces.record_event(
                TraceEventRecord(event_id="ev-1", run_id="ghost", kind="run_started")
            )


async def test_replay_carries_the_event_log(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        await uow.run_traces.record_event(
            TraceEventRecord(event_id="ev-1", run_id="run-1", kind="masking_applied")
        )

        trace = await uow.run_traces.replay("run-1")

    assert [event.kind for event in trace.events] == ["masking_applied"]


async def test_stripping_a_trace_keeps_the_run_and_its_summary(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # FR-025: retention removes the trace, never the record that the
    # investigation happened and what it concluded.
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        await uow.run_traces.complete_run(
            "run-1", status=RunStatus.COMPLETED, finished_at=at(5), summary="Pool exhaustion."
        )
        await uow.run_traces.record_turn(TurnRecord(turn_id="t-1", run_id="run-1", index=0))
        await uow.run_traces.record_tool_call(
            ToolCallRecord(call_id="c-1", run_id="run-1", turn_id="t-1", tool_name="k8s.pods")
        )
        await uow.run_traces.record_evidence(
            EvidenceRecord(evidence_id="e-1", run_id="run-1", source="loki", evidence_type="log")
        )
        await uow.run_traces.record_event(
            TraceEventRecord(event_id="ev-1", run_id="run-1", kind="run_started")
        )

        removed = await uow.run_traces.strip_trace("run-1")
        trace = await uow.run_traces.replay("run-1")

    assert removed == 4
    assert trace.turns == () and trace.tool_calls == () and trace.evidence == ()
    assert trace.events == ()
    assert trace.run.summary == "Pool exhaustion."
    assert trace.run.status is RunStatus.COMPLETED


async def test_stripping_a_run_that_does_not_exist_raises(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await uow.run_traces.strip_trace("ghost")


async def test_tool_calls_replay_in_the_order_they_arrived(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Not by id and not by timestamp. Two calls in one concurrent batch share a
    # microsecond, and ids sort lexically — so an arrival counter that stopped
    # advancing would leave the replay ordered by neither, silently.
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        await uow.run_traces.record_turn(TurnRecord(turn_id="t-1", run_id="run-1", index=0))
        for name in ("zeta", "alpha", "mu"):
            await uow.run_traces.record_tool_call(
                ToolCallRecord(
                    call_id=f"c-{name}",
                    run_id="run-1",
                    turn_id="t-1",
                    tool_name=name,
                    started_at=at(),
                )
            )

        trace = await uow.run_traces.replay("run-1")

    assert [call.tool_name for call in trace.tool_calls] == ["zeta", "alpha", "mu"]


async def test_evidence_replays_in_the_order_it_was_observed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        for name in ("zeta", "alpha", "mu"):
            await uow.run_traces.record_evidence(
                EvidenceRecord(
                    evidence_id=f"e-{name}",
                    run_id="run-1",
                    source=name,
                    evidence_type="log",
                    observed_at=at(),
                )
            )

        trace = await uow.run_traces.replay("run-1")

    assert [item.source for item in trace.evidence] == ["zeta", "alpha", "mu"]


async def test_every_event_gets_its_own_position(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Stated as a set rather than as "the last one is bigger": a counter that
    # stopped advancing after the first record still satisfies the weaker check
    # on two events and fails here on five.
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(run())
        recorded = [
            await uow.run_traces.record_event(
                TraceEventRecord(event_id=f"ev-{index}", run_id="run-1", kind="turn_completed")
            )
            for index in range(5)
        ]

    assert [event.sequence for event in recorded] == [0, 1, 2, 3, 4]
