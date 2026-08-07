"""Serialising a ``RunEvent`` as one SSE frame (FR-013).

The event vocabulary is feature 005's typed pipeline events, recorded by
feature 016 as ``RunEvent`` — the same shape every surface renders, so the
console and a raw ``curl`` see identical kinds and payloads.
"""

from __future__ import annotations

import json

from platform.runs.events import RunEvent

#: A comment frame. SSE comments start with ``:`` and are ignored by every
#: client, which is what makes them safe as a keep-alive: a proxy that closes
#: idle connections sees traffic, and an ``EventSource`` never fires ``onmessage``.
HEARTBEAT_FRAME = b": heartbeat\n\n"


def sse_frame(event: RunEvent) -> bytes:
    """Return ``event`` as one ``id``/``event``/``data`` SSE frame.

    ``id`` is the cursor a client presents on reconnect via ``Last-Event-ID``
    — the run and the sequence together, because a sequence alone is
    ambiguous across runs.
    """
    payload = {
        "run_id": event.run_id,
        "kind": event.kind.value,
        "sequence": event.sequence,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "turn_id": event.turn_id,
        "payload": dict(event.payload),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return (
        f"id: {event.run_id}:{event.sequence}\nevent: {event.kind.value}\ndata: {body}\n\n"
    ).encode()


__all__ = ["HEARTBEAT_FRAME", "sse_frame"]
