"""What comes back after the host restarts, and the check that nothing did not.

A homelab host reboots. It reboots for a kernel update, for a power cut, and
because somebody moved the desk. That is not an exceptional condition here, it
is Tuesday — so "the deployment resumes" has to be a property somebody checked
rather than a hope.

Almost all of it is already true by construction, and the reason is worth
stating: nothing this deployment is doing lives in a process. Detection is a
scheduled job in the database, verification obligations are rows with a due time
and a lease, incidents are rows, and the estate is a table. A restarted process
reads them and carries on, and a process that died mid-action leaves an
obligation whose lease expires and is claimed by the next one.

What this module adds is the *report*. Three things have to come back — the
observer, the scheduler, and every verification obligation that was owed — and a
deployment that came back with two of them looks entirely healthy: the console
renders, the API answers, and one of the three jobs is simply not running. There
is no error anywhere, and the symptom is that nothing has been detected since
Tuesday.

**An obligation whose lease expired while the host was off is owed, not lost.**
That is the single most important line here. A restart that dropped them would
leave actions taken and never verified, which is the exact state Article III
exists to prevent — and it would look identical to a deployment with nothing
outstanding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ResumedWork:
    """What was found waiting after a restart, and what is running again.

    Counts rather than the work itself, because this is a report an operator
    reads once after a reboot. The work is reachable everywhere else.
    """

    observer_running: bool
    scheduler_running: bool
    #: Verification obligations that were owed before the restart and still are.
    obligations_owed: int = 0
    #: Obligations whose lease was held by the process that died. Claimable
    #: again, and counted separately because they are the ones a naive restart
    #: would leave stuck rather than lose.
    obligations_reclaimed: int = 0
    #: Incidents that were open before the restart and still are. Zero is a
    #: perfectly good answer and a *drop* is not, which is why the before-count
    #: is carried too.
    incidents_open: int = 0
    incidents_open_before: int = 0
    resumed_at: datetime | None = None

    @property
    def everything_resumed(self) -> bool:
        """Return whether all three things that must come back have."""
        return self.observer_running and self.scheduler_running and not self.lost_incidents

    @property
    def lost_incidents(self) -> int:
        """Return how many open incidents did not survive the restart."""
        return max(self.incidents_open_before - self.incidents_open, 0)

    def describe(self) -> str:
        """Return what an operator is shown after the host comes back."""
        if self.everything_resumed:
            return (
                f"Resumed after a restart: the observer and the scheduler are running, "
                f"{self.incidents_open} incident(s) are still open, and "
                f"{self.obligations_owed} verification obligation(s) are still owed — "
                f"{self.obligations_reclaimed} of them reclaimed from the process that "
                f"stopped. Nothing was lost."
            )

        missing: list[str] = []
        if not self.observer_running:
            missing.append(
                "the observer is not running, so nothing is being detected — this is "
                "the failure that looks exactly like a healthy deployment"
            )
        if not self.scheduler_running:
            missing.append(
                "the scheduler is not running, so no scheduled work will start and no "
                "verification obligation will come due"
            )
        if self.lost_incidents:
            missing.append(f"{self.lost_incidents} open incident(s) did not survive the restart")
        return f"Restarted, but incompletely: {'; '.join(missing)}."

    def to_record(self) -> dict[str, Any]:
        """Return the document a health endpoint serves after a restart."""
        return {
            "observer_running": self.observer_running,
            "scheduler_running": self.scheduler_running,
            "obligations_owed": self.obligations_owed,
            "obligations_reclaimed": self.obligations_reclaimed,
            "incidents_open": self.incidents_open,
            "incidents_open_before": self.incidents_open_before,
            "lost_incidents": self.lost_incidents,
            "everything_resumed": self.everything_resumed,
            "resumed_at": self.resumed_at.isoformat() if self.resumed_at else "",
            "summary": self.describe(),
        }


__all__ = ["ResumedWork"]
