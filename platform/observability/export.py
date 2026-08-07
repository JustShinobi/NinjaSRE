"""OTLP over HTTP, encoded here, and isolated from everything that matters.

**Why there is no SDK.** The wire format is OTLP/JSON, which is a documented
encoding any collector accepts, and encoding it is a hundred lines of
dictionaries. An SDK would buy that in exchange for a dependency in the tree of
a product whose central promise is that nothing leaves the operator's host —
a tree the operator has to audit, and the first thing a security review reads.
The trade is not close. `tests/contract/observability/` asserts that this module
imports nothing but the standard library, so the promise is a property rather
than a claim.

**Failure isolation.** Nothing here raises at a caller. A refused connection, a
hung socket, a 500, a document that will not serialise — all of them increment
``dropped``, record the last failure, and return ``False``. An investigation
that produced an answer has succeeded, and nothing this module does afterwards
may change that.

**Bounded queue.** ``queue`` holds at most ``MAX_TELEMETRY_QUEUE_DEPTH``
records and discards the *oldest* when it is full. The alternative to dropping
telemetry during a collector outage is growing a buffer inside the process that
is investigating an incident, which turns a missing dashboard into a second one.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.observability import (
    MAX_TELEMETRY_QUEUE_DEPTH,
    OTLP_CONTENT_TYPE,
    TelemetrySignal,
)
from platform.observability.config import TelemetryConfig
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What one queued record is: the signal it belongs to and its OTLP document.
QueuedRecord = tuple[TelemetrySignal, dict[str, Any]]


@runtime_checkable
class Transport(Protocol):
    """How one encoded OTLP document reaches the collector."""

    def send(self, url: str, body: bytes, headers: dict[str, str], *, timeout: float) -> None:
        """Post ``body`` to ``url``, raising on anything that is not a success."""


@dataclass(frozen=True, slots=True)
class UrllibTransport:
    """The shipped transport: one POST, one timeout, no connection reuse.

    No pooling on purpose. Telemetry export is a background courtesy, and a
    pool held open against a collector is state that outlives the investigation
    it was recording — including when the collector is the thing that is down.
    """

    def send(self, url: str, body: bytes, headers: dict[str, str], *, timeout: float) -> None:
        """Post one OTLP document, raising on any transport or status failure."""
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            status = int(response.status)
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "collector refused the export", {}, None)  # type: ignore[arg-type]


@dataclass(slots=True)
class RecordingTransport:
    """A collector that records instead of receiving. For tests and dry runs."""

    sent: list[tuple[str, bytes, dict[str, str]]] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)

    def send(self, url: str, body: bytes, headers: dict[str, str], *, timeout: float) -> None:
        """Record one document, and the deadline it would have been sent under."""
        self.sent.append((url, body, dict(headers)))
        self.timeouts.append(timeout)


@dataclass(slots=True)
class OtlpExporter:
    """Posts OTLP documents at a collector, and never fails a caller.

    ``transport`` is a field rather than a constructor-only argument so a
    deployment can replace it — which is also what makes "a recovered collector
    is used again without a restart" testable without a sleep.
    """

    config: TelemetryConfig
    transport: Transport = field(default_factory=UrllibTransport)
    delivered: int = 0
    dropped: int = 0
    last_failure: str = ""
    _pending: deque[QueuedRecord] = field(
        default_factory=lambda: deque(maxlen=MAX_TELEMETRY_QUEUE_DEPTH), repr=False
    )

    @property
    def pending(self) -> list[QueuedRecord]:
        """Return the records waiting for export, oldest first."""
        return list(self._pending)

    def queue(self, signal: TelemetrySignal, document: dict[str, Any]) -> None:
        """Hold one document for the next flush, discarding the oldest when full.

        Counted as a drop at the moment it is discarded rather than at flush,
        because that is when the record stopped existing and an operator asking
        "am I losing telemetry" wants the answer before the flush that never
        comes.
        """
        if not self.config.enabled:
            return
        if len(self._pending) == MAX_TELEMETRY_QUEUE_DEPTH:
            self.dropped += 1
            self.last_failure = (
                f"the export queue reached its ceiling of {MAX_TELEMETRY_QUEUE_DEPTH} records"
            )
        self._pending.append((signal, document))

    def flush(self) -> int:
        """Export everything queued and return how much reached the collector.

        The queue is emptied whether or not the collector answered. Retaining
        what failed would make the queue unbounded by a second route, and the
        drop counter already records what was lost.
        """
        queued = list(self._pending)
        self._pending.clear()
        return sum(1 for signal, document in queued if self.export(signal, document))

    def export(self, signal: TelemetrySignal, document: dict[str, Any]) -> bool:
        """Post one document now, and return whether the collector took it.

        Never raises. The broad catch is the contract: a transport that grew a
        new exception type must not be able to fail the investigation that was
        being recorded.
        """
        if not self.config.enabled:
            return False

        try:
            body = json.dumps(document).encode("utf-8")
        except (TypeError, ValueError) as error:
            return self._failed(signal, error)

        headers = {"Content-Type": OTLP_CONTENT_TYPE}
        try:
            self.transport.send(
                self.config.url_for(signal),
                body,
                headers,
                timeout=self.config.timeout_seconds,
            )
        except Exception as error:  # noqa: BLE001 — telemetry must never fail a run
            return self._failed(signal, error)

        self.delivered += 1
        return True

    def to_record(self) -> dict[str, Any]:
        """Return what a diagnostic bundle and the health surface read."""
        return {
            "enabled": self.config.enabled,
            "endpoint": self.config.endpoint,
            "delivered": self.delivered,
            "dropped": self.dropped,
            "queued": len(self._pending),
            "last_failure": self.last_failure,
        }

    def _failed(self, signal: TelemetrySignal, error: Exception) -> bool:
        """Record one dropped export and say so, at warning rather than error.

        Warning, not error: a collector outage is not this deployment's failure
        and does not need a page. It needs to be visible to whoever is asking
        why the dashboard stopped moving.
        """
        self.dropped += 1
        self.last_failure = f"{type(error).__name__}: {error}"
        logger.warning(
            "telemetry.export_dropped",
            signal=signal.value,
            dropped=self.dropped,
            error=self.last_failure,
        )
        return False


__all__ = [
    "OtlpExporter",
    "QueuedRecord",
    "RecordingTransport",
    "Transport",
    "UrllibTransport",
]
