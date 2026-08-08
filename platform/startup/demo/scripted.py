"""An investigation that streams like a real one, with no model behind it.

FR-021. The live transcript is the single most convincing thing this product
does, and it is also the one thing a static demonstration cannot show: a
populated console proves the screens exist, and proves nothing about watching a
run think. So demo mode replays a recorded run at the pace a real one arrives
at, through the same event shape the console's live layer already consumes.

Paced rather than emitted at once, and that is not decoration. A transcript that
appears complete in one frame reads as a page; the same transcript arriving a
step at a time reads as a system working, which is the thing being demonstrated.
The interval is a constant so it can be turned down to nothing in a test — a
suite that spent two seconds per scripted run would be a suite somebody deletes.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.constants.first_run import (
    DEMO_SCRIPTED_EVENT_INTERVAL_SECONDS,
    DEMO_SCRIPTED_RUN_TRIGGER,
)
from platform.startup.demo.dataset import DemoDataset
from platform.startup.demo.labels import labelled


@dataclass(frozen=True, slots=True)
class ScriptedEvent:
    """One event of the replayed run, in the shape the live layer consumes."""

    run_id: str
    kind: str
    sequence: int
    occurred_at: datetime | None = None
    turn_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a stream writes."""
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "sequence": self.sequence,
            "occurred_at": None if self.occurred_at is None else self.occurred_at.isoformat(),
            "turn_id": self.turn_id,
            "payload": dict(self.payload),
        }


def scripted_events(dataset: DemoDataset) -> tuple[ScriptedEvent, ...]:
    """Return the recorded run's events, in sequence, labelled as a demonstration.

    Labelled in the payload rather than only by the tenant, because an event is
    the one thing here that leaves the database — it goes down a socket to a
    browser, and a client rendering it should be able to say so without having
    to know which organisation it is looking at.
    """
    rows = dataset.rows("run-stream", "events")
    events = [
        ScriptedEvent(
            run_id=str(row.get("run_id", "")),
            kind=str(row.get("kind", "")),
            sequence=int(row.get("sequence", index)),
            occurred_at=_instant(row.get("occurred_at")),
            turn_id=str(row["turn_id"]) if row.get("turn_id") else None,
            payload=labelled(row.get("payload") if isinstance(row.get("payload"), Mapping) else {}),
        )
        for index, row in enumerate(rows)
    ]
    return tuple(sorted(events, key=lambda event: event.sequence))


def _instant(value: Any) -> datetime | None:
    """Return an ISO timestamp as a datetime, or ``None``."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


async def stream_scripted_investigation(
    dataset: DemoDataset,
    *,
    interval_seconds: float = DEMO_SCRIPTED_EVENT_INTERVAL_SECONDS,
) -> AsyncIterator[ScriptedEvent]:
    """Yield the recorded run's events at the pace a live run produces them."""
    for event in scripted_events(dataset):
        if interval_seconds > 0:
            await asyncio.sleep(interval_seconds)
        yield event


def scripted_run_id(dataset: DemoDataset) -> str:
    """Return which run the scripted stream replays."""
    events = scripted_events(dataset)
    return events[0].run_id if events else ""


__all__ = [
    "DEMO_SCRIPTED_RUN_TRIGGER",
    "ScriptedEvent",
    "scripted_events",
    "scripted_run_id",
    "stream_scripted_investigation",
]
