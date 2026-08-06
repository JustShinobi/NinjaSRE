"""Cron expressions, IANA timezones, and the two nights a year they go wrong.

Written here rather than taken from a library, and the reason is the second half
of the title. Cron libraries handle daylight saving differently from one another
and usually silently: a job configured for 02:30 either does not run on the
March night when 02:30 does not exist, or runs twice on the October night when
it happens twice, and either way nobody finds out until a disaster-recovery
validation is missing from a report six months later. The behaviour NinjaSRE
needs is a decision, so it is written down and tested rather than inherited.

**Spring forward — the local time does not exist.** The job fires once, at the
instant it would have fired had the clocks not moved, and the firing is marked
shifted so the clock reading is explicable. For a 01:30 job on the London March
night that is 02:30 BST — the same moment 01:30 GMT would have been. Skipping is
the alternative and it is worse: a nightly job that silently does not run on one
night a year is the definition of a gap nobody notices.

**Fall back — the local time happens twice.** The job fires on the *first*
occurrence and not the second. That is a choice about which hour is "the" 01:30,
and the reason it is safe rather than merely arbitrary is that the claim key is
``(job_id, fire_time)`` and both occurrences resolve to the same local fire time
— so even a scheduler that evaluated both would only ever get one claim.

The expression syntax is the ordinary five-field one: minute, hour, day of
month, month, day of week. Ranges, steps, lists, and ``*``. No ``@reboot``, no
seconds field, no ``L``/``W``/``#``: each is a dialect somebody would have to
guess at, and a schedule an operator misread is worse than one they could not
write.

Day-of-month and day-of-week are **or**-ed when both are restricted, which is
what every crontab implementation does and what nobody expects the first time.
It is worth stating because the alternative reading — and-ing them — turns
``0 3 1 * 1`` from "the 1st, and every Monday" into "Mondays that fall on the
1st", which is roughly four times a decade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.constants.runs import DEFAULT_SCHEDULE_TIMEZONE, MAX_CRON_LOOKAHEAD_DAYS

#: Field bounds, in expression order. Day-of-week is 0–6 with 0 as Sunday, and
#: 7 is accepted as a second spelling of Sunday because half the crontabs in the
#: world are written that way.
_BOUNDS: tuple[tuple[int, int], ...] = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))

_FIELDS = ("minute", "hour", "day of month", "month", "day of week")

#: Named months and days, so an expression can be read out loud.
_NAMES: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
}  # fmt: skip


class CronError(ValueError):
    """A cron expression, or the timezone beside it, is not usable.

    Raised at parse time rather than at fire time. A schedule that only reveals
    it is malformed the first night it was meant to run is a schedule nobody
    finds out about until the morning after.
    """


@dataclass(frozen=True, slots=True)
class FireTime:
    """One firing, and whether daylight saving moved it.

    ``shifted`` is carried rather than inferred because it is what makes the
    spring-forward behaviour auditable: an operator looking at a run that
    started at 02:30 for a 01:30 schedule can see that the platform moved the
    clock reading rather than that something was an hour late.
    """

    at: datetime
    shifted: bool = False


@dataclass(frozen=True, slots=True)
class CronExpression:
    """A parsed five-field expression and the zone it is read in."""

    source: str
    timezone: str = DEFAULT_SCHEDULE_TIMEZONE
    minutes: frozenset[int] = frozenset()
    hours: frozenset[int] = frozenset()
    days: frozenset[int] = frozenset()
    months: frozenset[int] = frozenset()
    weekdays: frozenset[int] = frozenset()
    #: Whether each of the two day fields was restricted. Both unrestricted
    #: means every day; one restricted means that one; both restricted means
    #: their union, which is the rule crontab has and nobody expects.
    day_restricted: bool = False
    weekday_restricted: bool = False

    @classmethod
    def parse(cls, source: str, *, timezone: str = DEFAULT_SCHEDULE_TIMEZONE) -> CronExpression:
        """Return the expression ``source`` describes, or raise ``CronError``."""
        fields = source.split()
        if len(fields) != len(_BOUNDS):
            raise CronError(
                f"A cron expression has {len(_BOUNDS)} fields "
                f"({', '.join(_FIELDS)}); {source!r} has {len(fields)}."
            )
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as unknown:
            raise CronError(f"{timezone!r} is not an IANA timezone name.") from unknown

        parsed = [
            _parse_field(field, bounds=bounds, name=name, source=source)
            for field, bounds, name in zip(fields, _BOUNDS, _FIELDS)
        ]
        # 7 and 0 are both Sunday. Normalising here means every comparison
        # downstream is against one spelling.
        weekdays = frozenset(0 if day == 7 else day for day in parsed[4])

        return cls(
            source=source,
            timezone=timezone,
            minutes=parsed[0],
            hours=parsed[1],
            days=parsed[2],
            months=parsed[3],
            weekdays=weekdays,
            day_restricted=fields[2] != "*",
            weekday_restricted=fields[4] != "*",
        )

    @property
    def zone(self) -> ZoneInfo:
        """Return the timezone this expression is read in."""
        return ZoneInfo(self.timezone)

    def next_after(self, moment: datetime) -> FireTime:
        """Return the first firing strictly after ``moment``.

        ``moment`` may be in any zone; it is converted. The search walks minutes
        in local time and is bounded by ``MAX_CRON_LOOKAHEAD_DAYS``, because an
        expression naming February 30th has no next firing and an unbounded
        search for it is a hang rather than an error.
        """
        local = moment.astimezone(self.zone)
        # Truncate to the minute and step once: "strictly after" is what stops a
        # job that just fired from being claimed again for the same minute.
        candidate = local.replace(second=0, microsecond=0) + timedelta(minutes=1)
        deadline = local + timedelta(days=MAX_CRON_LOOKAHEAD_DAYS)

        while candidate <= deadline:
            if not self._matches_date(candidate):
                # Skip the whole day rather than its 1,440 minutes.
                candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if candidate.hour in self.hours and candidate.minute in self.minutes:
                return self._resolve(candidate)
            candidate += timedelta(minutes=1)

        raise CronError(
            f"{self.source!r} has no firing within {MAX_CRON_LOOKAHEAD_DAYS} days of "
            f"{moment.isoformat()}. It names a date that does not occur."
        )

    def _resolve(self, local: datetime) -> FireTime:
        """Return the instant ``local`` denotes, handling both DST transitions.

        Spring forward: the local reading does not exist, and converting it
        through UTC and back lands on the instant it would have been — 02:30 BST
        for a 01:30 GMT schedule — which is the firing, marked shifted.

        Fall back: the reading exists twice, and ``fold=0`` selects the earlier
        UTC instant. That is the one this platform defines as *the* firing, and
        the reason a scheduler evaluating both occurrences still only produces
        one run is that they resolve to the same ``(job_id, fire_time)`` claim.
        """
        first = local.replace(fold=0)
        # A nonexistent local time is one that does not survive a round trip
        # through UTC: the zone maps it forward, and mapping back gives an hour
        # that is not the one asked for.
        round_tripped = first.astimezone(ZoneInfo("UTC")).astimezone(self.zone)
        if (round_tripped.hour, round_tripped.minute) != (local.hour, local.minute):
            return FireTime(at=round_tripped, shifted=True)
        return FireTime(at=first)

    def _matches_date(self, moment: datetime) -> bool:
        """Return whether ``moment``'s date satisfies the three date fields."""
        if moment.month not in self.months:
            return False
        # ``weekday()`` is Monday-0; cron is Sunday-0.
        weekday = (moment.weekday() + 1) % 7
        day_ok = moment.day in self.days
        weekday_ok = weekday in self.weekdays

        if self.day_restricted and self.weekday_restricted:
            return day_ok or weekday_ok
        return day_ok and weekday_ok


def _parse_field(field: str, *, bounds: tuple[int, int], name: str, source: str) -> frozenset[int]:
    """Return the values one field admits, or raise ``CronError``."""
    low, high = bounds
    values: set[int] = set()

    for part in field.split(","):
        spec, _, step_text = part.partition("/")
        try:
            step = int(step_text) if step_text else 1
        except ValueError as broken:
            raise CronError(
                f"{step_text!r} is not a step in the {name} field of {source!r}."
            ) from broken
        if step < 1:
            raise CronError(f"A step of {step} in the {name} field of {source!r} names nothing.")

        if spec in {"*", ""}:
            start, end = low, high
        elif "-" in spec:
            first, _, last = spec.partition("-")
            start, end = _value(first, name, source), _value(last, name, source)
        else:
            start = end = _value(spec, name, source)

        if not (low <= start <= high and low <= end <= high):
            raise CronError(f"{spec!r} is outside {low}–{high} in the {name} field of {source!r}.")
        if start > end:
            raise CronError(
                f"{spec!r} runs backwards in the {name} field of {source!r}. "
                "Write it as two comma-separated ranges."
            )
        values.update(range(start, end + 1, step))

    if not values:  # pragma: no cover — every branch above adds at least one
        raise CronError(f"The {name} field of {source!r} names no value.")
    return frozenset(values)


def _value(text: str, name: str, source: str) -> int:
    """Return one field value, accepting a three-letter name for it."""
    stripped = text.strip()
    named = _NAMES.get(stripped.lower())
    if named is not None:
        return named
    try:
        return int(stripped)
    except ValueError as broken:
        raise CronError(f"{text!r} is not a value in the {name} field of {source!r}.") from broken


__all__ = ["CronError", "CronExpression", "FireTime"]
