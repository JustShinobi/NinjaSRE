"""The web console: a browser client of the REST API, and nothing more.

Tier 1. Every page here is assembled from what the API answered — the console
holds no business logic, opens no database connection, and recomputes nothing
the API already computes. Where a screen needs something derived (an effective
configuration under a proposed change, whether a capability is available for a
team), it asks; the alternative is a second implementation that drifts from the
first, and the drift shows up as a screen that told somebody the wrong thing.

What lives here is presentation and the two properties presentation owns:
rendering only the actions a principal actually holds (``permissions``), and
recovering a live event stream without losing or repeating an event
(``stream``).
"""

from __future__ import annotations

__all__: list[str] = []
