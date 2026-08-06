"""Cron evaluation, and the two nights a year it is worth testing."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from platform.scheduler.cron import CronError, CronExpression

LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")


def at(text: str, zone: ZoneInfo = UTC) -> datetime:  # type: ignore[assignment]
    """Return the instant ``text`` names in ``zone``."""
    return datetime.fromisoformat(text).replace(tzinfo=zone)


# -- parsing -------------------------------------------------------------------


def test_a_plain_expression_parses() -> None:
    expression = CronExpression.parse("30 2 * * *")

    assert expression.minutes == frozenset({30})
    assert expression.hours == frozenset({2})
    assert len(expression.days) == 31


@pytest.mark.parametrize(
    "source",
    [
        "30 2 * *",
        "30 2 * * * *",
        "60 2 * * *",
        "30 24 * * *",
        "30 2 0 * *",
        "30 2 * 13 *",
        "banana 2 * * *",
        "30-10 2 * * *",
        "30 2 * * */0",
    ],
)
def test_a_malformed_expression_is_refused_at_parse_time(source: str) -> None:
    # At parse rather than at fire: a schedule that only reveals it is broken on
    # the night it was meant to run is one nobody hears about until morning.
    with pytest.raises(CronError):
        CronExpression.parse(source)


def test_an_unknown_timezone_is_refused() -> None:
    with pytest.raises(CronError):
        CronExpression.parse("0 2 * * *", timezone="Mars/Olympus_Mons")


def test_lists_ranges_steps_and_names_all_parse() -> None:
    expression = CronExpression.parse("0,30 9-17/4 * jan-mar mon,fri")

    assert expression.minutes == frozenset({0, 30})
    assert expression.hours == frozenset({9, 13, 17})
    assert expression.months == frozenset({1, 2, 3})
    assert expression.weekdays == frozenset({1, 5})


def test_sunday_is_seven_as_well_as_zero() -> None:
    # Half the crontabs in the world spell it the other way.
    assert CronExpression.parse("0 2 * * 7").weekdays == frozenset({0})


# -- firing --------------------------------------------------------------------


def test_the_next_firing_is_strictly_after_the_moment_given() -> None:
    # Otherwise a job that just fired is immediately due again for the same
    # minute, and the claim it already holds is the only thing stopping it.
    expression = CronExpression.parse("30 2 * * *")

    assert expression.next_after(at("2026-03-01T02:29:00")).at == at("2026-03-01T02:30:00")
    # The firing itself is not "after" itself: asking again from it gives
    # tomorrow, which is what stops a job re-claiming the minute it just ran.
    assert expression.next_after(at("2026-03-01T02:30:00")).at == at("2026-03-02T02:30:00")


def test_a_day_of_month_and_a_day_of_week_are_or_ed() -> None:
    # What every crontab does, and what nobody expects the first time.
    expression = CronExpression.parse("0 3 1 * mon")

    # 2026-06-01 is a Monday; both fields agree.
    assert expression.next_after(at("2026-05-31T00:00:00")).at == at("2026-06-01T03:00:00")
    # 2026-06-08 is the next Monday, and not the 1st.
    assert expression.next_after(at("2026-06-01T03:01:00")).at == at("2026-06-08T03:00:00")


def test_a_monthly_expression_skips_to_the_right_month() -> None:
    expression = CronExpression.parse("0 0 29 2 *")

    # 2028 is the next leap year after 2026.
    assert expression.next_after(at("2026-03-01T00:00:00")).at == at("2028-02-29T00:00:00")


def test_an_expression_naming_a_date_that_never_occurs_raises() -> None:
    # Rather than searching forever.
    expression = CronExpression.parse("0 0 31 2 *")

    with pytest.raises(CronError):
        expression.next_after(at("2026-03-01T00:00:00"))


# -- daylight saving -----------------------------------------------------------


def test_spring_forward_fires_once_at_the_instant_it_would_have() -> None:
    # On 2026-03-29 in London, 01:00 becomes 02:00: local 01:30 does not exist.
    # The job fires at 02:30 BST, which is the same *instant* 01:30 GMT would
    # have been — so it runs exactly when it always did, at a clock reading that
    # moved. A job that silently skipped one night a year is a gap nobody sees.
    expression = CronExpression.parse("30 1 * * *", timezone="Europe/London")

    firing = expression.next_after(at("2026-03-28T02:00:00", LONDON))

    assert firing.shifted
    assert firing.at.astimezone(UTC) == at("2026-03-29T01:30:00")
    assert firing.at.astimezone(LONDON).strftime("%H:%M") == "02:30"
    # And the day is not skipped.
    assert firing.at.astimezone(LONDON).date().isoformat() == "2026-03-29"


def test_fall_back_fires_once_on_the_first_occurrence() -> None:
    # On 2026-10-25 in London, 02:00 becomes 01:00: 01:30 happens twice. The
    # earlier UTC instant is the firing, and the second one is not a second job.
    expression = CronExpression.parse("30 1 * * *", timezone="Europe/London")

    firing = expression.next_after(at("2026-10-24T02:00:00", LONDON))

    assert not firing.shifted
    assert firing.at.astimezone(UTC) == at("2026-10-25T00:30:00")

    # Asking again from just after that firing gives the *next day*, never the
    # repeat of the same local time an hour later.
    following = expression.next_after(firing.at)
    assert following.at.astimezone(LONDON).date().isoformat() == "2026-10-26"


def test_a_schedule_keeps_its_local_hour_across_a_transition() -> None:
    # The point of configuring a timezone rather than an offset: 02:00 in New
    # York stays 02:00 whichever side of the transition it lands on.
    expression = CronExpression.parse("0 2 * * *", timezone="America/New_York")

    before = expression.next_after(at("2026-03-05T12:00:00", NEW_YORK))
    after = expression.next_after(at("2026-03-20T12:00:00", NEW_YORK))

    assert before.at.astimezone(NEW_YORK).hour == 2
    assert after.at.astimezone(NEW_YORK).hour == 2
    # And the UTC offset genuinely moved, which is what made it worth asserting.
    assert before.at.utcoffset() != after.at.utcoffset()


def test_a_firing_is_returned_in_its_own_zone_and_compares_as_an_instant() -> None:
    expression = CronExpression.parse("0 9 * * *", timezone="Europe/London")

    firing = expression.next_after(at("2026-07-01T00:00:00"))

    assert firing.at.tzinfo is not None
    assert firing.at.astimezone(UTC) == at("2026-07-01T08:00:00")
