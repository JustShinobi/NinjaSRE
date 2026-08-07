"""SSE serialisation, cursor-based catch-up, heartbeats, and backpressure.

The hard part — a bounded per-subscriber buffer, exactly-once catch-up, and
disconnecting a subscriber that falls behind without touching the run — is
``platform.runs.stream`` (feature 016). This package is the HTTP framing
around it: turning a ``RunEvent`` into a wire frame, and a dropped connection
into an ended generator.
"""

from __future__ import annotations
