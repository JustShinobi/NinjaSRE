"""The bounded buffer and stalled-consumer disconnect (FR-012, SC-007).

Implemented in ``platform.runs.stream`` (feature 016): ``Subscription`` holds
a queue of ``MAX_STREAM_BUFFER_EVENTS`` and marks itself overflowed rather
than blocking the publisher, and ``RunStream.follow`` raises
``SubscriberTooSlow`` once a subscriber is behind — which
``streaming/subscription.py`` catches to end the SSE response. Nothing here
duplicates that; this module is the one place a caller reads the bound from
to answer "how far behind can a client fall" without reaching into the
platform tier's internals directly.

Multi-subscriber support (T026) is likewise already the shape of
``RunEventBroker``: it keys subscriptions by run id and fans one event out to
every one of them, so two clients streaming the same run are two independent
``Subscription`` objects, and dropping one for falling behind never touches
the other.
"""

from __future__ import annotations

from config.constants.runs import MAX_STREAM_BUFFER_EVENTS

__all__ = ["MAX_STREAM_BUFFER_EVENTS"]
