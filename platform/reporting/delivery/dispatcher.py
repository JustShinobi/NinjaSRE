"""Delivering one report to every configured destination, each isolated from the rest.

Four properties, and each one is a failure mode somebody has already had.

**Per-destination isolation.** A destination's failure — declared or entirely
unexpected — is caught, recorded, and left behind. Nothing here re-raises into
the caller, because an investigation that concluded successfully and then failed
because a wiki was down would be an investigation made *less* reliable by having
somewhere to publish it.

**Idempotency by key, not by hope.** The key is the run and the destination, it
is passed to the transport on every attempt, and a delivery already in the ledger
is not attempted again. A retry after a timeout is the case this exists for: the
vendor may well have taken the first copy, and "we think it failed" is not a
reason to send a second one.

**Retry is for transient failures only.** A permanent refusal — a deleted
channel, an archived project, a team that no longer exists — is recorded once. A
retry ceiling would eventually stop it, and "eventually" is four attempts of
telling a vendor about a team that will never exist again.

**Rendering goes through the registry.** The dispatcher never calls a formatter
directly, so every delivery is fitted to its destination's limit and a body over
the limit is a summary with a link rather than something a vendor silently cuts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.notifications import (
    DELIVERY_RECORD_ATTEMPTS,
    DELIVERY_RECORD_DESTINATION,
    DELIVERY_RECORD_REASON,
    DELIVERY_RECORD_REFERENCE,
    DELIVERY_RECORD_STATUS,
    DELIVERY_RECORD_SUMMARISED,
    REPORT_DELIVERY_BACKOFF_FACTOR,
    REPORT_DELIVERY_BACKOFF_SECONDS,
    REPORT_DELIVERY_MAX_BACKOFF_SECONDS,
    REPORT_MAX_DELIVERY_ATTEMPTS,
)
from platform.observability.logging import get_logger
from platform.reporting.delivery.health import DestinationHealth
from platform.reporting.models import Destination, FormattedReport, Report
from platform.reporting.registry import render

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


class DeliveryError(Exception):
    """Base for everything a report transport raises."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class TransientDeliveryFailure(DeliveryError):
    """The destination could not take this now, and might in a moment."""


class PermanentDeliveryFailure(DeliveryError):
    """The destination will not take this, however many times it is asked."""


class UnknownTeam(PermanentDeliveryFailure):
    """The team this delivery belongs to no longer exists.

    Permanent by construction rather than by classification. A deleted team's
    destinations are not coming back, and retrying is how one deletion becomes a
    recurring background failure nobody can find the source of.
    """

    def __init__(self, team_node_id: str) -> None:
        self.team_node_id = team_node_id
        super().__init__(f"the team {team_node_id} no longer exists")


class DeliveryStatus(StrEnum):
    """What happened to one destination's copy of a report."""

    DELIVERED = "delivered"
    #: Already delivered under this key. Not a failure and not a second
    #: delivery — the distinction is what a retry needs to be able to report.
    DUPLICATE = "duplicate"
    FAILED = "failed"
    #: Never attempted: unverified, unhealthy, or nothing configured to carry it.
    SKIPPED = "skipped"
    #: Attempted once and permanently refused.
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    """The outcome for one destination, as the trace keeps it."""

    destination: str
    run_id: str
    delivery_key: str
    status: DeliveryStatus
    attempts: int = 0
    reason: str = ""
    reference: str = ""
    summarised: bool = False
    at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether the report is at this destination."""
        return self.status in (DeliveryStatus.DELIVERED, DeliveryStatus.DUPLICATE)

    def to_payload(self) -> dict[str, Any]:
        """Return the payload a run-trace event carries."""
        return {
            DELIVERY_RECORD_DESTINATION: self.destination,
            DELIVERY_RECORD_STATUS: self.status.value,
            DELIVERY_RECORD_ATTEMPTS: self.attempts,
            DELIVERY_RECORD_REASON: self.reason,
            DELIVERY_RECORD_REFERENCE: self.reference,
            DELIVERY_RECORD_SUMMARISED: self.summarised,
        }


@runtime_checkable
class DeliveryTransport(Protocol):
    """Carries one rendered report to one destination.

    A protocol for the reason every other outbound seam here is one: the
    credential belongs at the network edge, not in the caller, and a seam means
    the whole delivery suite runs with no socket and no token.
    """

    async def deliver(
        self, formatted: FormattedReport, destination: Destination, *, delivery_key: str
    ) -> str:
        """Deliver ``formatted`` and return a reference to where it landed.

        ``delivery_key`` is the same on every attempt of the same delivery, so a
        destination that supports idempotency can use it. Raises
        ``TransientDeliveryFailure`` to be retried and ``PermanentDeliveryFailure``
        not to be.
        """


@runtime_checkable
class DeliveryTrace(Protocol):
    """Where a delivery outcome is written down."""

    async def record_delivery(self, record: DeliveryRecord) -> None:
        """Record that ``record`` happened."""


@dataclass(slots=True)
class DeliveryLedger:
    """Which deliveries have already happened, by key.

    Holds successes only. A failed delivery must be attemptable again — that is
    what a retry is — and a ledger of failures would be a second health store
    that could disagree with the first.
    """

    delivered: dict[str, DeliveryRecord] = field(default_factory=dict)

    def find(self, key: str) -> DeliveryRecord | None:
        """Return the delivery already recorded under ``key``, if there is one."""
        return self.delivered.get(key)

    def record(self, record: DeliveryRecord) -> None:
        """Keep ``record`` so a later attempt under the same key is a duplicate."""
        if record.status is DeliveryStatus.DELIVERED:
            self.delivered[record.delivery_key] = record


@dataclass(slots=True)
class DeliveryDispatcher:
    """Delivers a report to every destination, one failure at a time."""

    transports: Mapping[str, DeliveryTransport]
    health: DestinationHealth = field(default_factory=DestinationHealth)
    ledger: DeliveryLedger = field(default_factory=DeliveryLedger)
    trace: DeliveryTrace | None = None
    max_attempts: int = REPORT_MAX_DELIVERY_ATTEMPTS
    clock: Callable[[], datetime] = _utc_now
    #: Injected for the same reason every other backoff here injects one: a wait
    #: that cannot be substituted is a wait the suite has to sit through.
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def deliver(
        self, report: Report, destinations: Sequence[Destination], *, link: str = ""
    ) -> tuple[DeliveryRecord, ...]:
        """Deliver ``report`` to every destination and return one record each.

        Sequential rather than concurrent. Delivery is not on the critical path
        of an investigation — it happens after one concluded — and a serial pass
        means a vendor's rate limiter meets one caller rather than thirteen.
        """
        records: list[DeliveryRecord] = []
        for destination in destinations:
            record = await self._deliver_one(report, destination, link=link)
            self.ledger.record(record)
            await self._record(record)
            records.append(record)
        return tuple(records)

    async def _deliver_one(
        self, report: Report, destination: Destination, *, link: str
    ) -> DeliveryRecord:
        """Return the outcome of delivering ``report`` to one destination."""
        key = destination.delivery_key(report.run_id)

        already = self.ledger.find(key)
        if already is not None:
            return self._record_for(
                destination,
                report,
                key,
                status=DeliveryStatus.DUPLICATE,
                attempts=0,
                reason="already delivered under this key",
                reference=already.reference,
                summarised=already.summarised,
            )

        refusal = self._refusal(destination)
        if refusal is not None:
            return self._record_for(
                destination, report, key, status=DeliveryStatus.SKIPPED, reason=refusal
            )

        transport = self.transports[destination.kind]
        formatted = render(report, destination, link=link)
        return await self._attempt(report, destination, formatted, key, transport)

    def _refusal(self, destination: Destination) -> str | None:
        """Return why this destination is not being delivered to, or ``None``."""
        if not destination.verified:
            return (
                f"{destination.name} has never been verified; verify it before "
                f"an incident depends on it"
            )
        if destination.kind not in self.transports:
            return f"no transport is configured for {destination.kind}"
        if not self.health.is_available(destination.name):
            status = self.health.status(destination.name)
            return (
                f"{destination.name} is unhealthy after {status.consecutive_failures} "
                f"consecutive failures ({status.last_failure_reason})"
            )
        return None

    async def _attempt(
        self,
        report: Report,
        destination: Destination,
        formatted: FormattedReport,
        key: str,
        transport: DeliveryTransport,
    ) -> DeliveryRecord:
        """Return the outcome of attempting one delivery, retrying transient failures."""
        wait = REPORT_DELIVERY_BACKOFF_SECONDS
        reason = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                reference = await transport.deliver(formatted, destination, delivery_key=key)
            except PermanentDeliveryFailure as refused:
                self.health.record_failure(destination.name, reason=refused.reason)
                return self._record_for(
                    destination,
                    report,
                    key,
                    status=DeliveryStatus.REFUSED,
                    attempts=attempt,
                    reason=refused.reason,
                    summarised=formatted.summarised,
                )
            except TransientDeliveryFailure as failure:
                reason = failure.reason
            except Exception as unexpected:  # noqa: BLE001 - isolation is the point
                # A transport that raised something nobody declared is still one
                # destination's problem. Letting it out would take the other
                # twelve deliveries with it.
                reason = f"{type(unexpected).__name__}: {unexpected}"
                logger.error(
                    "reporting.transport_raised_unexpectedly",
                    destination=destination.name,
                    error=reason,
                )
                self.health.record_failure(destination.name, reason=reason)
                return self._record_for(
                    destination,
                    report,
                    key,
                    status=DeliveryStatus.FAILED,
                    attempts=attempt,
                    reason=reason,
                    summarised=formatted.summarised,
                )
            else:
                self.health.record_success(destination.name)
                return self._record_for(
                    destination,
                    report,
                    key,
                    status=DeliveryStatus.DELIVERED,
                    attempts=attempt,
                    reference=reference,
                    summarised=formatted.summarised,
                )

            if attempt < self.max_attempts:
                logger.info(
                    "reporting.delivery_retrying",
                    destination=destination.name,
                    attempt=attempt,
                    reason=reason,
                )
                await self.sleep(wait)
                wait = min(
                    wait * REPORT_DELIVERY_BACKOFF_FACTOR, REPORT_DELIVERY_MAX_BACKOFF_SECONDS
                )

        self.health.record_failure(destination.name, reason=reason)
        return self._record_for(
            destination,
            report,
            key,
            status=DeliveryStatus.FAILED,
            attempts=self.max_attempts,
            reason=reason,
            summarised=formatted.summarised,
        )

    def _record_for(
        self,
        destination: Destination,
        report: Report,
        key: str,
        *,
        status: DeliveryStatus,
        attempts: int = 0,
        reason: str = "",
        reference: str = "",
        summarised: bool = False,
    ) -> DeliveryRecord:
        """Return the record for one destination's outcome."""
        return DeliveryRecord(
            destination=destination.name,
            run_id=report.run_id,
            delivery_key=key,
            status=status,
            attempts=attempts,
            reason=reason,
            reference=reference,
            summarised=summarised,
            at=self.clock(),
        )

    async def _record(self, record: DeliveryRecord) -> None:
        """Write ``record`` to the trace, without letting the write lose the delivery.

        The report has already arrived by the time this runs. A trace store that
        is down is worth an error line; it is not worth reporting a successful
        delivery as a failure, which is what re-raising here would do.
        """
        if self.trace is None:
            return
        try:
            await self.trace.record_delivery(record)
        except Exception as failure:  # noqa: BLE001 - the delivery already happened
            logger.error(
                "reporting.delivery_not_traced",
                destination=record.destination,
                status=record.status.value,
                error=str(failure),
            )


__all__ = [
    "DeliveryDispatcher",
    "DeliveryError",
    "DeliveryLedger",
    "DeliveryRecord",
    "DeliveryStatus",
    "DeliveryTrace",
    "DeliveryTransport",
    "PermanentDeliveryFailure",
    "TransientDeliveryFailure",
    "UnknownTeam",
]
