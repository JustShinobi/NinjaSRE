"""Watching the estate, and deciding that something is wrong.

The component that makes the deployment speak first. Everything else in the
platform begins when somebody — a person, an upstream alerting system, a
scheduled objective — says there is a problem. This package is the part that
says it itself.

Four things live here and the boundaries between them are load-bearing.

``signals``
    A window over what has been observed. The unit every detector reads, and a
    value rather than a query result, so evaluation can be replayed against
    stored history.

``sources``
    Where signals come from: a poller calling an integration on its declared
    interval, the estate's own health transitions, and a query against somebody
    else's metrics system. None of them can hold a credential.

``detectors``
    The declarations and the four condition kinds. Pure functions from a window
    to a verdict — no clock, no transaction, no state carried between calls.

``evaluation``
    The tick. Claims its work with the scheduler's existing lease, evaluates
    every enabled detector over the estate, and hands the findings to the
    incident lifecycle.

The property the whole package is arranged around is that **evaluation carries
no state**. A condition has held for ten minutes when every sample in the last
ten minutes satisfies it, not when a counter says so. That is why a restart
mid-tick cannot double-fire, why two replicas cannot disagree, and why a
detector can be tested by replaying yesterday's signals through it.
"""

from __future__ import annotations
