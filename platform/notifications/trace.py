"""Writing every notification decision into the run's own log.

Including — especially — the decisions that sent nothing. A suppression, a
rate-limit refusal, and a severity that routed nowhere are the three ways an
operator ends up asking "why wasn't I told", and an event for each is what makes
that answerable from the trace rather than from somebody's memory of how the
policy was configured that week.

A record with no run behind it is dropped rather than invented into one. Some
notifications are not about an investigation — an escalation on an approval, a
digest — and inventing a run identifier for those would put events on a run that
did not produce them.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform.notifications.models import NotificationRecord
from platform.runs.events import TraceEventKind
from platform.runs.recorder import RunRecorder


@dataclass(slots=True)
class RunTraceNotificationLog:
    """Records notification decisions as events on the run they belong to."""

    recorder: RunRecorder

    async def record_notification(self, record: NotificationRecord) -> None:
        """Append ``record``'s decision to its run's log, when it has one."""
        if not record.run_id:
            return
        await self.recorder.record_event(
            record.run_id,
            TraceEventKind.NOTIFICATION_DECIDED,
            payload=record.to_payload(),
        )


__all__ = ["RunTraceNotificationLog"]
