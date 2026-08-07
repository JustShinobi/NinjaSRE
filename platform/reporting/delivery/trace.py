"""Writing each delivery outcome into the run's own log.

Separate from the dispatcher so the dispatcher holds a two-method port rather
than a recorder: that is what lets the delivery suite run with no store, and what
keeps `platform.runs` from having to know what a report is.

One event per destination, not one per run. "Reports delivered" cannot answer
the question somebody actually asks the morning after — *did the Jira ticket get
created* — and a run that delivered to twelve destinations and failed at the
thirteenth is the case where the difference matters.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform.reporting.delivery.dispatcher import DeliveryRecord
from platform.runs.events import TraceEventKind
from platform.runs.recorder import RunRecorder


@dataclass(slots=True)
class RunTraceDeliveryLog:
    """Records delivery outcomes as events on the run they belong to."""

    recorder: RunRecorder

    async def record_delivery(self, record: DeliveryRecord) -> None:
        """Append ``record``'s outcome to its run's log."""
        await self.recorder.record_event(
            record.run_id,
            TraceEventKind.REPORT_DELIVERED,
            payload=record.to_payload(),
        )


__all__ = ["RunTraceDeliveryLog"]
