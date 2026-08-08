"""The one path from a proposed action to an execution.

Everything above this module proposes; nothing above it performs. An actuator is
handed to the gate rather than called by its owner, so "no write happens without
a policy decision" is a property of one function instead of a rule that seven
call sites each honour — and the eighth, added next month, does not.

The order is the specification:

1. **Resolve the level**, from the policy set, purely, with its explanation.
2. **Evaluate the bounds** — the stop, the freeze windows, the budgets, the
   rollback requirement — after the level and never as part of it.
3. **Decide**, from the level, the risk class and the bound that applied.
4. **Act**, or not, through the actuator the caller supplied.
5. **Record**, whichever way it went, with the whole explanation.

Steps 2 and 3 are separate because the bounds do not all mean the same thing. A
kill switch and a freeze window *refuse*: no human can approve past them, and an
action inside one is simply not happening. A spent budget and a missing rollback
plan *downgrade*: the action is fine, it just is not one the deployment gets to
take unattended. Collapsing them would either make a freeze approvable or make a
spent budget an outage.

**A dry run is decided exactly as a real one and then not performed.** The
outcome is computed first and only then turned into a simulation, so what the
simulation reports is what would have happened rather than a second code path's
opinion about it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.autonomy import (
    AUTONOMY_DECISION_APPROVE,
    AUTONOMY_DECISION_EXECUTE,
    AUTONOMY_DECISION_PROPOSE,
    AUTONOMY_DECISION_REFUSE,
    AUTONOMY_DECISION_SIMULATE,
)
from platform.autonomy.audit import DecisionAuditor
from platform.autonomy.bounds import (
    Bound,
    BoundOutcome,
    EmergencyStop,
    NoStop,
    evaluate_bounds,
)
from platform.autonomy.budget import InMemorySpendLedger, SpendLedger, read_budgets, spend_budgets
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import NOTHING_CONFIGURED, PolicySet
from platform.autonomy.resolution import Resolution, resolve
from platform.autonomy.subjects import ProposedAction
from platform.observability.logging import get_logger

_LOG = get_logger(__name__)


class Outcome(StrEnum):
    """What happens to one proposed action."""

    EXECUTE = AUTONOMY_DECISION_EXECUTE
    SIMULATE = AUTONOMY_DECISION_SIMULATE
    PROPOSE = AUTONOMY_DECISION_PROPOSE
    APPROVE = AUTONOMY_DECISION_APPROVE
    REFUSE = AUTONOMY_DECISION_REFUSE


#: The bounds that refuse outright. No configuration and no human approves past
#: one: an action inside a freeze is not happening, and the point of a stop is
#: that it does not need an inventory first.
REFUSING_BOUNDS: frozenset[Bound] = frozenset({Bound.KILL_SWITCH, Bound.FREEZE})


@runtime_checkable
class Actuator(Protocol):
    """Whatever actually performs an action, once something has permitted it.

    A protocol, and the gate is its only caller. What performs a change is the
    remediation layer's business; what decides whether it may is this package's,
    and the two are kept apart so the decision can be tested exhaustively without
    anything that could touch an estate.
    """

    async def perform(self, action: ProposedAction) -> Any:
        """Perform ``action`` and return whatever the caller needs of the result."""


@runtime_checkable
class ExhaustionListener(Protocol):
    """Whatever a deployment wants told when a budget runs out.

    A protocol rather than an incident, a page or a chat message, because which
    of those a deployment wants is its own decision — and because the obligation
    this expresses is only that *something* is told. A budget that quietly
    stopped the deployment doing what it was configured to do is the one
    refusal nothing else here would say out loud: every individual action still
    gets an approval, and the pattern is invisible until somebody adds it up.
    """

    async def budget_exhausted(
        self, action: ProposedAction, *, budgets: Sequence[str], reason: str
    ) -> None:
        """Raise attention that ``budgets`` are spent and actions are now queuing."""


@dataclass(frozen=True, slots=True)
class Decision:
    """What happened to one action, and the whole of why.

    Frozen and complete. This is what the audit trail stores, what the API
    returns, and what the console shows beside a proposal *before* anybody acts —
    three renderings of one value rather than three descriptions of one event.
    """

    action: ProposedAction
    resolution: Resolution
    outcome: Outcome
    reason: str
    bound: Bound | None = None
    executed: bool = False
    result: Any = None
    budgets_spent: tuple[str, ...] = ()

    @property
    def permitted(self) -> bool:
        """Return whether the deployment was allowed to act on this unattended."""
        return self.outcome in (Outcome.EXECUTE, Outcome.SIMULATE)

    @property
    def needs_human(self) -> bool:
        """Return whether a person has to decide before anything happens."""
        return self.outcome in (Outcome.PROPOSE, Outcome.APPROVE)

    @property
    def simulated(self) -> bool:
        """Return whether this was decided and then deliberately not performed."""
        return self.outcome is Outcome.SIMULATE

    def describe(self) -> str:
        """Return the sentence a surface, a refusal and a notification all show."""
        return self.reason

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the API returns and the trace carries."""
        return {
            "action": self.action.to_record(),
            "decision": self.outcome.value,
            "reason": self.reason,
            "refused_by": self.bound.value if self.bound is not None else "",
            "executed": self.executed,
            "simulated": self.simulated,
            "budgets_spent": list(self.budgets_spent),
            "resolution": self.resolution.to_record(),
        }


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(slots=True)
class AutonomyGate:
    """The single path: resolve, bound, decide, act, record.

    Holds the policy set, the stop, the ledger and the auditor, and no memory of
    a previous decision. A decision is per-action and never generalises to a
    later one; a gate that cached one would be the mechanism by which it did.
    """

    policies: PolicySet = NOTHING_CONFIGURED
    stop: EmergencyStop = field(default_factory=NoStop)
    ledger: SpendLedger = field(default_factory=InMemorySpendLedger)
    auditor: DecisionAuditor | None = None
    #: Told when a budget runs out. Optional, and the warning log is not: a
    #: deployment that has wired nothing still leaves the record somewhere.
    exhaustion: ExhaustionListener | None = None
    clock: Callable[[], datetime] = field(default=_utc_now)

    async def decide(self, action: ProposedAction) -> Decision:
        """Return what should happen to ``action``, having performed nothing.

        The half a console calls to show an operator what *would* happen before
        they press anything, and the half ``run`` calls before it acts. One
        function, so what the console shows and what the gate does cannot differ.
        """
        at = self.clock()
        resolution = resolve(action, self.policies, at=at)
        budgets = await read_budgets(action, self.policies.budgets, at=at, ledger=self.ledger)
        bounds = evaluate_bounds(
            action,
            at=at,
            stop=self.stop,
            freezes=self.policies.freezes,
            budgets=budgets,
        )
        outcome, reason = _outcome_of(action, resolution, bounds)
        if bounds.bound is Bound.BUDGET:
            await self._exhausted(action, bounds)
        return Decision(
            action=action,
            resolution=resolution,
            outcome=outcome,
            reason=reason,
            bound=bounds.bound,
        )

    async def _exhausted(self, action: ProposedAction, bounds: BoundOutcome) -> None:
        """Say, out loud, that a budget has stopped the deployment acting.

        Raised at the decision rather than at the spend, because the moment
        worth telling somebody about is the first action that could not run —
        not the one that used the last of it, which looked like every other
        successful action at the time.
        """
        _LOG.warning(
            "autonomy.budget_exhausted",
            action_id=action.action_id,
            capability=action.capability,
            budgets=list(bounds.exhausted),
            reason=bounds.reason,
        )
        if self.exhaustion is None:
            return
        await self.exhaustion.budget_exhausted(
            action, budgets=bounds.exhausted, reason=bounds.reason
        )

    async def run(self, action: ProposedAction, actuator: Actuator) -> Decision:
        """Decide ``action``, perform it if it may run, and record either way.

        The only path to an execution in this deployment. ``actuator.perform`` is
        called from here and from nowhere else, and a structural test fails the
        build when something else calls one.
        """
        decision = await self.decide(action)

        if decision.outcome is Outcome.EXECUTE:
            result = await actuator.perform(action)
            decision = _with_execution(decision, result=result, spent=await self.spend(action))
        elif decision.outcome is Outcome.SIMULATE:
            _LOG.info(
                "autonomy.simulated",
                action_id=action.action_id,
                capability=action.capability,
                would_have=Outcome.EXECUTE.value,
            )

        await self.record(decision)
        return decision

    async def spend(self, action: ProposedAction) -> tuple[str, ...]:
        """Record one spend against every budget covering ``action``, and name them.

        Public because ``run`` is not the only caller: a deployment whose
        actuator lives behind its own machinery decides here and performs there,
        and the budget has to be spent by whoever actually made the change.
        Spending happens *after* the change, never at the point of permission —
        a permitted action that something further down refused would otherwise
        make the limit bound attempts rather than changes.
        """
        return await spend_budgets(
            action, self.policies.budgets, at=self.clock(), ledger=self.ledger
        )

    async def record(self, decision: Decision) -> None:
        """Write ``decision`` to the audit trail, whichever way it went."""
        if self.auditor is None:
            _LOG.info(
                "autonomy.unaudited_decision",
                action_id=decision.action.action_id,
                decision=decision.outcome.value,
            )
            return
        await self.auditor.decided(decision)

    async def expire_overrides(self) -> tuple[str, ...]:
        """Record every override that has run out, and return their names.

        Expiry is already in effect — resolution simply stops seeing an override
        past its instant — so this announces rather than enforces. That ordering
        is deliberate: an override must not outlive its window because a worker
        was down.
        """
        expired = self.policies.expired(self.clock())
        if self.auditor is not None:
            for override in expired:
                await self.auditor.override_expired(override)
        return tuple(override.name for override in expired)


def _outcome_of(
    action: ProposedAction, resolution: Resolution, bounds: BoundOutcome
) -> tuple[Outcome, str]:
    """Return what happens to ``action``, and the sentence that explains it."""
    if bounds.refused and bounds.bound in REFUSING_BOUNDS:
        return Outcome.REFUSE, (
            f"{action.describe()} was refused because {bounds.reason}. No autonomy level "
            f"and no approval overrides this."
        )

    level = resolution.level
    if bounds.refused:
        # A downgrading bound: the action is fine, it is just not one this
        # deployment takes unattended right now.
        outcome = Outcome.APPROVE if level.acts else Outcome.PROPOSE
        return outcome, (
            f"{action.describe()} needs a person because {bounds.reason}. {resolution.reason}"
        )

    if level is AutonomyLevel.PROPOSE_ONLY:
        return Outcome.PROPOSE, (
            f"{action.describe()} is proposed rather than run. {resolution.reason} A person "
            f"can run it with: {action.runnable()}"
        )

    if level is AutonomyLevel.ACT_ON_LOW_RISK and not action.risk_class.at_or_below(
        resolution.risk_bound
    ):
        return Outcome.APPROVE, (
            f"{action.describe()} is {action.risk_class.value} risk, above the configured "
            f"bound of {resolution.risk_bound.value}, so it needs an approval. "
            f"{resolution.reason}"
        )

    if resolution.dry_run:
        return Outcome.SIMULATE, (
            f"{action.describe()} would have run unattended, and was simulated instead "
            f"because this scope is in dry-run mode. {resolution.reason} The operation it "
            f"would have performed: {action.runnable()}"
        )

    return Outcome.EXECUTE, (f"{action.describe()} ran without asking. {resolution.reason}")


def _with_execution(decision: Decision, *, result: Any, spent: Sequence[str]) -> Decision:
    """Return ``decision`` stamped with what the actuator returned."""
    return Decision(
        action=decision.action,
        resolution=decision.resolution,
        outcome=decision.outcome,
        reason=decision.reason,
        bound=decision.bound,
        executed=True,
        result=result,
        budgets_spent=tuple(spent),
    )


__all__ = [
    "REFUSING_BOUNDS",
    "Actuator",
    "ExhaustionListener",
    "AutonomyGate",
    "Decision",
    "Outcome",
]
