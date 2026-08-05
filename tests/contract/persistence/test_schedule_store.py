"""Contract: scheduled jobs, and the leases that stop two workers doing one twice."""

from __future__ import annotations

import pytest
from conftest import PRIMARY_ORG, SECOND_ORG, at

from config.constants.persistence import MAX_JOB_CLAIM_BATCH
from platform.persistence.errors import BoundExceeded, RecordNotFound
from platform.persistence.ports import (
    JobOutcome,
    PersistenceGateway,
    ScheduledJob,
    TenantScope,
)

pytestmark = pytest.mark.contract


def job(
    job_id: str = "j-1", *, due_minutes: float | None = 0.0, enabled: bool = True
) -> ScheduledJob:
    """Return a job due at a fixed offset, or unscheduled."""
    return ScheduledJob(
        job_id=job_id,
        name="Knowledge sync",
        kind="knowledge.sync",
        schedule="0 2 * * *",
        next_run_at=at(due_minutes) if due_minutes is not None else None,
        enabled=enabled,
        payload={"source": "wiki"},
    )


async def test_a_job_round_trips(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job())
        found = await uow.schedules.get_job("j-1")

    assert found is not None
    assert found.payload["source"] == "wiki"


async def test_disabling_keeps_the_definition(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # An operator should not have to choose between stopping a job and losing
    # how it was configured.
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job())
        disabled = await uow.schedules.set_enabled("j-1", enabled=False)

        assert disabled.enabled is False
        assert len(await uow.schedules.list_jobs()) == 1
        assert await uow.schedules.list_jobs(enabled_only=True) == ()


async def test_unscheduled_jobs_sort_after_due_ones(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job("j-none", due_minutes=None))
        await uow.schedules.upsert_job(job("j-soon", due_minutes=1))
        listed = await uow.schedules.list_jobs()

    assert [item.job_id for item in listed] == ["j-soon", "j-none"]


async def test_only_due_and_enabled_jobs_are_claimed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job("j-due", due_minutes=-1))
        await uow.schedules.upsert_job(job("j-later", due_minutes=60))
        await uow.schedules.upsert_job(job("j-off", due_minutes=-1, enabled=False))
        await uow.schedules.upsert_job(job("j-none", due_minutes=None))

    async with gateway.begin_system() as system:
        claims = await system.jobs.claim_due(now=at(), worker_id="worker-a")

    assert [claim.job_id for claim in claims] == ["j-due"]


async def test_a_claimed_job_is_not_claimed_again(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job(due_minutes=-1))

    async with gateway.begin_system() as system:
        first = await system.jobs.claim_due(now=at(), worker_id="worker-a")
        second = await system.jobs.claim_due(now=at(), worker_id="worker-b")

    assert len(first) == 1
    assert second == ()


async def test_a_claim_carries_the_tenant_the_worker_will_need(
    gateway: PersistenceGateway,
) -> None:
    # The dispatcher claimed it without a scope; the worker needs one to open a
    # unit of work and actually do the job.
    async with gateway.begin(TenantScope(org_id=SECOND_ORG)) as uow:
        await uow.schedules.upsert_job(job(due_minutes=-1))

    async with gateway.begin_system() as system:
        claims = await system.jobs.claim_due(now=at(), worker_id="worker-a")

    assert [claim.org_id for claim in claims] == [SECOND_ORG]


async def test_work_is_shared_out_across_tenants(gateway: PersistenceGateway) -> None:
    for org in (PRIMARY_ORG, SECOND_ORG):
        async with gateway.begin(TenantScope(org_id=org)) as uow:
            await uow.schedules.upsert_job(job(f"j-{org}", due_minutes=-1))

    async with gateway.begin_system() as system:
        claims = await system.jobs.claim_due(now=at(), worker_id="worker-a")

    assert {claim.org_id for claim in claims} == {PRIMARY_ORG, SECOND_ORG}


async def test_releasing_records_the_outcome_and_the_next_run(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job(due_minutes=-1))

    async with gateway.begin_system() as system:
        claim = (await system.jobs.claim_due(now=at(), worker_id="worker-a"))[0]
        await system.jobs.release(
            claim.claim_id,
            outcome=JobOutcome.SUCCEEDED,
            completed_at=at(1),
            next_run_at=at(1440),
        )

    async with gateway.begin(scope) as uow:
        stored = await uow.schedules.get_job("j-1")

    assert stored is not None
    assert stored.last_outcome is JobOutcome.SUCCEEDED
    assert stored.next_run_at == at(1440)


async def test_a_one_shot_job_ends_unscheduled_rather_than_looping(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job(due_minutes=-1))

    async with gateway.begin_system() as system:
        claim = (await system.jobs.claim_due(now=at(), worker_id="worker-a"))[0]
        await system.jobs.release(claim.claim_id, outcome=JobOutcome.SUCCEEDED, completed_at=at(1))
        # Without this, the past ``next_run_at`` would make it due forever.
        assert await system.jobs.claim_due(now=at(2), worker_id="worker-a") == ()


async def test_a_worker_that_vanished_did_not_fail(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Nobody knows whether it ran. Recording a failure would put a false entry
    # in the operator's history of the job.
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job(due_minutes=-1))

    async with gateway.begin_system() as system:
        await system.jobs.claim_due(now=at(), worker_id="worker-a", lease_seconds=60.0)
        released = await system.jobs.expire_leases(now=at(2))
        assert len(released) == 1

        # And the job is claimable again, which is the point of a lease.
        assert len(await system.jobs.claim_due(now=at(2), worker_id="worker-b")) == 1

    async with gateway.begin(scope) as uow:
        stored = await uow.schedules.get_job("j-1")

    assert stored is not None
    assert stored.last_outcome is JobOutcome.ABANDONED


async def test_a_heartbeat_on_a_reclaimed_lease_tells_the_worker_to_stop(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(job(due_minutes=-1))

    async with gateway.begin_system() as system:
        claim = (await system.jobs.claim_due(now=at(), worker_id="worker-a", lease_seconds=60.0))[0]
        await system.jobs.expire_leases(now=at(2))

        with pytest.raises(RecordNotFound):
            await system.jobs.heartbeat(claim.claim_id, now=at(2))


async def test_no_worker_may_swallow_the_whole_backlog(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin_system() as system:
        with pytest.raises(BoundExceeded) as failure:
            await system.jobs.claim_due(
                now=at(), worker_id="worker-a", limit=MAX_JOB_CLAIM_BATCH + 1
            )

    assert failure.value.constant == "MAX_JOB_CLAIM_BATCH"
