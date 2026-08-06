"""Answering an allow-list entry's conditions, twice, against two different moments.

An approval can sit pending for ten minutes and an allow-listed action is
checked when it is proposed and again when it runs. In between, the things the
conditions are about change: a dependency is discovered, the clock crosses out
of the maintenance window, two other autonomous runs spend the rate limit. A
condition answered once is a condition about a system that no longer exists.

So there is one evaluator and it takes the moment as an argument. It has no
memory of a previous answer and offers no way to reuse one — the closest thing
to a cache here is the ledger of *completed* autonomous runs, which is the input
the rate limit needs and is deliberately not an answer to anything.

**Every unmet condition is reported, not the first.** An operator widening an
entry needs the full list, because fixing one and re-running to discover the
next is how an allow-list gets widened further than anybody intended.

**A run is recorded only once it has actually happened.** Recording at the point
of permission would let a refused-later action spend the rate limit, and would
make the limit bound attempts rather than changes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.constants.security import AUTONOMY_RATE_LIMIT_WINDOW_SECONDS
from platform.observability.logging import get_logger
from platform.remediation.autonomy.allow_list import (
    AllowList,
    AllowListEntry,
    ConditionContext,
)
from platform.remediation.errors import ConditionsNotMet
from platform.remediation.models import RemediationAction

_LOG = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Whether an action may run autonomously right now, and why not if it may not.

    ``entry`` is carried even on a refusal. "There is no entry" and "the entry's
    window closed" send an operator to different screens, and a bare ``False``
    would collapse them.
    """

    action_id: str
    capability: str
    permitted: bool
    entry: AllowListEntry | None = None
    unmet: tuple[str, ...] = ()
    evaluated_at: datetime | None = None

    @property
    def allow_listed(self) -> bool:
        """Return whether an entry covers this action at all."""
        return self.entry is not None

    def describe(self) -> str:
        """Return the sentence an operator or a denial message shows."""
        if self.permitted:
            return f"{self.capability} is permitted autonomously for this team right now."
        if self.entry is None:
            return (
                f"{self.capability} is not on this team's autonomous allow-list, so it "
                f"needs a human approval."
            )
        listed = "; ".join(self.unmet)
        return (
            f"{self.capability} is allow-listed for this team, but its conditions do not "
            f"hold: {listed}. It needs a human approval instead."
        )

    def raise_if_refused(self) -> None:
        """Raise ``ConditionsNotMet`` when an entry exists and its conditions lapsed.

        Only when an entry exists. An action that was never allow-listed is not
        a refusal to explain — it is the default, and raising for it would turn
        "most actions go to a human" into an exception path.
        """
        if self.permitted or self.entry is None:
            return
        raise ConditionsNotMet(self.capability, self.unmet)

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, which the audit trail carries."""
        return {
            "action_id": self.action_id,
            "capability": self.capability,
            "permitted": self.permitted,
            "allow_listed": self.allow_listed,
            "unmet": list(self.unmet),
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
        }


@dataclass(slots=True)
class ExecutionLedger:
    """When each team last ran each action type autonomously.

    Bounded by the rate-limit window rather than kept forever: this exists to
    answer one question about the recent past, and an unbounded list keyed by
    team and capability is a slow memory leak driven by exactly the deployments
    that use autonomy most.
    """

    window_seconds: float = AUTONOMY_RATE_LIMIT_WINDOW_SECONDS
    runs: dict[tuple[str, str], list[datetime]] = field(default_factory=dict)

    def record(self, action: RemediationAction, *, at: datetime) -> None:
        """Record that ``action`` ran autonomously at ``at``."""
        key = _key(action)
        held = self.runs.setdefault(key, [])
        held.append(at)
        self.runs[key] = self._within(held, at)

    def recent(self, action: RemediationAction, *, at: datetime) -> tuple[datetime, ...]:
        """Return this team's runs of this action type inside the window."""
        held = self.runs.get(_key(action))
        return tuple(self._within(held, at)) if held else ()

    def _within(self, moments: list[datetime], at: datetime) -> list[datetime]:
        """Return the moments still inside the window ending at ``at``."""
        cutoff = at.timestamp() - self.window_seconds
        return [moment for moment in moments if moment.timestamp() > cutoff]


def _key(action: RemediationAction) -> tuple[str, str]:
    """Return the ledger key an action counts against: its team and its type."""
    return (action.team_node_id or "", action.capability)


@dataclass(slots=True)
class ConditionEvaluator:
    """Evaluates an allow-list conjunctively, at whatever moment it is asked.

    Holds the list and the ledger and nothing else. In particular it holds no
    result: an evaluator that remembered its last answer would be the cache this
    module exists to not have.
    """

    allow_list: AllowList
    ledger: ExecutionLedger = field(default_factory=ExecutionLedger)

    def evaluate(
        self,
        action: RemediationAction,
        *,
        at: datetime,
        blast_radius: int = 0,
    ) -> Evaluation:
        """Return whether ``action`` may run autonomously at ``at``.

        ``blast_radius`` is passed rather than computed here, because the answer
        comes from the topology graph and this package is not the one that talks
        to it — and because passing it makes it obvious at every call site that
        a stale number is a stale decision.
        """
        entry = self.allow_list.entry_for(action)
        if entry is None:
            return Evaluation(
                action_id=action.action_id,
                capability=action.capability,
                permitted=False,
                evaluated_at=at,
            )

        context = ConditionContext(
            action=action,
            at=at,
            blast_radius=blast_radius,
            recent=self.ledger.recent(action, at=at),
        )
        unmet = entry.unmet(context)
        evaluation = Evaluation(
            action_id=action.action_id,
            capability=action.capability,
            permitted=not unmet,
            entry=entry,
            unmet=unmet,
            evaluated_at=at,
        )
        if unmet:
            _LOG.info(
                "remediation.autonomy_conditions_unmet",
                action_id=action.action_id,
                capability=action.capability,
                team=action.team_node_id,
                unmet=list(unmet),
            )
        return evaluation

    def record_execution(self, action: RemediationAction, *, at: datetime) -> None:
        """Record a completed autonomous execution against the rate limit."""
        self.ledger.record(action, at=at)

    def report(self) -> Mapping[str, Any]:
        """Return what a health endpoint says about autonomy in this deployment."""
        return {
            "entries": list(self.allow_list.report()),
            "window_seconds": self.ledger.window_seconds,
        }


__all__ = [
    "ConditionEvaluator",
    "Evaluation",
    "ExecutionLedger",
]
