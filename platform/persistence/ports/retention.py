"""How long each kind of record is kept, and the one kind that is never deleted.

FR-022 asks for configurable retention per data class with audit exempt. The
exemption is expressed twice on purpose. ``AuditRepository`` has no delete
method, so there is nothing for a sweep to call; and ``RetentionPolicy`` refuses
to be constructed with a finite window for ``DataClass.AUDIT``, so a policy that
would delete audit records cannot be represented, let alone applied. Either one
alone would hold today. Both together hold after somebody adds a generic
``delete_by_cutoff`` in a hurry.

Windows differ by an order of magnitude between classes, and the reason is worth
stating where the numbers are not: a trace is evidence for one investigation and
stops being interesting once the incident is closed, while episodes are the
corpus every ablation measures learning against. Deleting the corpus does not
just lose history — it removes the ability to prove the system improved, which
Article VII requires us to keep proving.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from config.constants.estate import RETENTION_DAYS_ESTATE_HISTORY
from config.constants.persistence import (
    RETENTION_DAYS_EPISODES,
    RETENTION_DAYS_KNOWLEDGE,
    RETENTION_DAYS_RUN_TRACES,
    RETENTION_DAYS_SESSIONS,
    RETENTION_EXEMPT_DATA_CLASSES,
)
from platform.persistence.errors import RetentionExempt


class DataClass(StrEnum):
    """A category of record with its own retention window."""

    RUN_TRACES = "run_traces"
    SESSIONS = "sessions"
    EPISODES = "episodes"
    KNOWLEDGE = "knowledge"
    AUDIT = "audit"
    #: Health transitions and the links from a resource to what touched it. The
    #: resources themselves are not swept: an absent resource *is* the record
    #: that something was removed, and deleting it would make the estate forget
    #: what it was asked to remember.
    ESTATE_HISTORY = "estate_history"

    @property
    def is_exempt(self) -> bool:
        """Return whether this class is exempt from retention deletion."""
        return self.value in RETENTION_EXEMPT_DATA_CLASSES


#: The window each class gets when the operator configures nothing. ``None``
#: means kept indefinitely, which is the only value an exempt class may hold.
DEFAULT_RETENTION_DAYS: dict[DataClass, int | None] = {
    DataClass.RUN_TRACES: RETENTION_DAYS_RUN_TRACES,
    DataClass.SESSIONS: RETENTION_DAYS_SESSIONS,
    DataClass.EPISODES: RETENTION_DAYS_EPISODES,
    DataClass.KNOWLEDGE: RETENTION_DAYS_KNOWLEDGE,
    DataClass.AUDIT: None,
    DataClass.ESTATE_HISTORY: RETENTION_DAYS_ESTATE_HISTORY,
}


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """One class of record and how long it is kept.

    ``retention_days`` of ``None`` means indefinitely. Constructing a finite
    window for an exempt class raises rather than being ignored: a policy that
    was silently not applied is worse than one that was rejected, because the
    operator believes it is in force.
    """

    data_class: DataClass
    retention_days: int | None

    def __post_init__(self) -> None:
        if self.data_class.is_exempt and self.retention_days is not None:
            raise RetentionExempt(self.data_class.value)
        if self.retention_days is not None and self.retention_days < 1:
            raise ValueError(
                f"A retention window of {self.retention_days} days would delete "
                f"{self.data_class.value} as fast as they are written. Use None to keep them."
            )

    @classmethod
    def default_for(cls, data_class: DataClass) -> RetentionPolicy:
        """Return the policy this class gets when nothing is configured."""
        return cls(data_class=data_class, retention_days=DEFAULT_RETENTION_DAYS[data_class])

    def cutoff(self, now: datetime) -> datetime | None:
        """Return the timestamp before which records may be deleted, or ``None``."""
        if self.retention_days is None:
            return None
        return now - timedelta(days=self.retention_days)


@dataclass(frozen=True, slots=True)
class PurgeReport:
    """What one retention pass actually removed."""

    data_class: DataClass
    deleted: int = 0
    cutoff: datetime | None = None


@runtime_checkable
class RetentionSweeper(Protocol):
    """Applies retention policies, across every tenant.

    Reached through the system unit of work. Retention is a property of the
    deployment rather than of one organisation, and running it per tenant would
    mean a tenant nobody swept keeping records forever without anybody noticing.
    """

    async def purge(self, policy: RetentionPolicy, *, now: datetime) -> PurgeReport:
        """Delete records older than ``policy``'s cutoff and report the count.

        A policy with no cutoff deletes nothing and reports zero. Raises
        ``RetentionExempt`` for an exempt data class, which is unreachable
        through ``RetentionPolicy`` and checked anyway — the implementations are
        what this contract is for.
        """

    async def purge_all(
        self,
        policies: tuple[RetentionPolicy, ...],
        *,
        now: datetime,
    ) -> tuple[PurgeReport, ...]:
        """Apply every policy and return one report each, in the order given."""


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "DataClass",
    "PurgeReport",
    "RetentionPolicy",
    "RetentionSweeper",
]
