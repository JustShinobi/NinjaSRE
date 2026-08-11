"""Sending what a destination subscribed to, and remembering whether it arrived.

Three properties, and each is a failure this shape prevents.

**Nothing leaves unmasked.** The body a destination receives has been through
the same masking policy any externalised text passes, and the level that did it
is on the destination row. A summary-with-link destination gets a bounded
summary and an authenticated URL rather than the report, which is the *default*
— widening it to the full report is a deliberate edit somebody made.

**Every attempt is a ledger row.** Delivered, or failed with the reason, in the
same table the arrivals are in. A report that did not arrive is worse than one
that never existed, because somebody is waiting for it, and the only thing worse
is one that did not arrive and left no trace.

**Retry is bounded and the schedule is named.** ``MAX_OUTBOUND_ATTEMPTS`` tries
on ``OUTBOUND_RETRY_BACKOFF_SECONDS``, and then the delivery is left failed for
a person to re-send. An unbounded retry against a destination that is down is
how a notification system becomes the outage.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from config.constants.transit import (
    DELIVERY_DETAIL_FULL_REPORT,
    MAX_DELIVERY_SUMMARY_CHARS,
    MAX_OUTBOUND_ATTEMPTS,
    OUTBOUND_RETRY_BACKOFF_SECONDS,
    TRANSIT_AUDIT_ACTION_RESEND,
    TRANSIT_AUDIT_RESOURCE_KIND,
)
from platform.config_service.bindings import masking_policy
from platform.config_service.schema import RootConfig
from platform.delivery.destinations import DeclaredDestination, destinations_for
from platform.masking.apply import mask
from platform.masking.mapping import MaskMapping
from platform.observability.logging import get_logger
from platform.persistence.ports.audit_repository import ActorKind, AuditEvent, AuditOutcome
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.persistence.ports.transit_ledger import (
    TransitDelivery,
    TransitDirection,
    TransitOutcome,
)

logger = get_logger(__name__)

#: How a message actually reaches a channel. Supplied by the composition root,
#: exactly as the gateway's model and deep verifiers are: reaching a chat
#: platform means a client and a credential proxy, and a dispatcher that built
#: one from ambient configuration would be posting into a workspace nobody
#: chose. ``None`` is a deployment that wired no transport, and then every
#: attempt fails with that as its reason — which is visible, and true.
Transport = Callable[["OutboundMessage"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """One thing to send, to one destination, about one event."""

    destination_id: str
    channel: str
    event: str
    subject: str
    body: str
    #: Where the reader goes for the rest of it, when the detail level says the
    #: rest of it does not travel. Authenticated at the far end — that is the
    #: whole security argument for the default level.
    link: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """What one dispatch did, per destination."""

    rows: tuple[TransitDelivery, ...] = ()

    @property
    def delivered(self) -> tuple[TransitDelivery, ...]:
        """Return the attempts the destination accepted."""
        return tuple(row for row in self.rows if row.outcome is TransitOutcome.DELIVERED)

    @property
    def failed(self) -> tuple[TransitDelivery, ...]:
        """Return the attempts that did not arrive."""
        return tuple(row for row in self.rows if row.outcome is TransitOutcome.FAILED)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class DeliveryDispatcher:
    """Tells every subscribed destination about one event, and ledgers each attempt."""

    gateway: PersistenceGateway
    scope: TenantScope
    settings: RootConfig
    #: What this deployment can actually deliver over. Passed in rather than
    #: derived, so a caller holding a live catalogue and a caller holding the
    #: configuration alone reach the same function.
    channels: tuple[str, ...] | None = None
    transport: Transport | None = None
    clock: Callable[[], datetime] = _utc_now
    #: How long to wait before each retry. Held rather than slept through: the
    #: dispatcher reports the schedule and a caller decides whether it is
    #: running inside a request or inside a worker.
    backoff_seconds: tuple[int, ...] = field(default=OUTBOUND_RETRY_BACKOFF_SECONDS)

    async def dispatch(
        self,
        event: str,
        *,
        subject: str,
        body: str,
        link: str = "",
    ) -> DeliveryResult:
        """Tell every destination subscribed to ``event``, and return what happened."""
        rows: list[TransitDelivery] = []
        for destination in destinations_for(self.settings, event, channels=self.channels):
            rows.append(
                await self._attempt(
                    self._message(destination, event, subject=subject, body=body, link=link),
                    attempt=1,
                )
            )
        return DeliveryResult(rows=tuple(rows))

    def _message(
        self,
        destination: DeclaredDestination,
        event: str,
        *,
        subject: str,
        body: str,
        link: str,
    ) -> OutboundMessage:
        """Return what actually leaves for ``destination``.

        Masked first, then cut to the detail level. In that order deliberately:
        cutting first and masking the remainder would mean the amount that
        leaves depends on where a masked identifier happened to fall.
        """
        policy = masking_policy(self.settings.policies)
        mapping = MaskMapping()
        safe_subject = mask(subject, policy=policy, mapping=mapping)
        safe_body = mask(body, policy=policy, mapping=mapping)
        if destination.detail != DELIVERY_DETAIL_FULL_REPORT:
            safe_body = _summarised(safe_body)
        return OutboundMessage(
            destination_id=destination.destination_id,
            channel=destination.channel,
            event=event,
            subject=safe_subject,
            body=safe_body,
            link=link,
            detail=destination.detail,
        )

    async def _attempt(self, message: OutboundMessage, *, attempt: int) -> TransitDelivery:
        """Send ``message`` once and write the attempt to the ledger."""
        at = self.clock()
        outcome = TransitOutcome.DELIVERED
        reason = ""
        if self.transport is None:
            outcome = TransitOutcome.FAILED
            reason = (
                "this deployment has no transport wired for outbound delivery; "
                "the message was composed and not sent"
            )
        else:
            try:
                await self.transport(message)
            except Exception as failure:  # noqa: BLE001 — every transport failure is a row
                outcome = TransitOutcome.FAILED
                reason = f"{type(failure).__name__}: {failure}"
                logger.warning(
                    "delivery.failed",
                    destination=message.destination_id,
                    event_type=message.event,
                    attempt=attempt,
                    reason=reason,
                )

        row = TransitDelivery(
            delivery_id=f"{message.destination_id}:{message.event}:{at.isoformat()}:{attempt}",
            direction=TransitDirection.OUTBOUND,
            source=message.destination_id,
            occurred_at=at,
            outcome=outcome,
            reason=reason,
            team_node_id=self.scope.team_node_id or "",
            event_type=message.event,
            attempt=attempt,
            detail={"channel": message.channel, "detail_level": message.detail},
        )
        async with self.gateway.begin(self.scope) as uow:
            await uow.transit.record(row)
        return row

    def next_backoff(self, attempt: int) -> int | None:
        """Return how long to wait before attempt ``attempt + 1``, or ``None``.

        ``None`` once ``MAX_OUTBOUND_ATTEMPTS`` is reached, which is the point
        the delivery is left failed for a person to re-send. A scheduler reads
        this rather than the constants directly, so "when does it try again" is
        answerable from one method.
        """
        if attempt >= MAX_OUTBOUND_ATTEMPTS or attempt > len(self.backoff_seconds):
            return None
        return self.backoff_seconds[attempt - 1]

    async def retry(self, failed: TransitDelivery, message: OutboundMessage) -> TransitDelivery:
        """Attempt ``message`` again, one attempt further on."""
        return await self._attempt(message, attempt=failed.attempt + 1)


def _summarised(body: str) -> str:
    """Return ``body`` cut to the summary length, at a word boundary where it can be.

    A cut mid-word reads as corruption rather than as a summary, and a reader
    who cannot tell the two apart cannot tell whether the link is worth
    following.
    """
    if len(body) <= MAX_DELIVERY_SUMMARY_CHARS:
        return body
    cut = body[:MAX_DELIVERY_SUMMARY_CHARS]
    space = cut.rfind(" ")
    return (cut[:space] if space > 0 else cut).rstrip() + "…"


async def resend(
    dispatcher: DeliveryDispatcher,
    failed: TransitDelivery,
    *,
    actor_id: str,
) -> TransitDelivery:
    """Send a failed delivery again because a person asked, and audit that they did.

    The audit row is written whatever the second attempt does. Who asked for a
    report to be sent again is a fact about a person's action, and recording it
    only when the retry succeeded would lose exactly the cases somebody later
    asks about.
    """
    message = OutboundMessage(
        destination_id=failed.source,
        channel=failed.detail.get("channel", ""),
        event=failed.event_type,
        subject=f"Re-sent: {failed.event_type}",
        body=failed.reason,
        detail=failed.detail.get("detail_level", ""),
    )
    row = await dispatcher.retry(failed, message)
    async with dispatcher.gateway.begin(dispatcher.scope) as uow:
        await uow.audit.append(
            AuditEvent(
                event_id=f"resend:{row.delivery_id}",
                occurred_at=row.occurred_at,
                actor_kind=ActorKind.USER,
                actor_id=actor_id,
                action=TRANSIT_AUDIT_ACTION_RESEND,
                resource_kind=TRANSIT_AUDIT_RESOURCE_KIND,
                resource_id=failed.delivery_id,
                outcome=(
                    AuditOutcome.ALLOWED
                    if row.outcome is TransitOutcome.DELIVERED
                    else AuditOutcome.FAILED
                ),
                detail={
                    "destination": failed.source,
                    "event": failed.event_type,
                    "attempt": str(row.attempt),
                },
            )
        )
    return row


__all__ = [
    "DeliveryDispatcher",
    "DeliveryResult",
    "OutboundMessage",
    "Transport",
    "resend",
]
