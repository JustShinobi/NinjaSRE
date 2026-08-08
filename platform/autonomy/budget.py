"""How many autonomous actions have already run, and where that count survives.

A budget interval outlives a deployment restart, so the count cannot live only
in the process that is counting. It lives in the audit trail: one append-only
row per action a budget is spent by, keyed by the budget and what it counts
against, and read back by the same window the budget is declared over.

That is a deliberate choice over a table of its own. The audit trail is already
in Postgres, already append-only, already tenant-scoped, and already the record
of every decision this package makes — so the spend and the decision that spent
it cannot disagree, and there is no second bookkeeping table to reconcile when
they do. A budget derived from the record *is* the record.

**Recording happens after the action, not when it is permitted.** A permitted
action that is then refused by something further down would otherwise spend the
budget without changing anything, which would make the limit bound attempts
rather than changes.

**The in-memory ledger is not a cache of the durable one.** It is the whole
ledger for a deployment with no persistence configured, and it says so. A
"cache" here would be a budget that reads as unspent for however long a replica
has been up.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from config.constants.autonomy import (
    AUTONOMY_AUDIT_ACTION_SPEND,
    AUTONOMY_AUDIT_RESOURCE_KIND_BUDGET,
    MAX_AUTONOMY_BUDGET_ROWS,
)
from platform.autonomy.bounds import BudgetRule, BudgetState, budget_states_needed
from platform.autonomy.subjects import ProposedAction
from platform.persistence.ports import (
    ActorKind,
    AuditEvent,
    AuditOutcome,
    PersistenceGateway,
    TenantScope,
)


@runtime_checkable
class SpendLedger(Protocol):
    """Where a budget's spend is counted, and where a new one is recorded."""

    async def spent(self, key: str, *, since: datetime) -> int:
        """Return how many actions have spent ``key`` since ``since``."""

    async def record(self, key: str, *, at: datetime, action_id: str) -> None:
        """Record that one action spent ``key`` at ``at``."""


@dataclass(slots=True)
class InMemorySpendLedger:
    """Spend held for the life of the process, and no longer.

    The honest ledger for a deployment with nothing behind it. A budget it
    reports is a budget over this replica's uptime, which is why the durable one
    exists and why this is not its cache.
    """

    spends: dict[str, list[datetime]] = field(default_factory=dict)

    async def spent(self, key: str, *, since: datetime) -> int:
        """Return how many spends of ``key`` fall inside the window."""
        held = self.spends.get(key, ())
        return sum(1 for moment in held if moment >= since)

    async def record(self, key: str, *, at: datetime, action_id: str) -> None:
        """Append one spend of ``key``."""
        del action_id
        self.spends.setdefault(key, []).append(at)


@dataclass(slots=True)
class AuditSpendLedger:
    """Spend counted from the audit trail, so it survives a restart.

    ``limit`` is bounded rather than unbounded because a budget is spent long
    before the bound is reached: the cap only ever limits what asking costs, and
    a count that stopped short would have stopped short of a number that had
    already refused the action.
    """

    gateway: PersistenceGateway
    scope: TenantScope
    actor_id: str = "ninjasre-autonomy"

    async def spent(self, key: str, *, since: datetime) -> int:
        """Return how many spend rows for ``key`` fall inside the window."""
        async with self.gateway.begin(self.scope) as uow:
            rows = await uow.audit.query(
                action=AUTONOMY_AUDIT_ACTION_SPEND,
                resource_kind=AUTONOMY_AUDIT_RESOURCE_KIND_BUDGET,
                resource_id=key,
                since=since,
                limit=MAX_AUTONOMY_BUDGET_ROWS,
            )
        return len(rows)

    async def record(self, key: str, *, at: datetime, action_id: str) -> None:
        """Append the one immutable row this spend is counted from."""
        async with self.gateway.begin(self.scope) as uow:
            await uow.audit.append(
                AuditEvent(
                    event_id=f"{AUTONOMY_AUDIT_ACTION_SPEND}:{action_id}:{key}",
                    occurred_at=at,
                    actor_kind=ActorKind.SYSTEM,
                    actor_id=self.actor_id,
                    action=AUTONOMY_AUDIT_ACTION_SPEND,
                    resource_kind=AUTONOMY_AUDIT_RESOURCE_KIND_BUDGET,
                    resource_id=key,
                    outcome=AuditOutcome.ALLOWED,
                    detail={"action_id": action_id, "budget": key},
                )
            )


def budget_keys(
    action: ProposedAction, budgets: Sequence[BudgetRule]
) -> tuple[tuple[BudgetRule, str], ...]:
    """Return every budget ``action`` would spend, and the key it spends it under."""
    return budget_states_needed(action, budgets)


async def read_budgets(
    action: ProposedAction,
    budgets: Sequence[BudgetRule],
    *,
    at: datetime,
    ledger: SpendLedger,
) -> tuple[BudgetState, ...]:
    """Return what each budget covering ``action`` has already spent."""
    states: list[BudgetState] = []
    for rule, key in budget_keys(action, budgets):
        since = at - timedelta(seconds=rule.interval_seconds)
        states.append(BudgetState(rule=rule, key=key, spent=await ledger.spent(key, since=since)))
    return tuple(states)


async def spend_budgets(
    action: ProposedAction,
    budgets: Sequence[BudgetRule],
    *,
    at: datetime,
    ledger: SpendLedger,
) -> tuple[str, ...]:
    """Record one spend against every budget covering ``action``, and name them."""
    keys = tuple(key for _, key in budget_keys(action, budgets))
    for key in keys:
        await ledger.record(key, at=at, action_id=action.action_id)
    return keys


__all__ = [
    "AuditSpendLedger",
    "InMemorySpendLedger",
    "SpendLedger",
    "budget_keys",
    "read_budgets",
    "spend_budgets",
]
