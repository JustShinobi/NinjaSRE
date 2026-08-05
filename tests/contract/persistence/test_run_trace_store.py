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
