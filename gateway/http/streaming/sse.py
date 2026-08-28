"""Serialising a ``RunEvent`` or a ``DeploymentEvent`` as one SSE frame.

The run vocabulary is feature 005's typed pipeline events, recorded by
feature 016 as ``RunEvent`` — the same shape every surface renders, so the
console and a raw ``curl`` see identical kinds and payloads. The deployment
vocabulary is the deployment-wide channel's own ten kinds; both share the
same frame shape (``id``/``event``/``data``) and differ only in what the
``id`` names — a run and a sequence for one, an epoch and a sequence for the
other.
"""

from __future__ import annotations

import json

from platform.runs.deployment import DeploymentEvent
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


def deployment_sse_frame(event: DeploymentEvent, *, epoch: str) -> bytes:
    """Return ``event`` as one ``id``/``event``/``data`` SSE frame.

    ``id`` is ``epoch:sequence`` — ``epoch`` names the broker's own lifetime in
    this process, not the event's run or incident, because the deployment
    channel has no single thing every frame is a position within.
    """
    payload = {
        "scope": event.scope.value,
        "kind": event.kind.value,
        "sequence": event.sequence,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": dict(event.payload),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return (f"id: {epoch}:{event.sequence}\nevent: {event.kind.value}\ndata: {body}\n\n").encode()


__all__ = ["HEARTBEAT_FRAME", "deployment_sse_frame", "sse_frame"]
