"""Marking one integration broken without breaking the deployment (FR-016).

A vendor ships a change that alters a response shape. The recorded fixtures the
contract suite runs against still pass, because they are recordings; the
scheduled live run does not. The question is what happens next, and there are
only two answers.

Failing the build is the wrong one. It is not the operator's change, they cannot
fix it, and a red build tells them nothing about which of their eighty-five
integrations is affected — so the pressure is to disable the live run, and then
the drift is undetected instead of merely unfixed.

Marking the integration degraded is the right one. Everything else keeps
working, the console says precisely which vendor broke and how, and the
investigation that would have called it knows in advance rather than discovering
it mid-incident.

**Unknown is not healthy.** An integration nothing has run against is
``UNKNOWN``, and the distinction is the same one ``Pages.truncated`` makes: a
result that was never obtained must not be reported as a result that was.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from integrations._catalogue.entry import HealthStatus

#: What a clock is here. Injectable so a test asserts a timestamp rather than a
#: range, and so a deployment can hand over the same clock everything else uses.
Clock = Callable[[], datetime]


def _now() -> datetime:
    """Return the current instant, in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class HealthRecord:
    """What the last live run against one integration found."""

    integration: str
    status: HealthStatus
    detail: str = ""
    observed_at: datetime | None = None

    @property
    def degraded(self) -> bool:
        """Return whether this integration is known to be broken."""
        return self.status is HealthStatus.DEGRADED

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form the console renders."""
        return {
            "integration": self.integration,
            "status": self.status.value,
            "detail": self.detail,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
        }


class HealthLedger:
    """What the live contract runs have found, per integration.

    In memory and per process. Persisting it belongs to whatever runs the
    scheduled job, and putting a repository port behind this would make
    ``integrations/`` reach for storage — which Article XI does not permit and
    which this does not need: the ledger's job is to turn a run's outcome into a
    status, and the run's owner decides where the status is written down.
    """

    __slots__ = ("_clock", "_records")

    def __init__(self, *, clock: Clock = _now) -> None:
        self._clock = clock
        self._records: dict[str, HealthRecord] = {}

    def record_success(self, integration: str) -> HealthRecord:
        """Record that a live run against ``integration`` succeeded."""
        return self._record(integration, HealthStatus.HEALTHY, "")

    def record_failure(self, integration: str, *, detail: str) -> HealthRecord:
        """Record that a live run failed, and what it was that failed.

        ``detail`` is what makes degradation actionable. "datadog is degraded"
        is a status; "search_logs now answers 422 to a query that worked
        yesterday" is something an operator can raise with a vendor.
        """
        if not detail.strip():
            raise ValueError(
                f"{integration}: degrading an integration without saying what broke leaves "
                f"an operator with a red mark and no next step"
            )
        return self._record(integration, HealthStatus.DEGRADED, detail)

    def status_of(self, integration: str) -> HealthRecord:
        """Return what is known about ``integration``, or that nothing is."""
        held = self._records.get(integration)
        if held is not None:
            return held
        return HealthRecord(integration=integration, status=HealthStatus.UNKNOWN)

    def degraded(self) -> tuple[HealthRecord, ...]:
        """Return every integration a live run has found broken, in name order."""
        return tuple(
            self._records[name] for name in sorted(self._records) if self._records[name].degraded
        )

    def to_records(self) -> tuple[dict[str, object], ...]:
        """Return every held record, in name order, for a console or a report."""
        return tuple(self._records[name].to_record() for name in sorted(self._records))

    def _record(self, integration: str, status: HealthStatus, detail: str) -> HealthRecord:
        """Store and return one observation."""
        record = HealthRecord(
            integration=integration,
            status=status,
            detail=detail,
            observed_at=self._clock(),
        )
        self._records[integration] = record
        return record


__all__ = [
    "Clock",
    "HealthLedger",
    "HealthRecord",
]
