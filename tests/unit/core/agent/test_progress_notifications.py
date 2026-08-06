"""Telling people a long run is still going, without teaching them to mute it.

The interval decides when a run is worth a word. The cooldown is the half that
matters, and it is the one an implementation without a test quietly loses: a run
long enough to need progress reporting is long enough to produce a notification
per turn, and the channel that gets one of those is muted before the
notification that mattered.
"""

from __future__ import annotations

import pytest

from config.constants.investigation import (
    PROGRESS_NOTIFICATION_COOLDOWN_SECONDS,
    PROGRESS_NOTIFICATION_INTERVAL_SECONDS,
)
from core.agent.interaction import (
    Attention,
    AttentionState,
    ProgressNotifier,
    ProgressReport,
    ProgressSink,
)

pytestmark = pytest.mark.unit


class _CollectingSink:
    def __init__(self, name: str = "slack") -> None:
        self._name = name
        self.delivered: list[ProgressReport] = []

    @property
    def name(self) -> str:
        return self._name

    async def deliver(self, report: ProgressReport) -> None:
        self.delivered.append(report)


class _BrokenSink(_CollectingSink):
    async def deliver(self, report: ProgressReport) -> None:
        raise ConnectionError("the channel is unreachable")


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _report(elapsed: float, *, run_id: str = "run-1") -> ProgressReport:
    return ProgressReport(
        run_id=run_id,
        objective="Why is checkout failing?",
        elapsed_seconds=elapsed,
        iterations=7,
        evidence_count=12,
    )


def _notifier(*sinks: _CollectingSink) -> tuple[ProgressNotifier, _FakeClock]:
    clock = _FakeClock()
    return ProgressNotifier(sinks=tuple(sinks), clock=clock), clock


# --- the interval (FR-018, T034) ------------------------------------------------


async def test_a_run_that_has_not_gone_on_long_enough_says_nothing() -> None:
    slack = _CollectingSink()
    notifier, _ = _notifier(slack)

    outcome = await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS - 1))

    assert not outcome.sent
    assert not outcome.suppressed, "nothing to say is not the same as withholding"
    assert slack.delivered == []


async def test_a_run_past_the_interval_reports_that_it_is_still_going() -> None:
    slack = _CollectingSink()
    notifier, _ = _notifier(slack)

    outcome = await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS))

    assert outcome.sent
    assert outcome.delivered == ("slack",)
    assert "Still investigating" in slack.delivered[0].describe()


async def test_the_report_carries_facts_rather_than_a_half_finished_hypothesis() -> None:
    """A wrong guess put in an incident channel is what everybody starts working
    from."""
    described = _report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS).describe()

    assert "7 step(s)" in described
    assert "12 piece(s) of evidence" in described


async def test_a_sink_that_is_down_does_not_stop_the_others() -> None:
    console = _CollectingSink("console")
    notifier, _ = _notifier(_BrokenSink(), console)

    outcome = await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS))

    assert outcome.delivered == ("console",)
    assert outcome.failed == ("slack",)


# --- the cooldown (FR-019, SC-008, T035) ----------------------------------------


async def test_a_long_run_does_not_report_on_every_turn() -> None:
    """SC-008. Ten checks past the interval inside one cooldown produce one
    notification."""
    slack = _CollectingSink()
    notifier, clock = _notifier(slack)

    for _ in range(10):
        await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS * 4))
        clock.advance(PROGRESS_NOTIFICATION_COOLDOWN_SECONDS / 20)

    assert len(slack.delivered) == 1


async def test_the_second_notification_arrives_once_the_cooldown_has_passed() -> None:
    slack = _CollectingSink()
    notifier, clock = _notifier(slack)

    await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS))
    clock.advance(PROGRESS_NOTIFICATION_COOLDOWN_SECONDS)
    await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS * 3))

    assert len(slack.delivered) == 2


async def test_a_suppressed_notification_says_why_rather_than_only_that_it_was() -> None:
    notifier, _ = _notifier(_CollectingSink())
    await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS))

    outcome = await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS * 2))

    assert outcome.suppressed
    assert "less than" in outcome.suppressed_reason


async def test_one_runs_cooldown_does_not_silence_another() -> None:
    """A notifier shared by a deployment must not let a chatty run suppress a
    quiet one's first report."""
    slack = _CollectingSink()
    notifier, _ = _notifier(slack)

    await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS, run_id="run-1"))
    await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS, run_id="run-2"))

    assert [report.run_id for report in slack.delivered] == ["run-1", "run-2"]


async def test_a_finished_runs_cooldown_is_forgotten() -> None:
    slack = _CollectingSink()
    notifier, _ = _notifier(slack)
    await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS))

    notifier.forget("run-1")
    await notifier.report(_report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS))

    assert len(slack.delivered) == 2


# --- attention exempts a run (FR-020 beside FR-018) ------------------------------


async def test_a_run_already_waiting_on_somebody_is_not_told_it_is_still_going() -> None:
    """Somebody has already been asked, on a surface that is already showing it."""
    slack = _CollectingSink()
    notifier, _ = _notifier(slack)

    outcome = await notifier.report(
        _report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS * 4),
        attention=Attention(state=AttentionState.WAITING_ON_APPROVAL, approvals=1),
    )

    assert not outcome.sent
    assert "already waiting on a human" in outcome.suppressed_reason
    assert slack.delivered == []


async def test_a_run_nobody_is_waiting_on_still_reports() -> None:
    slack = _CollectingSink()
    notifier, _ = _notifier(slack)

    outcome = await notifier.report(
        _report(PROGRESS_NOTIFICATION_INTERVAL_SECONDS), attention=Attention()
    )

    assert outcome.sent


def test_the_progress_sink_port_is_structural() -> None:
    assert isinstance(_CollectingSink(), ProgressSink)


def test_a_report_round_trips_to_a_record() -> None:
    record = _report(600.0).to_record()

    assert record["run_id"] == "run-1"
    assert record["elapsed_seconds"] == 600.0
