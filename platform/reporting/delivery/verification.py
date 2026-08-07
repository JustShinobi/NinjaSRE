"""Proving a destination works before an incident depends on it.

An unverified destination fails at 03:00, which is the worst possible moment to
discover a wrong API token, a channel the bot was never invited to, or a project
that was archived last quarter. So verification is a separate operation an
operator runs when they configure a destination, and the dispatcher refuses a
destination nobody has ever verified.

**A missing probe is a failure, not a pass.** A destination whose kind has no
verifier is reported as unverifiable, naming the kind. The alternative —
treating "we cannot check" as "it is fine" — makes the verification step report
success for exactly the destinations nobody has finished implementing.

**The reason is the vendor's own.** "Verification failed" sends an operator to
read logs; "the API token is not valid for this workspace" sends them to the
right settings page.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from platform.observability.logging import get_logger
from platform.reporting.delivery.dispatcher import DeliveryError
from platform.reporting.models import Destination

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Verification:
    """Whether one destination answered, and what it said if it did not."""

    destination: str
    ok: bool
    reason: str = ""
    checked_at: datetime | None = None

    def describe(self) -> str:
        """Return the sentence an operator reads."""
        if self.ok:
            return f"{self.destination} is reachable and accepted a test call."
        return f"{self.destination} cannot be delivered to: {self.reason}"

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this check."""
        return {
            "destination": self.destination,
            "ok": self.ok,
            "reason": self.reason,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }


@runtime_checkable
class VerificationProbe(Protocol):
    """Asks one destination kind whether it would accept a report."""

    async def check(self, destination: Destination) -> None:
        """Return if ``destination`` is usable, or raise ``DeliveryError`` saying why not."""


@dataclass(slots=True)
class DestinationVerifier:
    """Checks configured destinations, one probe per destination kind."""

    probes: Mapping[str, VerificationProbe] = field(default_factory=dict)
    clock: Callable[[], datetime] = _utc_now

    async def verify(self, destination: Destination) -> Verification:
        """Return whether ``destination`` is usable, and why not if it is not."""
        probe = self.probes.get(destination.kind)
        if probe is None:
            return Verification(
                destination=destination.name,
                ok=False,
                reason=f"no verifier is configured for {destination.kind}",
                checked_at=self.clock(),
            )
        try:
            await probe.check(destination)
        except DeliveryError as refused:
            logger.warning(
                "reporting.destination_verification_failed",
                destination=destination.name,
                reason=refused.reason,
            )
            return Verification(
                destination=destination.name,
                ok=False,
                reason=refused.reason,
                checked_at=self.clock(),
            )
        except Exception as unexpected:  # noqa: BLE001 - one destination's problem
            reason = f"{type(unexpected).__name__}: {unexpected}"
            logger.error(
                "reporting.destination_verification_raised",
                destination=destination.name,
                error=reason,
            )
            return Verification(
                destination=destination.name, ok=False, reason=reason, checked_at=self.clock()
            )
        return Verification(destination=destination.name, ok=True, checked_at=self.clock())

    async def verify_all(self, destinations: Sequence[Destination]) -> tuple[Verification, ...]:
        """Return one verification per destination, in the order given."""
        return tuple([await self.verify(destination) for destination in destinations])


__all__ = ["DestinationVerifier", "Verification", "VerificationProbe"]
