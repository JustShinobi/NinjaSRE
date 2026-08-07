"""Getting a rendered report to a destination, and knowing whether it arrived.

Three concerns, kept apart because they fail apart: dispatching with isolation
and idempotency, tracking which destinations have stopped working, and proving a
destination works before anybody depends on it at three in the morning.
"""

from __future__ import annotations

from platform.reporting.delivery.dispatcher import (
    DeliveryDispatcher,
    DeliveryError,
    DeliveryLedger,
    DeliveryRecord,
    DeliveryStatus,
    DeliveryTrace,
    DeliveryTransport,
    PermanentDeliveryFailure,
    TransientDeliveryFailure,
    UnknownTeam,
)
from platform.reporting.delivery.health import DestinationHealth, DestinationStatus
from platform.reporting.delivery.trace import RunTraceDeliveryLog
from platform.reporting.delivery.verification import (
    DestinationVerifier,
    Verification,
    VerificationProbe,
)

__all__ = [
    "DeliveryDispatcher",
    "DeliveryError",
    "DeliveryLedger",
    "DeliveryRecord",
    "DeliveryStatus",
    "DeliveryTrace",
    "DeliveryTransport",
    "DestinationHealth",
    "DestinationStatus",
    "DestinationVerifier",
    "PermanentDeliveryFailure",
    "RunTraceDeliveryLog",
    "TransientDeliveryFailure",
    "UnknownTeam",
    "Verification",
    "VerificationProbe",
]
