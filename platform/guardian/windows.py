"""Finding the hours the cluster is already busy, and offering them as freeze windows.

FR-020's phrasing is the whole design: freeze windows are *offered* rather than
required, "rather than requiring the operator to know they need one". Nobody
sets up a homelab and then thinks about change freezes. What they do is discover,
once, that something was migrated during the nightly backup and left a guest
locked — and the fix for that is knowing the backup schedule, which the cluster
already declares.

So the schedules are read, turned into windows with a margin either side, and
presented as a proposal. Applying is a policy write like any other.

**A window is offered, never imposed.** A deployment that silently froze itself
for a quarter of every day would be one whose autonomy was switched off by
accident, and the operator would conclude the feature does not work rather than
that it is doing what it was told.

**A window longer than a few hours is reported and not offered.** Six hours is
where a freeze stops being a window and becomes a posture, and a posture is a
decision somebody makes on purpose.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import time, timedelta
from typing import Any

from config.constants.guardian import (
    FREEZE_WINDOW_LEAD_MINUTES,
    FREEZE_WINDOW_TRAIL_MINUTES,
    MAX_DETECTED_FREEZE_HOURS,
)

#: How long a backup job is assumed to run when the cluster does not say. An
#: hour: most homelab jobs finish inside one, and the margin either side is what
#: absorbs the ones that do not. Guessing longer would freeze more of the night
#: than the backups actually use.
DEFAULT_BACKUP_MINUTES: int = 60


@dataclass(frozen=True, slots=True)
class ScheduledActivity:
    """One recurring thing the cluster already does, at a time it already declares."""

    name: str
    #: When it starts, in the cluster's own local time.
    starts_at: time
    minutes: int = DEFAULT_BACKUP_MINUTES
    #: What kind of activity this is, in the operator's words, so the offer can
    #: say "your pve02 backup" rather than "job backup-33b5e58a".
    describes: str = "backup"
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class OfferedWindow:
    """A freeze window this deployment noticed the operator probably wants.

    Carries the reasoning as well as the times, because an operator who is
    shown a freeze they did not ask for and cannot explain will refuse it —
    correctly.
    """

    name: str
    start: str
    end: str
    reason: str
    timezone: str = "UTC"
    #: The activity this was derived from, so declining one and keeping another
    #: is a decision about a real thing rather than about a time range.
    derived_from: str = ""

    def to_settings(self) -> dict[str, Any]:
        """Return this window as the freeze-window configuration document."""
        return {
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "timezone": self.timezone,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class WindowOffer:
    """Every window worth offering, and the activity that was too long to offer one for."""

    windows: tuple[OfferedWindow, ...] = ()
    #: Activities whose window would run longer than a freeze reasonably should.
    #: Reported rather than dropped: an operator whose backup genuinely takes
    #: eight hours has a real problem with autonomy overlapping it, and telling
    #: them is more use than a window they would have to fight.
    too_long: tuple[tuple[str, float], ...] = ()

    @property
    def has_offer(self) -> bool:
        """Return whether there is anything here to put in front of somebody."""
        return bool(self.windows)

    def summarise(self) -> str:
        """Return the sentence that goes above the offer."""
        if not self.windows and not self.too_long:
            return (
                "Nothing on this cluster runs on a schedule the deployment can see, so "
                "there is no window to offer. Backup jobs are where these come from."
            )
        parts: list[str] = []
        if self.windows:
            named = ", ".join(f"{window.start}–{window.end}" for window in self.windows)
            parts.append(
                f"{len(self.windows)} window(s) match what this cluster already does "
                f"every day: {named}. Inside them, actions that would change a guest wait "
                f"rather than colliding with a backup that is already running."
            )
        for name, hours in self.too_long:
            parts.append(
                f"{name} would need a {hours:.1f}-hour freeze, which is long enough that "
                f"offering it as a window would be switching autonomy off by another name. "
                f"It is worth knowing about rather than accepting."
            )
        return " ".join(parts)

    def to_record(self) -> dict[str, Any]:
        """Return the document the console renders and the API returns."""
        return {
            "summary": self.summarise(),
            "windows": [window.to_settings() for window in self.windows],
            "too_long": [{"activity": name, "hours": hours} for name, hours in self.too_long],
        }


def offer_windows(
    activities: Iterable[ScheduledActivity],
    *,
    timezone: str = "UTC",
    lead_minutes: int = FREEZE_WINDOW_LEAD_MINUTES,
    trail_minutes: int = FREEZE_WINDOW_TRAIL_MINUTES,
) -> WindowOffer:
    """Return the freeze windows ``activities`` suggest, with the reasoning for each.

    A disabled activity produces no window. A job that is switched off is not
    something the cluster does, and freezing around it would be freezing around
    a thing that never happens — which is how a deployment ends up with a
    permanent freeze nobody can account for.
    """
    offered: list[OfferedWindow] = []
    too_long: list[tuple[str, float]] = []

    for activity in _ordered(activities):
        if not activity.enabled:
            continue
        span_minutes = lead_minutes + activity.minutes + trail_minutes
        hours = span_minutes / 60.0
        if hours > MAX_DETECTED_FREEZE_HOURS:
            too_long.append((activity.name, hours))
            continue
        start = _shift(activity.starts_at, -lead_minutes)
        end = _shift(activity.starts_at, activity.minutes + trail_minutes)
        offered.append(
            OfferedWindow(
                name=f"around-{activity.name}",
                start=start,
                end=end,
                timezone=timezone,
                derived_from=activity.name,
                reason=(
                    f"your {activity.describes} {activity.name} starts at "
                    f"{activity.starts_at.strftime('%H:%M')} and takes about "
                    f"{activity.minutes} minutes. An action taken while it is running is "
                    f"the one that leaves a guest locked, so the window opens "
                    f"{lead_minutes} minutes early — a job that starts on time still has a "
                    f"queue in front of it — and closes {trail_minutes} minutes after it "
                    f"should have finished."
                ),
            )
        )

    return WindowOffer(windows=tuple(offered), too_long=tuple(too_long))


def _ordered(activities: Iterable[ScheduledActivity]) -> Sequence[ScheduledActivity]:
    """Return the activities in the order of the day, so the offer reads like one."""
    return sorted(activities, key=lambda activity: (activity.starts_at, activity.name))


def _shift(moment: time, minutes: int) -> str:
    """Return ``moment`` moved by ``minutes``, as ``HH:MM``, wrapping past midnight.

    Wrapping rather than clamping, because the windows this produces are around
    backups and backups run at two in the morning. A window from 01:30 to 03:30
    that clamped at midnight would silently become a window over the wrong half
    of the night.
    """
    total = timedelta(hours=moment.hour, minutes=moment.minute) + timedelta(minutes=minutes)
    wrapped = int(total.total_seconds()) % 86_400
    return f"{wrapped // 3600:02d}:{wrapped % 3600 // 60:02d}"


__all__ = [
    "DEFAULT_BACKUP_MINUTES",
    "OfferedWindow",
    "ScheduledActivity",
    "WindowOffer",
    "offer_windows",
]
