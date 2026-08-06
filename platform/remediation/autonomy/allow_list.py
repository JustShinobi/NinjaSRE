"""What a team has opted into running without a human, and under what conditions.

Read-only by default is the rule, and this is its explicit, scoped, revocable
exception. An entry says: *this* team, *this* action type, when *all* of these
conditions hold. Three properties keep that from being a hole rather than an
exception.

**Conditions are conjunctive.** Every one has to hold. An "any of" allow-list
would be widened one condition at a time by people each solving a real problem,
and the union of five reasonable relaxations is not reasonable.

**Production is excluded unless an entry names it.** An entry that declares no
environment condition gets one that refuses production, added here rather than
left to the operator. The alternative is a default nobody chose taking effect in
the environment where a mistake is most expensive.

**A condition is re-evaluated at execution time, not only when the action is
proposed.** That is ``evaluation``'s job rather than this module's — what lives
here is the declaration, deliberately with no notion of "now" in it, so a
condition cannot be answered once and cached by accident.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.security import (
    AUTONOMY_DEFAULT_MAX_BLAST_RADIUS,
    AUTONOMY_DEFAULT_RATE_LIMIT,
    AUTONOMY_RATE_LIMIT_WINDOW_SECONDS,
    PRODUCTION_ENVIRONMENT,
)
from platform.remediation.models import RemediationAction


@dataclass(frozen=True, slots=True)
class ConditionContext:
    """Everything a condition is answered against, at the moment it is asked.

    Assembled fresh for each evaluation. There is no cached field on it and no
    way to build one from an action alone, which is what stops a condition being
    answered at request time and reused at execution time — the specific failure
    the re-evaluation requirement exists to prevent.
    """

    action: RemediationAction
    at: datetime
    blast_radius: int = 0
    #: When this team last ran this action type autonomously, most recent last.
    recent: tuple[datetime, ...] = ()


@runtime_checkable
class Condition(Protocol):
    """One requirement an autonomous execution has to satisfy."""

    @property
    def name(self) -> str:
        """Return what this condition is called, for the refusal that names it."""

    def unmet(self, context: ConditionContext) -> str | None:
        """Return why this condition does not hold, or ``None`` when it does."""


@dataclass(frozen=True, slots=True)
class TargetPattern:
    """Only targets whose identifier matches a glob.

    A glob rather than a regular expression. Operators write these, the
    difference between ``staging-*`` and a pattern that accidentally matches
    everything is one character in the second language, and this is a list whose
    over-broad entry is a production outage.
    """

    pattern: str

    @property
    def name(self) -> str:
        """Return what this condition is called."""
        return "target pattern"

    def unmet(self, context: ConditionContext) -> str | None:
        """Return why the target is outside the pattern, or ``None``."""
        identifier = context.action.target.identifier
        if fnmatch.fnmatchcase(identifier, self.pattern):
            return None
        return f"{identifier!r} does not match the permitted pattern {self.pattern!r}"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """Only between two hours of the day, in UTC.

    Wrapping windows are supported and are the common case: "outside business
    hours" is 18:00 to 08:00, and a window type that could not express it would
    be one operators worked around by declaring two entries.
    """

    start_hour: int
    end_hour: int

    def __post_init__(self) -> None:
        for hour in (self.start_hour, self.end_hour):
            if not 0 <= hour <= 23:
                raise ValueError(f"A time window's hours must be 0–23; got {hour}.")
        if self.start_hour == self.end_hour:
            raise ValueError(
                "A window starting and ending at the same hour permits either nothing or "
                "everything depending on how it is read. Say which you meant."
            )

    @property
    def name(self) -> str:
        """Return what this condition is called."""
        return "time window"

    def unmet(self, context: ConditionContext) -> str | None:
        """Return why the current hour is outside the window, or ``None``."""
        hour = context.at.hour
        inside = (
            self.start_hour <= hour < self.end_hour
            if self.start_hour < self.end_hour
            else hour >= self.start_hour or hour < self.end_hour
        )
        if inside:
            return None
        return (
            f"{hour:02d}:00 UTC is outside the permitted window "
            f"{self.start_hour:02d}:00–{self.end_hour:02d}:00 UTC"
        )


@dataclass(frozen=True, slots=True)
class MaximumBlastRadius:
    """Only when few enough services depend on the target.

    The number is what changes between the request and the execution more often
    than anything else here — a dependency added, a discovery run completing —
    which is why re-evaluation matters most for this one.
    """

    limit: int = AUTONOMY_DEFAULT_MAX_BLAST_RADIUS

    @property
    def name(self) -> str:
        """Return what this condition is called."""
        return "maximum blast radius"

    def unmet(self, context: ConditionContext) -> str | None:
        """Return why the blast radius is too wide, or ``None``."""
        if context.blast_radius <= self.limit:
            return None
        return (
            f"{context.blast_radius} service(s) depend on "
            f"{context.action.target.identifier!r}, above the permitted {self.limit}"
        )


@dataclass(frozen=True, slots=True)
class RateLimit:
    """At most so many autonomous runs of this action per team, per window.

    A ceiling on damage rather than on nuisance. Whatever is wrong with an
    entry's other conditions, this is what bounds how many times it can be wrong
    before somebody notices.
    """

    limit: int = AUTONOMY_DEFAULT_RATE_LIMIT
    window_seconds: float = AUTONOMY_RATE_LIMIT_WINDOW_SECONDS

    @property
    def name(self) -> str:
        """Return what this condition is called."""
        return "rate limit"

    def unmet(self, context: ConditionContext) -> str | None:
        """Return why the rate limit is spent, or ``None``."""
        cutoff = context.at.timestamp() - self.window_seconds
        within = [moment for moment in context.recent if moment.timestamp() > cutoff]
        if len(within) < self.limit:
            return None
        return (
            f"{len(within)} autonomous run(s) of {context.action.capability!r} in the last "
            f"{self.window_seconds / 60:g} minutes, at the permitted limit of {self.limit}"
        )


@dataclass(frozen=True, slots=True)
class EnvironmentIs:
    """Only in these environments, and never in one that is not listed."""

    environments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "environments", tuple(sorted({name for name in self.environments if name}))
        )

    @property
    def name(self) -> str:
        """Return what this condition is called."""
        return "environment"

    def unmet(self, context: ConditionContext) -> str | None:
        """Return why the environment is not permitted, or ``None``."""
        environment = context.action.target.environment
        if environment and environment in self.environments:
            return None
        listed = ", ".join(self.environments) or "none"
        found = environment or "an unnamed environment"
        return f"{found} is not one of the permitted environments ({listed})"


#: The condition an entry gets when it declares none of its own: every
#: environment except production. Written as an exclusion the entry can
#: override by naming production explicitly, so enabling autonomy there is a
#: decision somebody made rather than a default they inherited.
def _default_environments(action_environments: Sequence[str]) -> EnvironmentIs:
    """Return the environment condition an entry with none of its own gets."""
    return EnvironmentIs(
        environments=tuple(name for name in action_environments if name != PRODUCTION_ENVIRONMENT)
    )


@dataclass(frozen=True, slots=True)
class AllowListEntry:
    """One team's opt-in for one action type, and the conditions on it.

    ``environments`` is a constructor convenience rather than a second way to
    say the same thing: it becomes an ``EnvironmentIs`` condition, so everything
    downstream evaluates one uniform list and no code path has to remember that
    environments are checked somewhere else as well.
    """

    capability: str
    team_node_id: str
    conditions: tuple[Condition, ...] = ()
    environments: tuple[str, ...] = ()
    added_by: str = ""

    def __post_init__(self) -> None:
        if not self.capability:
            raise ValueError("An allow-list entry needs the action type it permits.")
        if not self.team_node_id:
            raise ValueError(
                "An allow-list entry needs the team it belongs to. An entry scoped to "
                "nobody is an entry scoped to everybody."
            )
        declared = tuple(self.conditions)
        if not any(isinstance(condition, EnvironmentIs) for condition in declared):
            declared = (*declared, _default_environments(self.environments))
        object.__setattr__(self, "conditions", declared)

    def covers(self, action: RemediationAction) -> bool:
        """Return whether this entry is the one to evaluate for ``action``.

        Capability and team only. Everything else about whether the action may
        run is a condition, evaluated against the moment it runs — and folding
        one of them into the match would make it the one condition that was
        never re-evaluated.
        """
        return action.capability == self.capability and action.team_node_id == self.team_node_id

    def unmet(self, context: ConditionContext) -> tuple[str, ...]:
        """Return every condition that does not hold, in declaration order."""
        return tuple(
            reason
            for reason in (condition.unmet(context) for condition in self.conditions)
            if reason is not None
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this entry."""
        return {
            "capability": self.capability,
            "team_node_id": self.team_node_id,
            "added_by": self.added_by,
            "conditions": [condition.name for condition in self.conditions],
        }


@dataclass(slots=True)
class AllowList:
    """Every entry a deployment has, and the lookup the gate makes against it.

    A miss is the normal case and is not an error: most actions are not
    allow-listed and go to a human, which is the default the whole feature is
    built around.
    """

    entries: list[AllowListEntry] = field(default_factory=list)

    def add(self, entry: AllowListEntry) -> AllowList:
        """Add ``entry``, replacing any entry for the same team and action type."""
        self.entries = [
            held
            for held in self.entries
            if not (held.capability == entry.capability and held.team_node_id == entry.team_node_id)
        ]
        self.entries.append(entry)
        return self

    def remove(self, *, capability: str, team_node_id: str) -> bool:
        """Remove one entry and return whether it was there."""
        before = len(self.entries)
        self.entries = [
            held
            for held in self.entries
            if not (held.capability == capability and held.team_node_id == team_node_id)
        ]
        return len(self.entries) < before

    def entry_for(self, action: RemediationAction) -> AllowListEntry | None:
        """Return the entry covering ``action``, or ``None`` when none does."""
        for entry in self.entries:
            if entry.covers(action):
                return entry
        return None

    def report(self) -> tuple[Mapping[str, Any], ...]:
        """Return every entry, for the console and an operator's review."""
        return tuple(
            entry.to_record()
            for entry in sorted(self.entries, key=lambda held: (held.team_node_id, held.capability))
        )

    def __len__(self) -> int:
        """Return how many entries this deployment has."""
        return len(self.entries)


__all__ = [
    "AllowList",
    "AllowListEntry",
    "Condition",
    "ConditionContext",
    "EnvironmentIs",
    "MaximumBlastRadius",
    "RateLimit",
    "TargetPattern",
    "TimeWindow",
]
