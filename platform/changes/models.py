"""One change, and the window a question about changes is asked in.

**The window is a value, not two arguments.** Every bound this feature has —
how far back, how many, how much of one — is enforced where the value is built,
so a caller cannot assemble a query that skips the ceiling by doing the
arithmetic itself.

**A change carries no diff, and there is nowhere to put one.** Judging whether a
change was *right* is out of scope, and the way to keep it out is structural: the
record has no field a patch could arrive in, so a later contributor who wants to
score a change's merit has to add one and argue for it.

**Applied and committed are the same record.** A commit is a statement about a
repository; an apply is what touched the cluster. Making them two types would
mean every caller matched on which one it had, and the caller that forgot would
report a merged pull request as the cause of an outage in an environment nobody
had deployed it to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from config.constants.changes import (
    DEFAULT_CHANGE_WINDOW_HOURS,
    MAX_CHANGE_MESSAGE_CHARS,
    MAX_CHANGE_WINDOW_HOURS,
    MAX_PATHS_PER_CHANGE,
)
from platform.changes.errors import ChangeWindowInvalid


@dataclass(frozen=True, slots=True)
class ChangeWindow:
    """The half-open interval ``[start, end)`` a change question covers.

    Half-open so two adjacent windows share no change. A closed interval would
    report the same apply in the hour before an incident and the hour before
    that, and a report built from both would say it happened twice.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ChangeWindowInvalid(
                f"a change window ends after it starts; {self.start.isoformat()} to "
                f"{self.end.isoformat()} is not a window"
            )
        if self.hours > MAX_CHANGE_WINDOW_HOURS:
            raise ChangeWindowInvalid(
                f"{self.hours:.1f} hours is wider than one query may cover, which is "
                f"MAX_CHANGE_WINDOW_HOURS ({MAX_CHANGE_WINDOW_HOURS}). Ask twice rather than "
                f"asking wider: a window this size is a report about the repository rather "
                f"than a question about what broke."
            )

    @classmethod
    def ending(
        cls,
        end: datetime,
        *,
        hours: float = DEFAULT_CHANGE_WINDOW_HOURS,
    ) -> ChangeWindow:
        """Return the window of ``hours`` ending at ``end``."""
        return cls(start=end - timedelta(hours=hours), end=end)

    @property
    def hours(self) -> float:
        """Return how many hours this window spans."""
        return (self.end - self.start).total_seconds() / 3600.0

    def contains(self, moment: datetime) -> bool:
        """Return whether ``moment`` falls inside this window."""
        return self.start <= moment < self.end

    def describe(self) -> str:
        """Return the window as a sentence a report can quote."""
        return (
            f"the {self.hours:.0f} hour(s) ending {self.end.isoformat()}"
            if self.hours >= 1
            else f"the {self.hours * 60:.0f} minute(s) ending {self.end.isoformat()}"
        )


@dataclass(frozen=True, slots=True)
class Change:
    """One thing somebody changed, as every source reports it.

    ``component`` is empty when the source could not derive one — a git host
    reporting a commit that touched three unrelated directories has no single
    component to name, and guessing would put a strength label on a correlation
    that has none behind it.
    """

    change_id: str
    occurred_at: datetime
    author: str
    message: str
    paths: tuple[str, ...]
    #: Which source reported this, named in the evidence entry. A negative claim
    #: is only worth something if it says what was consulted to make it.
    source: str
    component: str = ""
    #: When this reached the cluster, or ``None`` for a change that was committed
    #: and never applied. The presence of the instant *is* the applied flag, so
    #: the two cannot disagree.
    applied_at: datetime | None = None
    #: Guardrail rules that fired on this change's own text, by name. Present so
    #: a reader can tell a message that was redacted from one that happened to
    #: contain the redaction marker.
    redactions: tuple[str, ...] = ()
    #: How many paths the change really touched, before the per-change cap.
    paths_seen: int = 0
    paths_truncated: bool = False
    message_truncated: bool = False
    #: Anything the source knows that has no field here — a pipeline identifier,
    #: an apply outcome. Free-form on purpose, and screened by the source before
    #: it arrives.
    detail: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Truncation happens at construction rather than at each caller. A cap
        # applied by whoever remembered to is a cap that is missing wherever the
        # record is built next.
        seen = self.paths_seen or len(self.paths)
        object.__setattr__(self, "paths_seen", seen)
        if len(self.paths) > MAX_PATHS_PER_CHANGE:
            object.__setattr__(self, "paths", self.paths[:MAX_PATHS_PER_CHANGE])
            object.__setattr__(self, "paths_truncated", True)
        if len(self.message) > MAX_CHANGE_MESSAGE_CHARS:
            object.__setattr__(self, "message", self.message[:MAX_CHANGE_MESSAGE_CHARS])
            object.__setattr__(self, "message_truncated", True)

    @property
    def applied(self) -> bool:
        """Return whether this change reached the cluster.

        A commit that nobody applied changed nothing, and reporting it beside
        one that did — with no way to tell them apart — is how an investigation
        blames a merge that never left the repository.
        """
        return self.applied_at is not None

    @property
    def instant(self) -> datetime:
        """Return when this change took effect, which is the apply if there was one."""
        return self.applied_at if self.applied_at is not None else self.occurred_at

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a trace, a route and a console read."""
        return {
            "change_id": self.change_id,
            "source": self.source,
            "component": self.component,
            "author": self.author,
            "message": self.message,
            "message_truncated": self.message_truncated,
            "occurred_at": self.occurred_at.isoformat(),
            "applied": self.applied,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "paths": list(self.paths),
            "paths_seen": self.paths_seen,
            "paths_truncated": self.paths_truncated,
            "redactions": list(self.redactions),
            "detail": dict(self.detail),
        }


__all__ = ["Change", "ChangeWindow"]
