"""A claimed job reaches the runner its kind names, or fails where somebody looks.

Three job kinds have been definable since they were written and have never run:
nothing existed that could take a claim and decide what to do with it. The gap is
the worst shape a scheduling defect takes — an operator registers a nightly sync,
the console shows it enabled and due, and the corpus quietly describes last
quarter for ever.

So the property under test is not "the runner was called". It is that **every
claim ends in an outcome somebody can read**: dispatched to its runner, or
released with a failure naming the kind that had none. A claim that ended
silently — swallowed, or held until its lease lapsed — is the failure this module
exists to remove, and it is asserted here in as many words.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest
from conftest import at

from config.constants.knowledge import (
    CORPUS_SYNC_JOB_KIND,
    KNOWLEDGE_SYNC_JOB_KIND,
    TOPOLOGY_DISCOVERY_JOB_KIND,
)
from platform.persistence.ports import (
    JobOutcome,
    PersistenceGateway,
    ScheduledJob,
    TenantScope,
)
from platform.scheduler.claiming import JobClaimer
from platform.scheduler.dispatch import (
    JobContext,
    JobKindDispatcher,
    ScheduledJobWorker,
    next_due,
)

NIGHTLY = "0 2 * * *"


@dataclass(slots=True)
class RecordingRunner:
    """A runner that records what it was handed and answers immediately."""

    record: Mapping[str, Any] = field(default_factory=lambda: {"ran": True})
    fail_with: Exception | None = None
    seen: list[JobContext] = field(default_factory=list)

    async def run(self, context: JobContext) -> Mapping[str, Any]:
        """Record ``context`` and return this runner's record."""
        self.seen.append(context)
        if self.fail_with is not None:
            raise self.fail_with
        return dict(self.record)


def job(
    *,
    kind: str = KNOWLEDGE_SYNC_JOB_KIND,
    job_id: str = "knowledge.sync:wiki",
    schedule: str = NIGHTLY,
    payload: Mapping[str, Any] | None = None,
) -> ScheduledJob:
    """Return a job of ``kind`` already due at the fixed epoch."""
    return ScheduledJob(
        job_id=job_id,
        name=f"{kind} for the suite",
        kind=kind,
        schedule=schedule,
        next_run_at=at(-1),
        payload=dict(payload or {"source": "wiki"}),
    )


async def store(gateway: PersistenceGateway, scope: TenantScope, one: ScheduledJob) -> None:
    """Persist ``one`` so a dispatcher can find it due."""
    async with gateway.begin(scope) as uow:
        await uow.schedules.upsert_job(one)


async def stored_job(
    gateway: PersistenceGateway, scope: TenantScope, job_id: str
) -> ScheduledJob | None:
    """Return the job as the store now holds it."""
    async with gateway.begin(scope) as uow:
        return await uow.schedules.get_job(job_id)


def worker_over(
    gateway: PersistenceGateway,
    dispatcher: JobKindDispatcher,
    *,
    worker_id: str = "replica-a",
) -> ScheduledJobWorker:
    """Return a worker claiming through ``gateway`` and dispatching by kind."""
    return ScheduledJobWorker(gateway=gateway, dispatcher=dispatcher, worker_id=worker_id)


# -- dispatch ------------------------------------------------------------------


async def test_a_due_job_reaches_the_runner_its_kind_names(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    runner = RecordingRunner(record={"stored": 3})
    await store(gateway, scope, job())

    results = await worker_over(gateway, JobKindDispatcher({KNOWLEDGE_SYNC_JOB_KIND: runner})).tick(
        now=at()
    )

    assert [one.job_id for one in results] == ["knowledge.sync:wiki"]
    assert results[0].outcome is JobOutcome.SUCCEEDED
    assert results[0].record == {"stored": 3}
    assert [context.job.kind for context in runner.seen] == [KNOWLEDGE_SYNC_JOB_KIND]


async def test_each_kind_reaches_its_own_runner_and_no_other(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    runners = {
        KNOWLEDGE_SYNC_JOB_KIND: RecordingRunner(),
        CORPUS_SYNC_JOB_KIND: RecordingRunner(),
        TOPOLOGY_DISCOVERY_JOB_KIND: RecordingRunner(),
    }
    for kind in runners:
        await store(gateway, scope, job(kind=kind, job_id=f"{kind}:wiki"))

    results = await worker_over(gateway, JobKindDispatcher(dict(runners))).tick(now=at())

    assert len(results) == 3
    assert {one.outcome for one in results} == {JobOutcome.SUCCEEDED}
    for kind, runner in runners.items():
        assert [context.job.kind for context in runner.seen] == [kind]


async def test_a_kind_with_no_runner_fails_with_the_kind_named(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The silent failure this module exists to remove, asserted directly."""
    await store(gateway, scope, job(kind="knowledge.telepathy", job_id="telepathy:wiki"))

    results = await worker_over(gateway, JobKindDispatcher({})).tick(now=at())

    assert results[0].outcome is JobOutcome.FAILED
    assert "knowledge.telepathy" in results[0].failure


async def test_a_kind_with_no_runner_still_releases_its_claim(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A job nobody can run must come due again, not sit under a dead lease."""
    await store(
        gateway,
        scope,
        job(kind="knowledge.telepathy", job_id="telepathy:wiki", schedule="every 60s"),
    )
    dispatcher = JobKindDispatcher({})

    await worker_over(gateway, dispatcher).tick(now=at())
    again = await worker_over(gateway, dispatcher, worker_id="replica-b").tick(now=at(5))

    assert [one.job_id for one in again] == ["telepathy:wiki"]


async def test_a_runner_that_raises_records_the_failure_and_releases(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    runner = RecordingRunner(fail_with=RuntimeError("the wiki refused the token"))
    await store(gateway, scope, job())

    results = await worker_over(gateway, JobKindDispatcher({KNOWLEDGE_SYNC_JOB_KIND: runner})).tick(
        now=at()
    )

    assert results[0].outcome is JobOutcome.FAILED
    assert "the wiki refused the token" in results[0].failure
    stored = await stored_job(gateway, scope, "knowledge.sync:wiki")
    assert stored is not None
    assert stored.last_outcome is JobOutcome.FAILED


async def test_a_second_runner_for_one_kind_is_refused(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Two runners for one kind is a job that runs twice, or runs the wrong one."""
    dispatcher = JobKindDispatcher({KNOWLEDGE_SYNC_JOB_KIND: RecordingRunner()})

    with pytest.raises(ValueError, match=KNOWLEDGE_SYNC_JOB_KIND):
        dispatcher.register(KNOWLEDGE_SYNC_JOB_KIND, RecordingRunner())


# -- what happens next ---------------------------------------------------------


async def test_a_successful_run_is_scheduled_again_from_its_own_expression(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    await store(gateway, scope, job())

    await worker_over(
        gateway, JobKindDispatcher({KNOWLEDGE_SYNC_JOB_KIND: RecordingRunner()})
    ).tick(now=at())

    stored = await stored_job(gateway, scope, "knowledge.sync:wiki")
    assert stored is not None
    assert stored.next_run_at == next_due(job(), after=at())
    assert stored.next_run_at is not None and stored.next_run_at > at()


async def test_a_failed_run_is_scheduled_again_too(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A sync that failed tonight still syncs tomorrow; failure is not deletion."""
    runner = RecordingRunner(fail_with=RuntimeError("the wiki was unreachable"))
    await store(gateway, scope, job())

    await worker_over(gateway, JobKindDispatcher({KNOWLEDGE_SYNC_JOB_KIND: runner})).tick(now=at())

    stored = await stored_job(gateway, scope, "knowledge.sync:wiki")
    assert stored is not None and stored.next_run_at is not None
    assert stored.next_run_at > at()


def test_the_interval_vocabulary_schedules_as_well_as_the_cron_one() -> None:
    """Discovery declarations write ``every Ns``; the scheduler owns cron."""
    assert next_due(job(schedule="every 900s"), after=at()) == at(15)
    assert next_due(job(schedule="0 2 * * *"), after=at()) == datetime(
        2026, 3, 2, 2, 0, tzinfo=at().tzinfo
    )


def test_an_expression_that_parses_as_neither_leaves_the_job_unscheduled() -> None:
    """Unscheduled rather than firing immediately for a time nobody can name."""
    assert next_due(job(schedule="whenever the mood takes it"), after=at()) is None


async def test_a_job_deleted_while_it_was_claimed_does_not_strand_the_worker(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The operator deleted it mid-flight; the worker reports it and carries on."""
    await store(gateway, scope, job())
    worker = worker_over(gateway, JobKindDispatcher({KNOWLEDGE_SYNC_JOB_KIND: RecordingRunner()}))

    async with gateway.begin_system() as system:
        claim = (
            await JobClaimer(dispatcher=system.jobs, worker_id="replica-a").claim_due(now=at())
        )[0]
    async with gateway.begin(scope) as uow:
        await uow.schedules.delete_job("knowledge.sync:wiki")

    result = await worker.run_claim(claim, now=at())

    assert result.outcome is JobOutcome.FAILED
    assert "knowledge.sync:wiki" in result.failure
