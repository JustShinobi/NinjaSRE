"""One source of "now" for both stores, and one definition of stale.

A timezone-naive instant compared against a timezone-aware one raises, and the
place that raises is three modules away from the place that produced it. Every
timestamp in this package therefore comes from here.

``clock`` is a parameter on everything that needs one, defaulting to this
function, so a staleness assertion fails because the rule changed rather than
because the suite ran a week after the fixture was written.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


def is_stale(moment: datetime | None, *, at: datetime, after_days: float) -> bool:
    """Return whether ``moment`` is older than ``after_days`` before ``at``.

    ``None`` is stale. Something nobody ever verified is not thereby fresh, and
    the alternative — treating an absent timestamp as "just now" — would report
    hand-entered topology as freshly confirmed by a discovery run that has never
    seen it.
    """
    if moment is None:
        return True
    return moment < at - timedelta(days=after_days)


__all__ = ["is_stale", "now"]
