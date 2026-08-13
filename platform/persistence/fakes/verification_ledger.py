"""In-memory record of what has been checked, keyed the way a real one is.

Keyed by ``(kind, subject)``, which is what makes "one answer per thing" a
property of the storage rather than of every caller remembering to replace the
previous row.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.first_run import MAX_VERIFICATION_PAGE_SIZE
from platform.persistence.fakes.state import TenantState
from platform.persistence.ports.verification_ledger import (
    VerificationRecord,
    VerificationSubject,
    check_verification_limit,
    sort_key,
)


@dataclass(slots=True)
class FakeVerificationLedger:
    """One organisation's record of what has been checked."""

    org_id: str
    state: TenantState

    async def record(self, record: VerificationRecord) -> VerificationRecord:
        """Store ``record``, replacing any earlier answer about the same thing."""
        self.state.verifications[(record.kind.value, record.subject)] = record
        return record

    async def latest(self, *, kind: VerificationSubject, subject: str) -> VerificationRecord | None:
        """Return what is known about one thing, or ``None`` if nobody has checked it."""
        return self.state.verifications.get((kind.value, subject))

    async def records(
        self,
        *,
        kind: VerificationSubject | None = None,
        limit: int = MAX_VERIFICATION_PAGE_SIZE,
    ) -> tuple[VerificationRecord, ...]:
        """Return the recorded checks, by kind then subject."""
        bound = check_verification_limit(limit)
        found = [
            row for row in self.state.verifications.values() if kind is None or row.kind is kind
        ]
        found.sort(key=sort_key)
        return tuple(found[:bound])

    async def forget(self, *, kind: VerificationSubject, subject: str) -> bool:
        """Delete what was recorded about one thing, and say whether there was any."""
        return self.state.verifications.pop((kind.value, subject), None) is not None


__all__ = ["FakeVerificationLedger"]
