"""Contract: retention per data class, and the class that is never deleted."""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import EPOCH, at

from platform.persistence.errors import RetentionExempt
from platform.persistence.ports import (
    ActorKind,
    AgentRun,
    AuditEvent,
    DataClass,
    Episode,
    EvidenceRecord,
    PersistenceGateway,
    RetentionPolicy,
    RunStatus,
    SessionRecord,
    TenantScope,
    TurnRecord,
)

pytestmark = pytest.mark.contract

#: Long enough after the seeded records that a one-day window has expired them.
LATER = EPOCH + timedelta(days=30)


def test_a_finite_window_cannot_be_written_for_the_audit_trail() -> None:
    """FR-022, expressed so the bad policy cannot be represented.

    A policy that was silently not applied is worse than one that was rejected,
    because the operator believes it is in force.
    """
    with pytest.raises(RetentionExempt):
        RetentionPolicy(data_class=DataClass.AUDIT, retention_days=30)

    # Keeping them indefinitely is the only thing this class may say.
    assert RetentionPolicy.default_for(DataClass.AUDIT).retention_days is None


def test_a_window_that_deletes_as_fast_as_records_arrive_is_refused() -> None:
    with pytest.raises(ValueError, match="as fast as they are written"):
        RetentionPolicy(data_class=DataClass.RUN_TRACES, retention_days=0)


def test_defaults_keep_the_corpus_far_longer_than_the_traces() -> None:
    # Article VII: deleting the corpus removes the ability to prove the system
    # improved.
    traces = RetentionPolicy.default_for(DataClass.RUN_TRACES).retention_days
    episodes = RetentionPolicy.default_for(DataClass.EPISODES).retention_days

    assert traces is not None
    assert episodes is not None
    assert episodes > traces


async def test_purging_traces_takes_everything_hanging_off_them(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A trace missing its evidence is not a smaller trace, it is a misleading
    # one: what the model said, with no record of what the system observed.
    async with gateway.begin(scope) as uow:
        await uow.run_traces.start_run(AgentRun(run_id="run-1", trigger="alert", started_at=EPOCH))
        await uow.run_traces.record_turn(TurnRecord(turn_id="t-1", run_id="run-1", index=0))
        await uow.run_traces.record_evidence(
            EvidenceRecord(evidence_id="e-1", run_id="run-1", source="loki", evidence_type="log")
        )
        await uow.run_traces.complete_run("run-1", status=RunStatus.COMPLETED, finished_at=at(5))

    async with gateway.begin_system() as system:
        report = await system.retention.purge(
            RetentionPolicy(data_class=DataClass.RUN_TRACES, retention_days=1), now=LATER
        )

    assert report.deleted == 1

    async with gateway.begin(scope) as uow:
        assert await uow.run_traces.get_run("run-1") is None
        assert await uow.run_traces.turns_for_run("run-1") == ()
        assert await uow.run_traces.evidence_for_run("run-1") == ()


async def test_the_audit_trail_survives_a_sweep_of_everything_else(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.audit.append(
            AuditEvent(
                event_id="e-1",
                occurred_at=EPOCH,
                actor_kind=ActorKind.USER,
                actor_id="u-ada",
                action="approval.decide",
                resource_kind="approval",
                resource_id="a-1",
            )
        )
        await uow.sessions.save(
            SessionRecord(session_id="s-1", status="completed", updated_at=EPOCH)
        )
        await uow.episodes.save(
            Episode(
                episode_id="ep-1",
                title="Old",
                summary="Old.",
                signature="checkout-5xx",
                occurred_at=EPOCH,
            )
        )

    async with gateway.begin_system() as system:
        reports = await system.retention.purge_all(
            (
                RetentionPolicy(data_class=DataClass.SESSIONS, retention_days=1),
                RetentionPolicy(data_class=DataClass.EPISODES, retention_days=1),
            ),
            now=LATER,
        )

        with pytest.raises(RetentionExempt):
            await system.retention.purge(RetentionPolicy.default_for(DataClass.AUDIT), now=LATER)

    assert [report.data_class for report in reports] == [DataClass.SESSIONS, DataClass.EPISODES]
    assert [report.deleted for report in reports] == [1, 1]

    async with gateway.begin(scope) as uow:
        assert await uow.sessions.load("s-1") is None
        assert await uow.episodes.get("ep-1") is None
        assert await uow.audit.get("e-1") is not None


async def test_a_policy_with_no_window_deletes_nothing(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.sessions.save(
            SessionRecord(session_id="s-1", status="completed", updated_at=EPOCH)
        )

    async with gateway.begin_system() as system:
        report = await system.retention.purge(
            RetentionPolicy(data_class=DataClass.SESSIONS, retention_days=None), now=LATER
        )

    assert report.deleted == 0
    assert report.cutoff is None

    async with gateway.begin(scope) as uow:
        assert await uow.sessions.load("s-1") is not None


async def test_records_inside_the_window_are_left_alone(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.sessions.save(
            SessionRecord(session_id="s-old", status="completed", updated_at=EPOCH)
        )
        await uow.sessions.save(
            SessionRecord(
                session_id="s-recent", status="completed", updated_at=LATER - timedelta(hours=1)
            )
        )

    async with gateway.begin_system() as system:
        report = await system.retention.purge(
            RetentionPolicy(data_class=DataClass.SESSIONS, retention_days=1), now=LATER
        )

    assert report.deleted == 1

    async with gateway.begin(scope) as uow:
        assert await uow.sessions.load("s-old") is None
        assert await uow.sessions.load("s-recent") is not None
