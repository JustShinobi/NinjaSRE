"""Reclaiming traces without losing the history, and reading that history back."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
from conftest import PRINCIPAL, TEAM, at

from config.constants.runs import TRIGGER_ALERT, TRIGGER_SCHEDULE
from platform.persistence.ports import ActorKind, AuditEvent, PrincipalKind, RunStatus, UnitOfWork
from platform.runs.history import RunHistory, RunQuery
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder
from platform.runs.retention import TraceRetention

OTHER_TEAM = "team-search"


def recorder(uow: UnitOfWork, clock: Callable[[], datetime], *, prefix: str = "id") -> RunRecorder:
    """Return a recorder over the unit of work.

    ``prefix`` keeps identifiers unique across the several runs a test records:
    two runs whose turns shared an id would be two runs sharing a turn, and the
    store is keyed by id exactly as PostgreSQL is.
    """
    counter = iter(range(10_000))
    return RunRecorder(
        store=uow.run_traces, clock=clock, ids=lambda: f"{prefix}-{next(counter):04d}"
    )


async def finished_run(
    uow: UnitOfWork,
    clock: Callable[[], datetime],
    *,
    run_id: str,
    trigger: str = TRIGGER_ALERT,
    team: str = TEAM,
    job_id: str | None = None,
    cost: float = 0.02,
    status: RunStatus = RunStatus.COMPLETED,
) -> str:
    """Record and close one run, and return its id."""
    writer = recorder(uow, clock, prefix=run_id)
    run = await writer.start_run(
        trigger=trigger,
        principal_id=PRINCIPAL,
        team_node_id=team,
        run_id=run_id,
        job_id=job_id,
    )
    turn = await writer.record_turn(
        RecordedTurn(
            run_id=run.run_id,
            index=0,
            model="claude-opus-5",
            prompt_tokens=500,
            completion_tokens=120,
            cost=cost,
        )
    )
    await writer.record_call(
        RecordedCall(run_id=run.run_id, turn_id=turn.turn_id, name="loki.query")
    )
    await writer.record_evidence(
        run_id=run.run_id, source="loki", evidence_type="log", body={"lines": 3}
    )
    await writer.complete_run(run.run_id, status=status, summary="Pool exhaustion.")
    return run.run_id


# -- retention -----------------------------------------------------------------


async def test_retention_removes_the_trace_and_keeps_the_run_and_its_summary(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    run_id = await finished_run(uow, clock, run_id="run-old")
    await uow.audit.append(
        AuditEvent(
            event_id="audit-1",
            occurred_at=at(),
            actor_kind=ActorKind.SYSTEM,
            actor_id=run_id,
            action="capability.invoke",
            resource_kind="run",
            resource_id=run_id,
        )
    )

    retention = TraceRetention(store=uow.run_traces, retention_days=30)
    report = await retention.sweep(now=at() + timedelta(days=90))

    trace = await uow.run_traces.replay(run_id)

    assert report.runs_stripped == 1
    assert report.records_removed > 0
    assert trace.turns == () and trace.tool_calls == () and trace.evidence == ()
    assert trace.events == ()
    # The run and what it concluded survive — the history is the point.
    assert trace.run.summary == "Pool exhaustion."
    assert trace.run.status is RunStatus.COMPLETED
    # And the audit trail is untouched by any of it.
    assert await uow.audit.get("audit-1") is not None


async def test_retention_leaves_a_run_inside_the_window_alone(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    run_id = await finished_run(uow, clock, run_id="run-recent")

    report = await TraceRetention(store=uow.run_traces, retention_days=30).sweep(
        now=at() + timedelta(days=5)
    )

    assert report.runs_stripped == 0
    assert (await uow.run_traces.replay(run_id)).turns != ()


async def test_retention_never_strips_a_run_that_is_still_going(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # Stripping one mid-flight would delete the trace the recorder is writing.
    writer = recorder(uow, clock)
    run = await writer.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id="run-live"
    )
    await writer.record_turn(RecordedTurn(run_id=run.run_id, index=0, model="m"))

    report = await TraceRetention(store=uow.run_traces, retention_days=1).sweep(
        now=at() + timedelta(days=400)
    )

    assert report.runs_stripped == 0
    assert (await uow.run_traces.replay(run.run_id)).turns != ()


async def test_a_retention_window_of_zero_days_removes_nothing(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # "Keep indefinitely" has to be expressible, and it must not read as
    # "delete everything immediately".
    await finished_run(uow, clock, run_id="run-kept")

    report = await TraceRetention(store=uow.run_traces, retention_days=0).sweep(
        now=at() + timedelta(days=4_000)
    )

    assert report.cutoff is None
    assert report.runs_stripped == 0


# -- history -------------------------------------------------------------------


async def test_scheduled_and_interactive_runs_share_one_history(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    # They differ in trigger and principal and in nothing else. A console with
    # two lists makes "what has this team been doing" a question you answer
    # twice and then reconcile.
    await finished_run(uow, clock, run_id="run-alert", trigger=TRIGGER_ALERT)
    await finished_run(uow, clock, run_id="run-nightly", trigger=TRIGGER_SCHEDULE, job_id="job-dr")

    history = RunHistory(store=uow.run_traces)

    assert {run.run_id for run in await history.list_runs()} == {"run-alert", "run-nightly"}
    scheduled = await history.list_runs(RunQuery(trigger=TRIGGER_SCHEDULE))
    assert [run.run_id for run in scheduled] == ["run-nightly"]
    by_job = await history.list_runs(RunQuery(job_id="job-dr"))
    assert [run.run_id for run in by_job] == ["run-nightly"]


async def test_history_filters_by_team_status_and_time_range(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    await finished_run(uow, clock, run_id="run-payments", team=TEAM)
    await finished_run(uow, clock, run_id="run-search", team=OTHER_TEAM)
    await finished_run(uow, clock, run_id="run-failed", team=TEAM, status=RunStatus.FAILED)

    history = RunHistory(store=uow.run_traces)

    by_team = await history.list_runs(RunQuery(team_node_id=TEAM))
    assert {run.run_id for run in by_team} == {"run-payments", "run-failed"}

    failed = await history.list_runs(RunQuery(team_node_id=TEAM, status=RunStatus.FAILED))
    assert [run.run_id for run in failed] == ["run-failed"]

    later = await history.list_runs(RunQuery(since=at() + timedelta(days=1)))
    assert later == ()


async def test_a_sub_agent_run_is_not_a_second_investigation_in_the_list(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    writer = recorder(uow, clock)
    parent = await writer.start_run(
        trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id="run-parent"
    )
    child = await writer.start_subagent_run(
        parent_run_id=parent.run_id,
        objective="check the pool",
        principal_id=PRINCIPAL,
        team_node_id=TEAM,
        run_id="run-child",
    )

    history = RunHistory(store=uow.run_traces)

    assert [run.run_id for run in await history.list_runs()] == ["run-parent"]
    assert {run.run_id for run in await history.list_runs(RunQuery(include_subagents=True))} == {
        "run-parent",
        "run-child",
    }
    assert [run.run_id for run in await history.children_of("run-parent")] == [child.run_id]


async def test_cost_is_aggregated_per_run_and_per_team(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    await finished_run(uow, clock, run_id="run-a", team=TEAM, cost=0.02)
    await finished_run(uow, clock, run_id="run-b", team=TEAM, cost=0.05)
    await finished_run(uow, clock, run_id="run-c", team=OTHER_TEAM, cost=1.00)

    history = RunHistory(store=uow.run_traces)

    one = await history.cost_of("run-a")
    assert one.cost == pytest.approx(0.02)
    assert one.total_tokens == 620

    team = await history.cost_over(RunQuery(team_node_id=TEAM))
    assert team.runs == 2
    assert team.cost == pytest.approx(0.07)
    assert team.turns == 2


async def test_a_period_summary_covers_only_the_window_it_was_asked_for(
    uow: UnitOfWork, clock: Callable[[], datetime]
) -> None:
    await finished_run(uow, clock, run_id="run-in", cost=0.10)

    history = RunHistory(store=uow.run_traces)
    outside = await history.cost_over(RunQuery(since=at() + timedelta(hours=2)))

    assert outside.runs == 0
    assert outside.cost == pytest.approx(0.0)


def test_a_principal_kind_exists_for_a_schedule_to_act_as() -> None:
    # A scheduled run is attributed, not anonymous: the schedule's principal is
    # what an approval inside it attributes to.
    assert PrincipalKind.SERVICE_ACCOUNT.value
