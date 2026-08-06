"""The durable record of an investigation, and the live view of one in flight.

Two halves of one fact. ``recorder`` writes what happened while it is
happening; ``replay`` reads it back afterwards; ``stream`` delivers it to
whoever is watching now and to whoever reconnects having missed some of it.

The **event log is the source of truth and the pub/sub is a delivery
optimisation.** Everything reaches the log first, and a subscriber attaches to
the broker only after it has caught up from the log. That ordering is what makes
reconnection deliver every missed event exactly once instead of nearly always.
"""

from __future__ import annotations

from platform.runs.cursor import Cursor
from platform.runs.events import TraceEventKind
from platform.runs.history import CostSummary, RunHistory, RunQuery, attention_from
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder
from platform.runs.replay import ReplayedCall, ReplayedRun, ReplayedTurn, replay_trace
from platform.runs.retention import TraceRetention, TraceRetentionReport
from platform.runs.stream import RunEventBroker, RunStream, Subscription
from platform.runs.truncation import Truncation, truncate

__all__ = [
    "CostSummary",
    "Cursor",
    "RecordedCall",
    "RecordedTurn",
    "ReplayedCall",
    "ReplayedRun",
    "ReplayedTurn",
    "RunEventBroker",
    "RunHistory",
    "RunQuery",
    "RunRecorder",
    "RunStream",
    "Subscription",
    "TraceEventKind",
    "TraceRetention",
    "TraceRetentionReport",
    "Truncation",
    "attention_from",
    "truncate",
    "replay_trace",
]
