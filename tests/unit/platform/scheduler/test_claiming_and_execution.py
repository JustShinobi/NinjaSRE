"""Exactly one replica runs a due job, and a dead one releases it."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from conftest import (
    OTHER_TEAM,
    PRINCIPAL,
    TEAM,
    FixedSettings,
    RecordingPipeline,
    at,
    recorder_over,
)

from platform.persistence.ports import (
    JobOutcome,
    PersistenceGateway,
    RunStatus,
    TenantScope,
)
from platform.scheduler.claiming import ClaimLost, JobClaimer, fire_key, heartbeating
from platform.scheduler.concurrency import ConcurrencyLimits
from platform.scheduler.executor import JobExecutor
from platform.scheduler.models import Schedule
from platform.scheduler.reaper import LeaseReaper

NIGHTLY = "0 2 * * *"


def schedule(job_id: str = "job-dr", *, team: str = TEAM) -> Schedule:
    """Return a schedule due at the fixed epoch."""
    return Schedule(
        job_id=job_id,
        name="Nightly DR validation",
        team_node_id=team,
        principal_id=PRINCIPAL,
        cron=NIGHTLY,
        objective="prove the standby can take over",
        next_run_at=at(-1),
    )


async def store_schedule(gateway: PersistenceGateway, scope: TenantScope, one: Schedule) -> None:
    """Persist ``one`` so a dispatcher can find it due."""
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(one.to_job())


# -- claiming ------------------------------------------------------------------


async def test_one_firing_is_claimed_by_exactly_one_of_three_replicas(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    await store_schedule(gateway, scope, schedule())

    claimed: list[str] = []
    for worker in ("replica-a", "replica-b", "replica-c"):
        async with gateway.begin_system() as system:
            claimer = JobClaimer(dispatcher=system.jobs, worker_id=worker)
            claimed.extend(claim.worker_id for claim in await claimer.claim_due(now=at()))

    assert len(claimed) == 1


async def test_a_hundred_firings_across_three_replicas_run_once_each(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The success criterion, stated directly. Each firing is claimed by exactly
    # one replica and the job comes due again only when that one releases it.
    await store_schedule(gateway, scope, schedule())

    workers = ("replica-a", "replica-b", "replica-c")
    executions: list[tuple[str, int]] = []

    for firing in range(100):
        moment = at(firing)
        winners = []
        for worker in workers:
            async with gateway.begin_system() as system:
                claimer = JobClaimer(dispatcher=system.jobs, worker_id=worker)
                for claim in await claimer.claim_due(now=moment):
                    winners.append((worker, claim))

        assert len(winners) == 1, f"firing {firing} was claimed {len(winners)} times"
        worker, claim = winners[0]
        executions.append((worker, firing))

        async with gateway.begin_system() as system:
            await JobClaimer(dispatcher=system.jobs, worker_id=worker).release(
                claim,
                outcome=JobOutcome.SUCCEEDED,
                completed_at=moment,
                next_run_at=at(firing + 1) - timedelta(seconds=1),
            )

    assert len(executions) == 100
    assert {firing for _, firing in executions} == set(range(100))


async def test_a_disabled_job_is_never_claimed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    from platform.scheduler.models import DisabledReason

    await store_schedule(gateway, scope, schedule().disabled(DisabledReason.OPERATOR))

    async with gateway.begin_system() as system:
        claims = await JobClaimer(dispatcher=system.jobs, worker_id="replica-a").claim_due(now=at())

    assert claims == ()


async def test_a_heartbeat_keeps_a_lease_and_a_lost_one_raises(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    await store_schedule(gateway, scope, schedule())

    async with gateway.begin_system() as system:
        claimer = JobClaimer(dispatcher=system.jobs, worker_id="replica-a")
        claim = (await claimer.claim_due(now=at()))[0]
        renewed = await claimer.heartbeat(claim, now=at(1))
        assert renewed.lease_expires_at > claim.lease_expires_at

        # The lease lapses and something else takes the job.
        await system.jobs.expire_leases(now=at(600))

        with pytest.raises(ClaimLost):
            await claimer.heartbeat(claim, now=at(601))


async def test_the_heartbeat_task_stops_when_its_block_ends(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A heartbeat outliving its work would keep a lease alive for a job nobody
    # is running, which is a lock again with extra steps.
    await store_schedule(gateway, scope, schedule())

    async with gateway.begin_system() as system:
        claimer = JobClaimer(dispatcher=system.jobs, worker_id="replica-a")
        claim = (await claimer.claim_due(now=at()))[0]
        async with heartbeating(claimer, claim, interval_seconds=0.01) as task:
            await asyncio.sleep(0.03)
            assert not task.done()

    assert task.cancelled() or task.done()


# -- execution -----------------------------------------------------------------


async def test_a_scheduled_run_is_an_ordinary_run_with_a_schedule_trigger(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    pipeline = RecordingPipeline(summary="The standby took over cleanly.")
    async with gateway.begin(scope) as uow:
        executor = JobExecutor(recorder=recorder_over(uow.run_traces), pipeline=pipeline)

        result = await executor.execute(schedule(), fire_time=at())

        stored = await uow.run_traces.get_run(result.run.run_id if result.run else "")

    assert result.outcome is JobOutcome.SUCCEEDED
    assert result.ran
    assert stored is not None
    assert stored.trigger == "schedule"
    assert stored.status is RunStatus.COMPLETED
    assert stored.summary == "The standby took over cleanly."


async def test_the_same_firing_cannot_produce_two_runs(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The second layer of exactly-once: even if a lease lapsed and another
    # replica claimed this firing, the run id is derived from the firing.
    pipeline = RecordingPipeline()
    async with gateway.begin(scope) as uow:
        executor = JobExecutor(recorder=recorder_over(uow.run_traces), pipeline=pipeline)

        first = await executor.execute(schedule(), fire_time=at())
        second = await executor.execute(schedule(), fire_time=at())

    assert first.ran
    assert second.duplicate
    assert not second.ran
    assert len(pipeline.requests) == 1
    assert first.run is not None
    assert first.run.run_id == fire_key("job-dr", at())


async def test_configuration_is_resolved_when_the_job_runs(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A schedule created in March and running in September uses September's
    # configuration, so the resolution happens here and not at creation.
    pipeline = RecordingPipeline()
    settings = FixedSettings(values={"model": "claude-opus-5"})
    async with gateway.begin(scope) as uow:
        executor = JobExecutor(
            recorder=recorder_over(uow.run_traces), pipeline=pipeline, settings=settings
        )
        await executor.execute(schedule(), fire_time=at())

    assert settings.asked == [TEAM]
    assert pipeline.requests[0].settings == {"model": "claude-opus-5"}


async def test_a_failing_investigation_closes_its_run_and_does_not_raise(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A raising executor would drop the release of the claim with it, and the
    # job would be blocked until the lease expired.
    pipeline = RecordingPipeline(fail_with=RuntimeError("the standby is unreachable"))
    async with gateway.begin(scope) as uow:
        executor = JobExecutor(recorder=recorder_over(uow.run_traces), pipeline=pipeline)

        result = await executor.execute(schedule(), fire_time=at())

        stored = await uow.run_traces.get_run(result.run.run_id if result.run else "")

    assert result.outcome is JobOutcome.FAILED
    assert result.failure == "the standby is unreachable"
    assert stored is not None
    assert stored.status is RunStatus.FAILED


# -- concurrency ---------------------------------------------------------------


async def test_a_team_cannot_occupy_more_than_its_share(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    gate = asyncio.Event()
    pipeline = RecordingPipeline(gate=gate)
    limits = ConcurrencyLimits(global_limit=4, team_limit=2)

    async with gateway.begin(scope) as uow:
        executor = JobExecutor(
            recorder=recorder_over(uow.run_traces), pipeline=pipeline, limits=limits
        )
        running = [
            asyncio.create_task(executor.execute(schedule(f"job-{n}"), fire_time=at()))
            for n in range(4)
        ]
        # Let the ones that can start, start.
        for _ in range(10):
            await asyncio.sleep(0)

        assert pipeline.in_flight == 2
        assert limits.running_for(TEAM) == 2

        gate.set()
        await asyncio.gather(*running)

    assert pipeline.peak_in_flight == 2
    # Queued rather than dropped: every firing eventually ran.
    assert len(pipeline.requests) == 4


async def test_work_beyond_the_limit_queues_rather_than_being_refused(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    gate = asyncio.Event()
    pipeline = RecordingPipeline(gate=gate)
    limits = ConcurrencyLimits(global_limit=1, team_limit=1)

    async with gateway.begin(scope) as uow:
        executor = JobExecutor(
            recorder=recorder_over(uow.run_traces), pipeline=pipeline, limits=limits
        )
        running = [
            asyncio.create_task(executor.execute(schedule(f"job-{n}"), fire_time=at()))
            for n in range(3)
        ]
        for _ in range(10):
            await asyncio.sleep(0)
        gate.set()
        results = await asyncio.gather(*running)

    assert pipeline.peak_in_flight == 1
    assert all(result.ran for result in results)


async def test_one_teams_backlog_does_not_block_another(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The reason the per-team limit exists at all: a global limit alone lets one
    # team's midnight sweep fill every slot in the deployment.
    gate = asyncio.Event()
    pipeline = RecordingPipeline(gate=gate)
    limits = ConcurrencyLimits(global_limit=4, team_limit=1)

    async with gateway.begin(scope) as uow:
        executor = JobExecutor(
            recorder=recorder_over(uow.run_traces), pipeline=pipeline, limits=limits
        )
        busy = [
            asyncio.create_task(
                executor.execute(schedule(f"job-payments-{n}", team=TEAM), fire_time=at())
            )
            for n in range(3)
        ]
        other = asyncio.create_task(
            executor.execute(schedule("job-search", team=OTHER_TEAM), fire_time=at())
        )
        for _ in range(10):
            await asyncio.sleep(0)

        assert limits.running_for(TEAM) == 1
        assert limits.running_for(OTHER_TEAM) == 1

        gate.set()
        await asyncio.gather(*busy, other)


async def test_a_permit_is_released_when_the_investigation_fails(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A permit leaked by a failure is a slot the deployment never gets back.
    pipeline = RecordingPipeline(fail_with=RuntimeError("boom"))
    limits = ConcurrencyLimits(global_limit=1, team_limit=1)

    async with gateway.begin(scope) as uow:
        executor = JobExecutor(
            recorder=recorder_over(uow.run_traces), pipeline=pipeline, limits=limits
        )
        await executor.execute(schedule("job-a"), fire_time=at())
        await executor.execute(schedule("job-b"), fire_time=at())

    assert limits.running == 0
    assert len(pipeline.requests) == 2


def test_a_limit_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="stop every scheduled run"):
        ConcurrencyLimits(global_limit=0)
    with pytest.raises(ValueError, match="not a limit"):
        ConcurrencyLimits(global_limit=2, team_limit=4)


# -- reaping -------------------------------------------------------------------


async def test_a_killed_replica_releases_its_job_and_its_run_is_interrupted(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    await store_schedule(gateway, scope, schedule())

    # A replica claims the job, starts the run, and dies.
    async with gateway.begin_system() as system:
        claim = (
            await JobClaimer(dispatcher=system.jobs, worker_id="replica-doomed").claim_due(now=at())
        )[0]

    async with gateway.begin(scope) as uow:
        await recorder_over(uow.run_traces).start_run(
            trigger="schedule",
            principal_id=PRINCIPAL,
            team_node_id=TEAM,
            run_id=fire_key(claim.job_id, at()),
            job_id=claim.job_id,
        )

    # The lease runs out and the reaper comes round.
    report = await LeaseReaper(gateway=gateway).reap(now=at(600))

    assert report.leases_expired == 1
    assert report.runs_interrupted == 1
    assert report.jobs == ("job-dr",)

    async with gateway.begin(scope) as uow:
        run = await uow.run_traces.get_run(fire_key("job-dr", at()))
    assert run is not None
    assert run.status is RunStatus.INTERRUPTED

    # And the job is claimable again, by somebody else.
    async with gateway.begin_system() as system:
        reclaimed = await JobClaimer(dispatcher=system.jobs, worker_id="replica-b").claim_due(
            now=at(601)
        )
    assert [c.job_id for c in reclaimed] == ["job-dr"]


async def test_reaping_a_claim_whose_worker_died_before_starting_marks_nothing(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # An ordinary outcome: the lease released, and nothing else to tidy.
    await store_schedule(gateway, scope, schedule())
    async with gateway.begin_system() as system:
        await JobClaimer(dispatcher=system.jobs, worker_id="replica-doomed").claim_due(now=at())

    report = await LeaseReaper(gateway=gateway).reap(now=at(600))

    assert report.leases_expired == 1
    assert report.runs_interrupted == 0


async def test_reaping_leaves_a_run_that_closed_itself_alone(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The worker's own terminal write is the more informed one.
    await store_schedule(gateway, scope, schedule())
    async with gateway.begin_system() as system:
        claim = (
            await JobClaimer(dispatcher=system.jobs, worker_id="replica-a").claim_due(now=at())
        )[0]

    async with gateway.begin(scope) as uow:
        recorder = recorder_over(uow.run_traces)
        run = await recorder.start_run(
            trigger="schedule",
            principal_id=PRINCIPAL,
            team_node_id=TEAM,
            run_id=fire_key(claim.job_id, at()),
            job_id=claim.job_id,
        )
        await recorder.complete_run(run.run_id, status=RunStatus.COMPLETED, summary="fine")

    report = await LeaseReaper(gateway=gateway).reap(now=at(600))

    assert report.runs_interrupted == 0
    async with gateway.begin(scope) as uow:
        stored = await uow.run_traces.get_run(fire_key("job-dr", at()))
    assert stored is not None
    assert stored.status is RunStatus.COMPLETED
