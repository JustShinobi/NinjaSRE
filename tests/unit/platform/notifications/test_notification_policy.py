"""Who gets told, who does not, and the record of both."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.notifications import (
    CRITICAL_NOTIFICATION_COOLDOWN_SECONDS,
    MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW,
    NOTIFICATION_COOLDOWN_SECONDS,
)
from platform.notifications.cooldown import Cooldown
from platform.notifications.limits import RateLimiter
from platform.notifications.models import (
    Notification,
    NotificationDecision,
    NotificationSink,
    Outcome,
    Severity,
    SinkKind,
)
from platform.notifications.policy import NotificationPolicy, QuietHours
from platform.reporting.models import Audience

TEAM = "team-payments"
DAYTIME = datetime(2026, 3, 1, 14, 0, tzinfo=UTC)
NIGHT = datetime(2026, 3, 1, 3, 14, tzinfo=UTC)


def sink(kind: SinkKind, target: str = "somewhere") -> NotificationSink:
    """Return a verified sink of ``kind``."""
    return NotificationSink(kind=kind, target=target, verified=True)


ALL_SINKS = (
    sink(SinkKind.PAGERDUTY, "routing-key"),
    sink(SinkKind.PUSHOVER, "user-key"),
    sink(SinkKind.CHAT, "#incidents"),
    sink(SinkKind.EMAIL, "oncall@example.invalid"),
    sink(SinkKind.WEBHOOK, "https://example.invalid/hook"),
)


def notification(**overrides: object) -> Notification:
    """Return a notification about one subject."""
    fields: dict[str, object] = {
        "subject": "checkout-latency",
        "title": "Checkout latency: connection pool exhausted",
        "message": "The 14:02 deploy narrowed the pool.",
        "severity": Severity.HIGH,
        "outcome": Outcome.UNRESOLVED,
        "team_node_id": TEAM,
        "run_id": "run-1",
        "link": "https://ninjasre.invalid/runs/run-1",
    }
    fields.update(overrides)
    return Notification(**fields)  # type: ignore[arg-type]


def policy(**overrides: object) -> NotificationPolicy:
    """Return a policy over every sink kind."""
    fields: dict[str, object] = {
        "sinks": ALL_SINKS,
        "cooldown": Cooldown(),
        "limits": RateLimiter(),
    }
    fields.update(overrides)
    return NotificationPolicy(**fields)  # type: ignore[arg-type]


def kinds_of(sinks: tuple[NotificationSink, ...]) -> set[SinkKind]:
    """Return the kinds a routing chose."""
    return {item.kind for item in sinks}


# -- T033/FR-015: routing by severity and outcome -------------------------------


def test_a_critical_unresolved_outcome_reaches_the_paging_sinks() -> None:
    routing = policy().route(notification(severity=Severity.CRITICAL), at=DAYTIME)

    assert SinkKind.PAGERDUTY in kinds_of(routing.sinks)
    assert SinkKind.PUSHOVER in kinds_of(routing.sinks)
    assert routing.decision is NotificationDecision.SENT


def test_a_high_outcome_reaches_pushover_and_chat_but_not_pagerduty() -> None:
    routing = policy().route(notification(severity=Severity.HIGH), at=DAYTIME)

    assert kinds_of(routing.sinks) == {SinkKind.PUSHOVER, SinkKind.CHAT, SinkKind.WEBHOOK}


def test_a_medium_outcome_reaches_chat_only() -> None:
    routing = policy().route(notification(severity=Severity.MEDIUM), at=DAYTIME)

    assert not any(item.pages for item in routing.sinks)
    assert SinkKind.CHAT in kinds_of(routing.sinks)


def test_noise_notifies_nobody_and_says_so() -> None:
    routing = policy().route(
        notification(severity=Severity.NOISE, outcome=Outcome.NOISE), at=DAYTIME
    )

    assert routing.sinks == ()
    assert routing.decision is NotificationDecision.NO_SINK
    assert "noise" in routing.records[0].reason


def test_a_resolved_outcome_never_wakes_anybody_however_severe_it_was() -> None:
    routing = policy().route(
        notification(severity=Severity.CRITICAL, outcome=Outcome.RESOLVED), at=DAYTIME
    )

    assert routing.sinks
    assert not any(item.pages for item in routing.sinks)


def test_a_team_with_no_matching_sink_is_recorded_rather_than_silent() -> None:
    routing = NotificationPolicy(sinks=(sink(SinkKind.PAGERDUTY),)).route(
        notification(severity=Severity.MEDIUM), at=DAYTIME
    )

    assert routing.sinks == ()
    assert routing.decision is NotificationDecision.NO_SINK
    assert "no enabled sink" in routing.records[0].reason


def test_a_disabled_sink_is_not_routed_to() -> None:
    disabled = NotificationSink(
        kind=SinkKind.CHAT, target="#incidents", verified=True, enabled=False
    )

    routing = NotificationPolicy(sinks=(disabled,)).route(
        notification(severity=Severity.MEDIUM), at=DAYTIME
    )

    assert routing.sinks == ()


# -- T034/FR-023: quiet hours ---------------------------------------------------


def quiet() -> QuietHours:
    """Return the default quiet-hours window."""
    return QuietHours()


def test_a_non_critical_notification_in_quiet_hours_leaves_the_paging_sinks() -> None:
    routing = policy(quiet_hours=quiet()).route(notification(severity=Severity.HIGH), at=NIGHT)

    assert not any(item.pages for item in routing.sinks)
    assert SinkKind.CHAT in kinds_of(routing.sinks)
    assert routing.diverted
    assert routing.decision is NotificationDecision.DIVERTED


def test_a_critical_notification_ignores_quiet_hours() -> None:
    routing = policy(quiet_hours=quiet()).route(notification(severity=Severity.CRITICAL), at=NIGHT)

    assert SinkKind.PAGERDUTY in kinds_of(routing.sinks)
    assert not routing.diverted


def test_quiet_hours_do_not_apply_during_the_day() -> None:
    routing = policy(quiet_hours=quiet()).route(notification(severity=Severity.HIGH), at=DAYTIME)

    assert SinkKind.PUSHOVER in kinds_of(routing.sinks)
    assert not routing.diverted


def test_quiet_hours_are_evaluated_in_the_team_timezone() -> None:
    # 03:14 UTC is 14:14 in Auckland, which is the middle of the working day.
    routing = policy(quiet_hours=QuietHours(timezone="Pacific/Auckland")).route(
        notification(severity=Severity.HIGH), at=NIGHT
    )

    assert SinkKind.PUSHOVER in kinds_of(routing.sinks)


def test_a_window_that_wraps_midnight_covers_both_sides_of_it() -> None:
    window = QuietHours(start_hour=22, end_hour=7)

    assert window.covers(datetime(2026, 3, 1, 23, 0, tzinfo=UTC))
    assert window.covers(datetime(2026, 3, 1, 2, 0, tzinfo=UTC))
    assert not window.covers(datetime(2026, 3, 1, 12, 0, tzinfo=UTC))


def test_quiet_hours_can_be_switched_off() -> None:
    assert not QuietHours(enabled=False).covers(NIGHT)


def test_an_impossible_quiet_hours_boundary_is_refused() -> None:
    with pytest.raises(ValueError, match="hour of the day"):
        QuietHours(start_hour=25)


def test_quiet_hours_with_no_non_paging_sink_left_is_recorded() -> None:
    routing = NotificationPolicy(sinks=(sink(SinkKind.PUSHOVER),), quiet_hours=quiet()).route(
        notification(severity=Severity.HIGH), at=NIGHT
    )

    assert routing.sinks == ()
    assert [record.decision for record in routing.records] == [
        NotificationDecision.DIVERTED,
        NotificationDecision.NO_SINK,
    ]


# -- T035/SC-004: cooldown ------------------------------------------------------


def test_a_repeat_within_the_cooldown_is_suppressed_and_recorded() -> None:
    live = policy()
    first = live.route(notification(), at=DAYTIME)
    live.commit(first, at=DAYTIME)

    second = live.route(notification(), at=DAYTIME + timedelta(seconds=60))

    assert second.sinks == ()
    assert second.decision is NotificationDecision.SUPPRESSED
    assert len(live.cooldown.suppressions) == 1
    assert live.cooldown.suppressions[0].subject == "checkout-latency"


def test_a_repeat_after_the_cooldown_is_sent() -> None:
    live = policy()
    live.commit(live.route(notification(), at=DAYTIME), at=DAYTIME)

    later = live.route(
        notification(), at=DAYTIME + timedelta(seconds=NOTIFICATION_COOLDOWN_SECONDS + 1)
    )

    assert later.sends


def test_a_different_subject_is_not_suppressed_by_the_first_one() -> None:
    live = policy()
    live.commit(live.route(notification(), at=DAYTIME), at=DAYTIME)

    other = live.route(notification(subject="payments-errors"), at=DAYTIME)

    assert other.sends


def test_the_same_subject_at_a_higher_severity_is_not_suppressed() -> None:
    live = policy()
    live.commit(live.route(notification(severity=Severity.MEDIUM), at=DAYTIME), at=DAYTIME)

    worse = live.route(notification(severity=Severity.CRITICAL), at=DAYTIME)

    assert worse.sends


def test_a_critical_subject_has_a_shorter_cooldown() -> None:
    live = policy()
    critical = notification(severity=Severity.CRITICAL)
    live.commit(live.route(critical, at=DAYTIME), at=DAYTIME)

    inside = live.route(
        critical, at=DAYTIME + timedelta(seconds=CRITICAL_NOTIFICATION_COOLDOWN_SECONDS - 1)
    )
    outside = live.route(
        critical, at=DAYTIME + timedelta(seconds=CRITICAL_NOTIFICATION_COOLDOWN_SECONDS + 1)
    )

    assert not inside.sends
    assert outside.sends


def test_every_suppression_says_what_would_have_been_said() -> None:
    live = policy()
    live.commit(live.route(notification(), at=DAYTIME), at=DAYTIME)
    live.route(notification(), at=DAYTIME + timedelta(seconds=60))

    described = live.cooldown.suppressions[0].describe()

    assert "Checkout latency: connection pool exhausted" in described
    assert "checkout-latency" in described


def test_the_suppression_record_is_bounded() -> None:
    live = Cooldown(max_retained=3)
    note = notification()
    live.record_sent(note, at=DAYTIME)
    for offset in range(10):
        live.check(note, at=DAYTIME + timedelta(seconds=offset))

    assert len(live.suppressions) == 3


def test_an_operator_can_ask_what_one_team_was_not_told() -> None:
    live = policy()
    live.commit(live.route(notification(), at=DAYTIME), at=DAYTIME)
    live.route(notification(), at=DAYTIME + timedelta(seconds=60))

    assert len(live.cooldown.suppressions_for(TEAM)) == 1
    assert live.cooldown.suppressions_for("team-other") == ()


# -- T036/FR-017: rate limits ---------------------------------------------------


def test_a_team_is_bounded_across_every_sink() -> None:
    live = policy()
    for index in range(MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW):
        routing = live.route(notification(subject=f"subject-{index}"), at=DAYTIME)
        live.commit(routing, at=DAYTIME)

    over = live.route(notification(subject="one-too-many"), at=DAYTIME)

    assert over.sinks == ()
    assert over.decision is NotificationDecision.RATE_LIMITED


def test_the_rate_limit_window_slides() -> None:
    live = policy()
    for index in range(MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW):
        live.commit(live.route(notification(subject=f"s-{index}"), at=DAYTIME), at=DAYTIME)

    later = live.route(notification(subject="after"), at=DAYTIME + timedelta(seconds=3_601))

    assert later.sends


def test_one_teams_volume_does_not_limit_another() -> None:
    live = policy()
    for index in range(MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW):
        live.commit(live.route(notification(subject=f"s-{index}"), at=DAYTIME), at=DAYTIME)

    other = live.route(notification(subject="theirs", team_node_id="team-search"), at=DAYTIME)

    assert other.sends


def test_checking_the_limit_does_not_spend_it() -> None:
    limiter = RateLimiter()

    for _ in range(MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW + 5):
        assert limiter.check(TEAM, at=DAYTIME).allowed


# -- T037: what an operator is shown -------------------------------------------


def test_the_rate_limit_report_names_the_teams_that_hit_it() -> None:
    live = policy()
    for index in range(MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW):
        live.commit(live.route(notification(subject=f"s-{index}"), at=DAYTIME), at=DAYTIME)
    live.route(notification(subject="over"), at=DAYTIME)

    report = live.limits.report(at=DAYTIME)

    assert report["rate_limited_teams"] == [TEAM]
    assert report["used"][TEAM] == MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW


def test_nothing_is_committed_when_nothing_was_routed() -> None:
    live = policy()
    routing = live.route(notification(severity=Severity.NOISE, outcome=Outcome.NOISE), at=DAYTIME)

    live.commit(routing, at=DAYTIME)

    assert live.limits.report(at=DAYTIME)["used"] == {}
    assert live.cooldown.sent == {}


def test_a_sink_audience_is_carried_through_routing() -> None:
    public = NotificationSink(
        kind=SinkKind.CHAT, target="#status", verified=True, audience=Audience.PUBLIC
    )

    routing = NotificationPolicy(sinks=(public,)).route(
        notification(severity=Severity.MEDIUM), at=DAYTIME
    )

    assert routing.sinks[0].audience is Audience.PUBLIC
