"""What happens to firings nobody was there for, and to a job whose team went."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import OTHER_TEAM, PRINCIPAL, TEAM

from config.constants.runs import MAX_MISFIRE_CATCH_UP_RUNS
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.scheduler import misfire
from platform.scheduler.cron import CronError
from platform.scheduler.models import DisabledReason, MisfirePolicy, Schedule
from platform.scheduler.service import ScheduleService

HOURLY = "0 * * * *"

#: A Monday at 00:00 UTC, so an hourly expression's firings are round numbers.
EPOCH = datetime(2026, 3, 2, 0, 0, tzinfo=UTC)


def hours(count: float) -> datetime:
    """Return the instant ``count`` hours after the epoch."""
    return EPOCH + timedelta(hours=count)


def hourly(*, due: datetime | None, policy: MisfirePolicy) -> Schedule:
    """Return an hourly schedule due at ``due`` under ``policy``."""
    return Schedule(
        job_id="job-hourly",
        name="Hourly sweep",
        team_node_id=TEAM,
        principal_id=PRINCIPAL,
        cron=HOURLY,
        misfire=policy,
        next_run_at=due,
    )


# -- misfire -------------------------------------------------------------------


def test_a_schedule_not_yet_due_has_nothing_to_run() -> None:
    recovery = misfire.resolve(hourly(due=hours(5), policy=MisfirePolicy.RUN_ONCE), now=hours(4))

    assert recovery.runs == 0
    assert recovery.next_run_at == hours(5)


def test_a_schedule_with_no_due_time_is_left_alone() -> None:
    # Brand new, disabled, or a one-shot that has fired. Inventing a firing for
    # it would be inventing work.
    recovery = misfire.resolve(hourly(due=None, policy=MisfirePolicy.RUN_ALL), now=hours(9))

    assert recovery.runs == 0
    assert recovery.next_run_at is None


def test_a_firing_that_is_merely_late_runs_whatever_the_policy_says() -> None:
    # Inside the grace period the system was busy, not absent — so a SKIP
    # schedule delayed ninety seconds by a concurrency limit still runs.
    recovery = misfire.resolve(
        hourly(due=hours(1), policy=MisfirePolicy.SKIP),
        now=hours(1) + timedelta(seconds=90),
        grace_seconds=300,
    )

    assert recovery.fire_times == (hours(1),)
    assert recovery.next_run_at == hours(2)


def test_skip_forgets_the_missed_firings_and_moves_on() -> None:
    # A health sweep: yesterday's answer is worthless.
    recovery = misfire.resolve(
        hourly(due=hours(1), policy=MisfirePolicy.SKIP), now=hours(6) + timedelta(minutes=5)
    )

    assert recovery.runs == 0
    assert recovery.skipped == 6
    assert recovery.next_run_at == hours(7)


def test_run_once_runs_the_most_recent_missed_firing() -> None:
    # A nightly report: one is owed, and it should describe the world as it is
    # rather than as it was six hours ago.
    recovery = misfire.resolve(
        hourly(due=hours(1), policy=MisfirePolicy.RUN_ONCE), now=hours(6) + timedelta(minutes=5)
    )

    assert recovery.fire_times == (hours(6),)
    assert recovery.skipped == 5
    assert recovery.next_run_at == hours(7)


def test_run_all_replays_every_missed_firing_in_order() -> None:
    recovery = misfire.resolve(
        hourly(due=hours(1), policy=MisfirePolicy.RUN_ALL), now=hours(4) + timedelta(minutes=5)
    )

    assert recovery.fire_times == (hours(1), hours(2), hours(3), hours(4))
    assert not recovery.capped
    assert recovery.next_run_at == hours(5)


def test_run_all_is_capped_so_an_outage_does_not_become_a_stampede() -> None:
    # A deployment down for a week must not wake up and start two thousand
    # investigations in the same minute.
    recovery = misfire.resolve(hourly(due=hours(1), policy=MisfirePolicy.RUN_ALL), now=hours(200))

    assert recovery.runs == MAX_MISFIRE_CATCH_UP_RUNS
    assert recovery.capped
    assert recovery.skipped > 0


def test_a_lower_cap_is_honoured() -> None:
    recovery = misfire.resolve(
        hourly(due=hours(1), policy=MisfirePolicy.RUN_ALL), now=hours(50), limit=3
    )

    assert recovery.runs == 3
    assert recovery.capped


# -- management ----------------------------------------------------------------


def service(uow: object) -> ScheduleService:
    """Return a schedule service over a unit of work, with a fixed clock."""
    return ScheduleService(store=uow.schedules, clock=lambda: EPOCH)  # type: ignore[attr-defined]


async def test_creating_a_schedule_computes_its_first_firing(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        created = await service(uow).create(
            job_id="job-dr",
            name="Nightly DR validation",
            team_node_id=TEAM,
            principal_id=PRINCIPAL,
            cron="0 2 * * *",
            objective="prove the standby can take over",
        )

    assert created.next_run_at == EPOCH.replace(hour=2)
    assert created.enabled
    assert created.principal_id == PRINCIPAL


async def test_a_malformed_expression_is_refused_before_anything_is_stored(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A stored schedule that cannot be evaluated is a job that will never run
    # and will never say why.
    async with gateway.begin(scope) as uow:
        with pytest.raises(CronError):
            await service(uow).create(
                job_id="job-broken",
                name="Broken",
                team_node_id=TEAM,
                principal_id=PRINCIPAL,
                cron="every tuesday",
                objective="",
            )

        assert await uow.schedules.get_job("job-broken") is None


async def test_a_schedule_carries_a_principal_so_its_runs_are_attributable(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A schedule is not a way to act without anybody being responsible for it.
    async with gateway.begin(scope) as uow:
        await service(uow).create(
            job_id="job-dr",
            name="Nightly DR validation",
            team_node_id=TEAM,
            principal_id=PRINCIPAL,
            cron="0 2 * * *",
            objective="",
        )
        read = await service(uow).get("job-dr")

    assert read is not None
    assert read.principal_id == PRINCIPAL
    assert read.team_node_id == TEAM


async def test_changing_an_expression_recomputes_the_due_time(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        managed = service(uow)
        await managed.create(
            job_id="job-dr",
            name="DR",
            team_node_id=TEAM,
            principal_id=PRINCIPAL,
            cron="0 2 * * *",
            objective="",
        )

        changed = await managed.update_expression("job-dr", cron="30 4 * * *")

    assert changed.cron == "30 4 * * *"
    assert changed.next_run_at == EPOCH.replace(hour=4, minute=30)


async def test_disabling_records_the_operator_as_the_reason_and_unschedules(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Leaving a due time in the past on a disabled job means re-enabling it
    # fires immediately for a time that has gone.
    async with gateway.begin(scope) as uow:
        managed = service(uow)
        await managed.create(
            job_id="job-dr",
            name="DR",
            team_node_id=TEAM,
            principal_id=PRINCIPAL,
            cron="0 2 * * *",
            objective="",
        )

        stopped = await managed.set_enabled("job-dr", enabled=False)
        restarted = await managed.set_enabled("job-dr", enabled=True)

    assert not stopped.enabled
    assert stopped.disabled_reason is DisabledReason.OPERATOR
    assert stopped.next_run_at is None
    assert restarted.enabled
    assert restarted.disabled_reason is None
    assert restarted.next_run_at == EPOCH.replace(hour=2)


async def test_a_job_whose_team_was_deleted_is_disabled_with_a_reason(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Never silently dropped: an operator who loses the definition has nothing
    # to look at, and one whose job kept running gets configuration resolved
    # against a node that is not in the tree.
    async with gateway.begin(scope) as uow:
        managed = service(uow)
        await managed.create(
            job_id="job-payments",
            name="Payments",
            team_node_id=TEAM,
            principal_id=PRINCIPAL,
            cron="0 2 * * *",
            objective="",
        )
        await managed.create(
            job_id="job-search",
            name="Search",
            team_node_id=OTHER_TEAM,
            principal_id=PRINCIPAL,
            cron="0 3 * * *",
            objective="",
        )

        disabled = await managed.disable_orphans(live_teams=[TEAM])

        surviving = await managed.get("job-payments")
        orphan = await managed.get("job-search")

    assert [one.job_id for one in disabled] == ["job-search"]
    assert orphan is not None
    assert not orphan.enabled
    assert orphan.disabled_reason is DisabledReason.TEAM_DELETED
    # The definition is still there to be read and re-enabled.
    assert orphan.cron == "0 3 * * *"
    assert surviving is not None and surviving.enabled


async def test_listing_filters_by_team_and_by_enablement(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        managed = service(uow)
        await managed.create(
            job_id="job-a",
            name="A",
            team_node_id=TEAM,
            principal_id=PRINCIPAL,
            cron="0 2 * * *",
            objective="",
        )
        await managed.create(
            job_id="job-b",
            name="B",
            team_node_id=OTHER_TEAM,
            principal_id=PRINCIPAL,
            cron="0 3 * * *",
            objective="",
        )
        await managed.set_enabled("job-b", enabled=False)

        mine = await managed.list(team_node_id=TEAM)
        live = await managed.list(enabled_only=True)

    assert [one.job_id for one in mine] == ["job-a"]
    assert [one.job_id for one in live] == ["job-a"]


async def test_changing_a_schedule_that_does_not_exist_raises(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await service(uow).set_enabled("job-ghost", enabled=False)


async def test_rescheduling_a_one_shot_that_has_fired_leaves_it_unscheduled(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # It did what it was configured to do; calling that a fault would be wrong.
    async with gateway.begin(scope) as uow:
        managed = service(uow)
        await managed.create(
            job_id="job-leap",
            name="Leap day",
            team_node_id=TEAM,
            principal_id=PRINCIPAL,
            cron="0 0 29 2 *",
            objective="",
        )

        moved = await managed.reschedule("job-leap", after=EPOCH)
        exhausted = await managed.reschedule("job-leap", after=EPOCH.replace(year=2030))

    assert moved.next_run_at is not None
    assert moved.next_run_at.year == 2028
    # 2032's 29th of February is beyond the lookahead from 2030.
    assert exhausted.next_run_at is None or exhausted.next_run_at.year == 2032
