"""What has actually been checked on this deployment, and what the check found.

The eighteenth port, and the smallest. It exists because of a defect that is
easy to describe and impossible to work around from a console: a check that
passed reported green while the page was open and reverted to "nobody has
checked this one" on reload, because nothing wrote the answer down. The setup
step that says "check that each of them works" was therefore uncompletable —
not hard, uncompletable — for as long as the result lived in a process.

**Current state, not history.** One row per thing that can be checked, replaced
each time it is checked. A ledger of every check ever run would be a different
port with a retention class and a paging story, and none of it would answer the
one question every surface here asks, which is whether this thing works *now*.
The remediation ledger is the one that keeps history, and it keeps it because a
success ratio needs the rows.

**A verdict belongs to the credential it was reached with.** Replacing a key
forgets the verdict — ``forget`` is on the protocol for that reason and is
called by the write that stores a credential. Without it, a deployment whose
key was rotated to a broken one keeps the green tick it earned with the old
one, which is worse than never having checked: it is a wrong answer with the
authority of a measurement.

**Keyed per organisation and not per team.** Credentials are held per team, but
the question a checklist asks is "has anybody on this deployment got Prometheus
working", and a read narrowed to one team would answer no for a deployment where
the one operator who set it up did so under theirs. The team that ran the check
is carried on the row, so the fact is not lost — it is just not the key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from config.constants.first_run import (
    MAX_VERIFICATION_PAGE_SIZE,
    SETUP_CHECK_FAILED,
    SETUP_CHECK_PASSED,
    SETUP_CHECK_SUBJECT_INTEGRATION,
    SETUP_CHECK_SUBJECT_PROVIDER,
)
from platform.persistence.errors import BoundExceeded


class VerificationOutcome(StrEnum):
    """What one check concluded. There is no third member.

    A check that could not be run is a check with no row. Writing "unknown"
    down would make the absence of a record and the presence of an inconclusive
    one two spellings of the same screen, and then "nobody has checked this" —
    the sentence this whole port exists to stop being permanent — would have two
    sources that can disagree.
    """

    #: The thing answered, doing what it was asked to do.
    PASSED = SETUP_CHECK_PASSED
    #: It was reached and it did not. ``detail`` says what happened.
    FAILED = SETUP_CHECK_FAILED


class VerificationSubject(StrEnum):
    """What was checked. Two, because they are checked by different code.

    An integration's check asks a vendor; a provider's check exercises tool
    calling and structured output against a model endpoint. They answer with
    different evidence, and an operator reading "prometheus is verified" is
    being told nothing at all about their model.
    """

    INTEGRATION = SETUP_CHECK_SUBJECT_INTEGRATION
    MODEL_PROVIDER = SETUP_CHECK_SUBJECT_PROVIDER


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    """One thing, the last time it was checked, and what the check found.

    ``model_id`` is on the row rather than in ``detail`` because the provider
    check's whole failure mode was verifying a model nobody configured: a
    verdict that does not name what it exercised is a verdict an operator cannot
    tell apart from the wrong one.
    """

    subject: str
    kind: VerificationSubject
    outcome: VerificationOutcome
    checked_at: datetime
    #: What the check found, in a sentence. Required for a failure.
    detail: str = ""
    #: Who asked for it. Empty for a check a scheduled job ran.
    checked_by: str = ""
    #: The team whose credential was exercised. Carried, never keyed on.
    team_node_id: str = ""
    #: The model a provider check actually exercised. Empty for an integration.
    model_id: str = ""

    def __post_init__(self) -> None:
        if not self.subject:
            raise ValueError(
                "A verification needs the subject it is about. A verdict with no subject "
                "is a green tick nothing can be joined to."
            )
        if self.outcome is VerificationOutcome.FAILED and not self.detail.strip():
            raise ValueError(
                f"{self.subject!r} is recorded as failed with no detail. A red mark that "
                f"does not say what happened leaves an operator with a colour and no "
                f"next step, which is the state this record exists to end."
            )

    @property
    def verified(self) -> bool:
        """Return whether this thing is known to work."""
        return self.outcome is VerificationOutcome.PASSED


def check_verification_limit(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the page bound."""
    if limit > MAX_VERIFICATION_PAGE_SIZE:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_VERIFICATION_PAGE_SIZE,
            constant="MAX_VERIFICATION_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def sort_key(record: VerificationRecord) -> tuple[str, str]:
    """Return the order both backends list records in: kind, then subject.

    Shared rather than implemented twice, so a console rendered from PostgreSQL
    and one rendered from the in-memory backend cannot put the same three rows
    in two orders.
    """
    return (record.kind.value, record.subject)


@runtime_checkable
class VerificationLedger(Protocol):
    """One organisation's record of what has been checked, inside one transaction."""

    async def record(self, record: VerificationRecord) -> VerificationRecord:
        """Store ``record``, replacing any earlier answer about the same thing.

        Keyed by ``(kind, subject)`` rather than generated, because this is
        current state: two rows for one integration would be two answers to
        "does this work", and a surface would have to pick one.
        """

    async def latest(self, *, kind: VerificationSubject, subject: str) -> VerificationRecord | None:
        """Return what is known about one thing, or ``None`` if nobody has checked it."""

    async def records(
        self,
        *,
        kind: VerificationSubject | None = None,
        limit: int = MAX_VERIFICATION_PAGE_SIZE,
    ) -> tuple[VerificationRecord, ...]:
        """Return the recorded checks, by kind then subject.

        ``kind`` of ``None`` is every kind rather than none, for the reason
        ``EstateQuery`` gives: it is the only reading that composes when a
        caller builds the argument from an optional input. Raises
        ``BoundExceeded`` above ``MAX_VERIFICATION_PAGE_SIZE``.
        """

    async def forget(self, *, kind: VerificationSubject, subject: str) -> bool:
        """Delete what was recorded about one thing, and say whether there was any.

        Called when the credential behind it is replaced. ``False`` rather than
        an error for something nobody had checked: the caller wanted the row
        gone, and it is gone.
        """


__all__ = [
    "VerificationLedger",
    "VerificationOutcome",
    "VerificationRecord",
    "VerificationSubject",
    "check_verification_limit",
    "sort_key",
]
