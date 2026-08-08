"""The four gates no level overrides, evaluated after the level and never as one.

The kill switch, freeze windows, action budgets and the rollback requirement are
not high settings of the same scale. They are a second gate, and the difference
is the point: expressed as levels, some configuration somewhere could set a
level that passes them. Expressed here, the most permissive posture an operator
can write still stops at all four.

They are evaluated in a fixed order — stop, freeze, budget, rollback — and the
first one that refuses is the one named. The order is severity, not efficiency:
an operator reading "refused by the kill switch" needs to know that first, and
learning instead that their budget is spent would send them to fix the wrong
thing.

**The stop is a protocol, satisfied structurally.** The deployment already holds
one emergency stop, and a second one in this package would be a second thing to
engage during the ten seconds in which it matters. Depending on it by shape
rather than by import keeps the dependency pointing the way the tier table says
it must, and keeps this package testable without one.

**A freeze window is read in a named timezone, always.** A window that meant
something different on a laptop and in the cluster would be the least debuggable
control here, and "01:00 to 04:00" during a daylight-saving change is a real
question with a real answer that only ``zoneinfo`` has.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.constants.autonomy import (
    AUTONOMY_BOUND_BUDGET,
    AUTONOMY_BOUND_FREEZE,
    AUTONOMY_BOUND_KILL_SWITCH,
    AUTONOMY_BOUND_ROLLBACK,
    AUTONOMY_BUDGET_SCOPE_CAPABILITY,
    AUTONOMY_BUDGET_SCOPE_RESOURCE,
    AUTONOMY_BUDGET_SCOPE_TEAM,
    AUTONOMY_BUDGET_SCOPES,
    DEFAULT_AUTONOMY_BUDGET,
    DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS,
    DEFAULT_FREEZE_TIMEZONE,
)
from platform.autonomy.scopes import PolicyScope
from platform.autonomy.subjects import ProposedAction, Subject


class Bound(StrEnum):
    """Which of the four gates refused, in the order they are evaluated."""

    KILL_SWITCH = AUTONOMY_BOUND_KILL_SWITCH
    FREEZE = AUTONOMY_BOUND_FREEZE
    BUDGET = AUTONOMY_BOUND_BUDGET
    ROLLBACK = AUTONOMY_BOUND_ROLLBACK


@runtime_checkable
class EmergencyStop(Protocol):
    """Whatever this deployment stops automated writes with.

    Structural, so the deployment's existing switch satisfies it without this
    package importing one — and so a test can supply a stop that is simply on.
    """

    def is_engaged(self, *, team_node_id: str | None = None) -> bool:
        """Return whether any switch currently stops this team's writes."""

    def describe_for(self, *, team_node_id: str | None = None) -> str:
        """Return the sentence a refusal shows, empty when nothing is engaged."""


@dataclass(frozen=True, slots=True)
class NoStop:
    """No switch is engaged. The neutral default and the test double."""

    def is_engaged(self, *, team_node_id: str | None = None) -> bool:
        """Return ``False``: nothing here stops anything."""
        del team_node_id
        return False

    def describe_for(self, *, team_node_id: str | None = None) -> str:
        """Return the empty description of a switch that is not engaged."""
        del team_node_id
        return ""


@dataclass(frozen=True, slots=True)
class FreezeWindow:
    """A span of the day during which nothing in scope may run, in a named zone.

    Wrapping windows are supported and are the common case — backups run from
    01:00 to 04:00 and maintenance from 22:00 to 06:00 — because a window type
    that could not express one is a window operators work around by declaring
    two, and two windows with one typo between them is a gap nobody sees.
    """

    name: str
    scope: PolicyScope
    start: time
    end: time
    timezone: str = DEFAULT_FREEZE_TIMEZONE
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A freeze window needs a name; a refusal has to name what refused.")
        if self.start == self.end:
            raise ValueError(
                f"{self.name}: a window starting and ending at the same time freezes either "
                f"nothing or everything depending on how it is read. Say which you meant."
            )
        # Resolved once, here, so a zone nobody has fails at save time rather
        # than at three in the morning when the window would have applied.
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as unknown:
            raise ValueError(
                f"{self.name}: {self.timezone!r} is not a timezone this host knows"
            ) from unknown

    def covers(self, at: datetime, action: ProposedAction, subject: Subject) -> bool:
        """Return whether ``at`` falls inside this window for ``subject``."""
        if not self.scope.matches(action, subject):
            return False
        return self.contains(at)

    def contains(self, at: datetime) -> bool:
        """Return whether ``at``, read in this window's own zone, is inside it.

        The conversion is the whole of the timezone requirement: an instant is
        compared against a wall-clock span, and which wall clock is a property
        of the window rather than of the host that happens to be asking.
        """
        local = at.astimezone(ZoneInfo(self.timezone)).timetz().replace(tzinfo=None)
        if self.start < self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end

    def describe(self) -> str:
        """Return the sentence an operator reads when this window refuses."""
        why = f" — {self.reason}" if self.reason else ""
        return (
            f"the freeze window {self.name!r} covers {self.scope.describe()} between "
            f"{self.start.isoformat('minutes')} and {self.end.isoformat('minutes')} "
            f"{self.timezone}{why}"
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, which is also the exported document's form."""
        record: dict[str, Any] = {
            "name": self.name,
            "scope": self.scope.to_record(),
            "start": self.start.isoformat("minutes"),
            "end": self.end.isoformat("minutes"),
            "timezone": self.timezone,
        }
        if self.reason:
            record["reason"] = self.reason
        return record


@dataclass(frozen=True, slots=True)
class BudgetRule:
    """How many actions may run in scope over an interval, and against what.

    Counted per resource, per capability, or per team. One action spends every
    budget that covers it rather than the narrowest, because they are three
    ceilings on three different things: "no more than twice on this container"
    and "no more than ten times across this team" are both true statements and
    neither is a weaker version of the other.
    """

    name: str
    counted_by: str = AUTONOMY_BUDGET_SCOPE_RESOURCE
    limit: int = DEFAULT_AUTONOMY_BUDGET
    interval_seconds: float = DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS
    scope: PolicyScope | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A budget needs a name; an exhaustion has to name what is spent.")
        if self.counted_by not in AUTONOMY_BUDGET_SCOPES:
            raise ValueError(
                f"{self.name}: {self.counted_by!r} is not something a budget counts against; "
                f"expected one of {', '.join(AUTONOMY_BUDGET_SCOPES)}"
            )
        if self.limit < 0:
            raise ValueError(f"{self.name}: a budget of {self.limit} is not a budget.")
        if self.interval_seconds <= 0:
            raise ValueError(
                f"{self.name}: a budget interval must be a positive number of seconds."
            )

    def applies_to(self, action: ProposedAction, subject: Subject) -> bool:
        """Return whether this budget covers ``subject`` under ``action``."""
        return self.scope is None or self.scope.matches(action, subject)

    def key_for(self, action: ProposedAction, subject: Subject) -> str:
        """Return the ledger key this action spends against for ``subject``.

        The budget's own name is part of the key. Two budgets counting the same
        resource on different intervals are two ceilings, and a key that omitted
        the name would make them one.
        """
        if self.counted_by == AUTONOMY_BUDGET_SCOPE_CAPABILITY:
            counted = action.capability
        elif self.counted_by == AUTONOMY_BUDGET_SCOPE_TEAM:
            counted = subject.team_node_id or action.team_node_id
        else:
            counted = subject.resource_id
        return f"{self.name}:{self.counted_by}:{counted}"

    def describe(self, spent: int) -> str:
        """Return the sentence an operator reads when this budget refuses."""
        minutes = self.interval_seconds / 60
        return (
            f"the budget {self.name!r} permits {self.limit} action(s) per "
            f"{minutes:g} minutes per {self.counted_by}, and {spent} have run"
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, which is also the exported document's form."""
        record: dict[str, Any] = {
            "name": self.name,
            "counted_by": self.counted_by,
            "limit": self.limit,
            "interval_seconds": self.interval_seconds,
        }
        if self.scope is not None:
            record["scope"] = self.scope.to_record()
        return record


@dataclass(frozen=True, slots=True)
class BoundOutcome:
    """Whether the bounds refused, which one did, and what to tell an operator.

    ``exhausted`` is separate from ``bound`` because a spent budget is the one
    refusal that has to raise attention of its own: the deployment has stopped
    doing something it was configured to do, and nothing else here will say so.
    """

    refused: bool = False
    bound: Bound | None = None
    reason: str = ""
    exhausted: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the decision's audit detail carries."""
        return {
            "refused": self.refused,
            "bound": self.bound.value if self.bound is not None else "",
            "reason": self.reason,
            "exhausted_budgets": list(self.exhausted),
        }


#: Nothing refused. A value rather than ``None`` so a caller reads one shape.
PERMITTED: BoundOutcome = BoundOutcome()


@dataclass(frozen=True, slots=True)
class BudgetState:
    """What a budget has already spent, as the ledger answered it."""

    rule: BudgetRule
    key: str
    spent: int = 0

    @property
    def exhausted(self) -> bool:
        """Return whether this budget has nothing left."""
        return self.spent >= self.rule.limit


def evaluate_bounds(
    action: ProposedAction,
    *,
    at: datetime,
    stop: EmergencyStop,
    freezes: Sequence[FreezeWindow] = (),
    budgets: Sequence[BudgetState] = (),
) -> BoundOutcome:
    """Return whether any bound refuses ``action``, and which one did.

    Pure, and takes the budget's already-read state rather than the ledger. The
    reading is the one part of this that touches storage, and keeping it outside
    means the whole ordering — stop, freeze, budget, rollback — is exhaustively
    testable without one.
    """
    if stop.is_engaged(team_node_id=action.team_node_id or None):
        return BoundOutcome(
            refused=True,
            bound=Bound.KILL_SWITCH,
            reason=stop.describe_for(team_node_id=action.team_node_id or None)
            or "automated writes are stopped for this deployment",
        )

    for window in freezes:
        for subject in action.subjects:
            if window.covers(at, action, subject):
                return BoundOutcome(
                    refused=True,
                    bound=Bound.FREEZE,
                    reason=window.describe(),
                )

    spent = tuple(state for state in budgets if state.exhausted)
    if spent:
        return BoundOutcome(
            refused=True,
            bound=Bound.BUDGET,
            reason=spent[0].rule.describe(spent[0].spent),
            exhausted=tuple(state.key for state in spent),
        )

    if not action.has_rollback_plan:
        return BoundOutcome(
            refused=True,
            bound=Bound.ROLLBACK,
            reason=(
                f"{action.capability} has no rollback plan, so it needs a human approval "
                f"at every autonomy level"
            ),
        )

    return PERMITTED


def budget_states_needed(
    action: ProposedAction, budgets: Sequence[BudgetRule]
) -> tuple[tuple[BudgetRule, str], ...]:
    """Return every (budget, key) pair ``action`` would spend, deduplicated.

    Deduplicated because an action over twelve guests on one node spends a
    per-team budget once, not twelve times — the budget counts actions, and this
    is one action.
    """
    seen: dict[str, BudgetRule] = {}
    for rule in budgets:
        for subject in action.subjects:
            if not rule.applies_to(action, subject):
                continue
            key = rule.key_for(action, subject)
            seen.setdefault(key, rule)
    return tuple((rule, key) for key, rule in seen.items())


__all__ = [
    "PERMITTED",
    "Bound",
    "BoundOutcome",
    "BudgetRule",
    "BudgetState",
    "EmergencyStop",
    "FreezeWindow",
    "NoStop",
    "budget_states_needed",
    "evaluate_bounds",
]
