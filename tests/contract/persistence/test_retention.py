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
    HealthDerivation,
    PayloadSample,
    PersistenceGateway,
    ReferenceKind,
    Resource,
    ResourceHealth,
    ResourceReference,
    RetentionPolicy,
    RetentionSweeper,
    RunStatus,
    SessionRecord,
    TenantScope,
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
    TransitQuery,
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


async def test_estate_history_is_swept_by_the_one_retention_path(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The transitions and links go; the resource itself deliberately stays.

    An absent resource *is* the record that something was removed, and deleting
    it would make the estate forget the thing it was asked to remember. What
    ages out is the history hanging off it.
    """
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="res-1",
                kind="virtual_machine",
                source="proxmox",
                native_id="qemu/101",
                display_name="checkout",
                first_seen_at=EPOCH,
                last_seen_at=EPOCH,
            )
        )
        await uow.estate.record_health(
            "res-1",
            HealthDerivation(
                state=ResourceHealth.HEALTHY, rule="provider_status", derived_at=EPOCH
            ),
        )
        await uow.estate.link(
            ResourceReference(
                resource_id="res-1",
                reference_kind=ReferenceKind.RUN,
                reference_id="run-1",
                recorded_at=EPOCH,
            )
        )

    async with gateway.begin_system() as system:
        report = await system.retention.purge(
            RetentionPolicy(data_class=DataClass.ESTATE_HISTORY, retention_days=1), now=LATER
        )

    assert report.deleted == 2
    async with gateway.begin(scope) as uow:
        assert await uow.estate.transitions("res-1") == ()
        assert await uow.estate.references("res-1") == ()
        assert await uow.estate.get("res-1") is not None


async def test_estate_history_inside_its_window_is_left_alone(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="res-1",
                kind="node",
                source="proxmox",
                native_id="node/pve1",
                first_seen_at=EPOCH,
                last_seen_at=EPOCH,
            )
        )
        await uow.estate.record_health(
            "res-1",
            HealthDerivation(
                state=ResourceHealth.HEALTHY, rule="provider_status", derived_at=EPOCH
            ),
        )

    async with gateway.begin_system() as system:
        report = await system.retention.purge(
            RetentionPolicy(data_class=DataClass.ESTATE_HISTORY, retention_days=365),
            now=EPOCH + timedelta(days=30),
        )

    assert report.deleted == 0
    async with gateway.begin(scope) as uow:
        assert len(await uow.estate.transitions("res-1")) == 1


async def test_transit_rows_age_out_and_the_samples_do_not(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The delivery log is a history; the sample is one row per source.

    Sweeping the samples by age would delete "what does this source send" from
    exactly the sources that send rarely, which is the question they exist for.
    """
    async with gateway.begin(scope) as uow:
        await uow.transit.record(
            TransitDelivery(
                delivery_id="alertmanager-1",
                direction=TransitDirection.INGRESS,
                source="alertmanager",
                occurred_at=EPOCH,
                outcome=TransitOutcome.ACCEPTED,
            )
        )
        await uow.transit.store_sample(
            PayloadSample(
                source="alertmanager",
                captured_at=EPOCH,
                body='{"status":"firing"}',
                masking_policy="standard",
            )
        )

    async with gateway.begin_system() as system:
        report = await system.retention.purge(
            RetentionPolicy(data_class=DataClass.TRANSIT, retention_days=1), now=LATER
        )

    assert report.deleted == 1
    async with gateway.begin(scope) as uow:
        assert await uow.transit.deliveries(TransitQuery()) == ()
        assert await uow.transit.sample("alertmanager") is not None


def test_every_data_class_is_swept_by_the_same_sweeper() -> None:
    """T-031: nothing introduces a second retention path.

    The estate does not get a purge of its own. Every class the deployment
    knows about is a member of one enumeration, applied by one sweeper reached
    through the system unit of work — so "how long is anything kept" has one
    answer and one place to change it.
    """
    exempt = {data_class for data_class in DataClass if data_class.is_exempt}
    sweepable = set(DataClass) - exempt

    assert DataClass.ESTATE_HISTORY in sweepable
    for data_class in sweepable:
        assert RetentionPolicy.default_for(data_class).retention_days is not None

    # ``RetentionSweeper`` is the whole retention surface: two methods, both of
    # which take policies. A class-specific delete would show up here.
    assert {name for name in dir(RetentionSweeper) if not name.startswith("_")} == {
        "purge",
        "purge_all",
    }
