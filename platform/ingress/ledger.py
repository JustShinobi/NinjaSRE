"""Writing the transit row, and turning a raw body into something safe to keep.

The two things a caller on the ingress path needs, in one module, because they
are the two halves of one decision: a delivery is remembered, and what is
remembered of its payload has already been through the masking policy.

**The raw body never reaches storage.** ``masked_sample`` is the only
constructor of a ``PayloadSample`` the platform offers, it takes bytes and a
policy, and it returns a record whose body has been masked and capped. There is
no path from a request body to the ledger that does not pass through here.

**A delivery identifier is derived, not generated.** Two writes of the same
crossing — a handler that recorded its rejection and then recorded it again on a
retried request — land on one row. The instant is in the key because two
deliveries of the same bytes at different moments are two crossings, which is
the opposite of what the *idempotency* index decides and is why they are two
different keys built for two different questions.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime

from platform.masking.apply import mask
from platform.masking.mapping import MaskMapping
from platform.masking.policy import MaskingPolicy
from platform.persistence.ports.transaction import UnitOfWork
from platform.persistence.ports.transit_ledger import (
    PayloadSample,
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
    bounded_sample,
)

#: How much of the body digest goes into a delivery key. Sixteen hex characters
#: is 64 bits, which makes a collision between two bodies arriving at the same
#: instant from the same source something that does not happen in a deployment's
#: lifetime, and keeps the key short enough to read in a log line.
_DIGEST_CHARS = 16


def delivery_key(*, source: str, received_at: datetime, body: bytes) -> str:
    """Return the ledger identifier one crossing gets.

    Derived from the source, the instant, and a digest of the bytes, so a
    handler that wrote its row twice wrote one row — the same property the
    signal store's derived key has, and for the same reason.

    Deliberately *not* the source's own event id. That identifies the alert
    group the sender is talking about and is what the idempotency index answers
    "have I seen this before" with; this identifies one arrival. Two arrivals of
    one group are one event id and two ledger rows, which is the whole point of
    a ledger.
    """
    digest = hashlib.sha256(body).hexdigest()[:_DIGEST_CHARS]
    return f"{source}:{received_at.isoformat()}:{digest}"


def masked_sample(
    body: bytes,
    *,
    source: str,
    captured_at: datetime,
    policy: MaskingPolicy,
    delivery_id: str = "",
) -> PayloadSample:
    """Return what may be kept of ``body``: masked, capped, and naming its policy.

    A fresh mapping per sample rather than a shared one. Tokens are only useful
    within the run that issued them, and a sample is read by a person looking at
    a screen — carrying a mapping across sources would make two payloads share a
    token whose meaning nobody can look up.

    Bytes that are not valid UTF-8 are replaced rather than raising. A sender
    posting something undecodable is exactly the case the sample exists to make
    visible, and a capture that threw would leave the screen with nothing to
    show for it.
    """
    text = body.decode("utf-8", errors="replace")
    masked, truncated = bounded_sample(mask(text, policy=policy, mapping=MaskMapping()))
    return PayloadSample(
        source=source,
        captured_at=captured_at,
        body=masked,
        masking_policy=policy.level.value,
        delivery_id=delivery_id,
        truncated=truncated,
    )


async def record_delivery(
    uow: UnitOfWork,
    *,
    delivery_id: str,
    source: str,
    occurred_at: datetime,
    outcome: TransitOutcome,
    reason: str = "",
    matched_rule: str = "",
    team_node_id: str = "",
    resource_id: str = "",
    run_id: str = "",
    incident_id: str = "",
    detail: Mapping[str, str] | None = None,
) -> TransitDelivery:
    """Write one ingress crossing to the ledger and return the row.

    A function rather than a method on something, because every caller already
    holds a unit of work and the alternative is an object whose only state is
    the unit of work it was handed.
    """
    return await uow.transit.record(
        TransitDelivery(
            delivery_id=delivery_id,
            direction=TransitDirection.INGRESS,
            source=source,
            occurred_at=occurred_at,
            outcome=outcome,
            reason=reason,
            matched_rule=matched_rule,
            team_node_id=team_node_id,
            resource_id=resource_id,
            run_id=run_id,
            incident_id=incident_id,
            detail=dict(detail or {}),
        )
    )


__all__ = ["delivery_key", "masked_sample", "record_delivery"]
