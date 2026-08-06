"""The one place a write is stopped, and the order the checks happen in.

Gating lives at the runtime hook rather than inside each capability, and that is
the property the whole feature rests on: it applies under any runtime, to every
tool, including the one somebody adds next month without reading this file. A
check inside seven appliers is seven checks, and the eighth capability does not
have one.

The order is the specification, not an implementation detail:

1. **The kill switch**, because it overrides everything including an approval
   already granted. An action approved thirty seconds ago is exactly the kind
   this has to catch — the person who approved it did so before whatever made an
   operator reach for the switch.
2. **The classification**, from the capability's declared side-effect level
   against the organisation's policy. A capability with no declaration is a
   write, always; absence is never permission.
3. **The allow-list**, evaluated against *now*.
4. **The approval**, raised through feature 015's machinery, with the loop
   suspended while a human decides.
5. **The plan**, persisted before anything executes.
6. **The conditions again**, at execution time, because an approval can sit
   pending while the blast radius changes underneath it.

**A refusal is a value, not an exception.** ``Deny`` goes back to the model
classified ``APPROVAL_REQUIRED`` or ``PERMISSION_DENIED``, and the difference
matters: one is worth waiting for and the other is not. The investigation
continues either way — an agent that stopped because a mitigation was declined
would have thrown away the diagnosis it had already reached.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.security import DEFAULT_GATED_SIDE_EFFECT_LEVELS
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import ALLOW, Deny, HookPoint, HookResult, ToolContext
from core.capability.metadata import SideEffectLevel
from core.capability.result import CapabilityErrorClass
from core.llm.types import ToolCall
from platform.approvals.models import ChangeState, PendingChange
from platform.approvals.policy import SecurityPolicy
from platform.observability.logging import get_logger
from platform.remediation.autonomy.evaluation import ConditionEvaluator
from platform.remediation.autonomy.kill_switch import KillSwitch
from platform.remediation.errors import (
    ConditionsNotMet,
    KillSwitchEngaged,
    NoRollbackPlan,
    RemediationError,
)
from platform.remediation.execution import Execution, RemediationExecutor
from platform.remediation.models import (
    RemediationAction,
    RemediationEvidence,
    RemediationTarget,
    utc_now,
)
from platform.remediation.request import RequestBuilder
from platform.remediation.rollback.generator import RollbackWaiver

_LOG = get_logger(__name__)

#: The name the hook registers under, so an ablation can unregister exactly this
#: one and a trace can say which hook refused a call.
PRE_TOOL_USE_HOOK = "remediation.pre_tool_use"

#: Guardrails run first, at -100. This runs after them and before anything else,
#: because a call a guardrail is going to block outright should not first cost a
#: human the interruption of being asked about it.
HOOK_ORDER = -50

#: Which arguments name the thing being changed, in the order they are tried.
#: A convention rather than a schema, because the seven remediation capabilities
#: take different argument names for the same idea and a mapping per capability
#: is a table that drifts from the capabilities it describes.
TARGET_ARGUMENTS = ("workload", "target", "node", "service", "flag", "cache")
ENVIRONMENT_ARGUMENT = "environment"


@dataclass(frozen=True, slots=True)
class GatingPolicy:
    """Which side-effect levels this organisation requires approval for.

    A policy that names none gets the default — everything above
    ``read_sensitive`` — rather than gating nothing. An unconfigured deployment
    has not decided to run production writes unattended; it has not decided
    anything, and the safe reading of silence is the strict one.
    """

    gated_levels: tuple[str, ...] = DEFAULT_GATED_SIDE_EFFECT_LEVELS

    @classmethod
    def of_policy(cls, policy: SecurityPolicy) -> GatingPolicy:
        """Return the gating an organisation's security policy describes."""
        declared = policy.require_approval_for_side_effect_levels
        return cls(gated_levels=tuple(declared) if declared else DEFAULT_GATED_SIDE_EFFECT_LEVELS)

    def gates(self, level: SideEffectLevel) -> bool:
        """Return whether an action at ``level`` needs approval or an allow-list.

        Two conditions, and the second is not redundant. The policy decides
        which levels an organisation gates; the scale decides which levels are
        writes at all. An organisation cannot un-gate a write by leaving it off
        its list, because Article III is not an organisational preference.
        """
        return level.value in self.gated_levels or level.needs_approval


@dataclass(frozen=True, slots=True)
class RunContext:
    """Who this run acts for, and which team's rules apply to it.

    Bound when the hook is registered rather than read out of the session,
    because a hook that reconstructed the principal per call would reconstruct
    it differently on the one path nobody tested — and that path is the one
    somebody will ask about afterwards.
    """

    requester: str
    team_node_id: str | None = None
    run_id: str = ""
    environment: str = ""


@runtime_checkable
class DecisionWaiter(Protocol):
    """Suspends the loop until a human decides, or until the window closes.

    A protocol because how a deployment waits is its own decision — polling the
    store, a queue, an in-process event — and because the thing this package
    needs to guarantee is only that it does not proceed until there is an answer
    or the answer is "nobody said anything in time".
    """

    async def wait(self, change_id: str, *, timeout_seconds: float) -> PendingChange:
        """Return the change once it is decided, or as expired when it is not."""


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """What the gate decided about one call, and why.

    Kept as a value beside the ``Deny`` the loop sees, because the trace, the
    audit trail, and the operator's "why did nothing happen" all want the reason
    in a form richer than one sentence aimed at a model.
    """

    capability: str
    permitted: bool
    autonomous: bool = False
    approval_id: str = ""
    reason: str = ""
    classification: CapabilityErrorClass = CapabilityErrorClass.APPROVAL_REQUIRED
    execution: Execution | None = None

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the run trace carries."""
        return {
            "capability": self.capability,
            "permitted": self.permitted,
            "autonomous": self.autonomous,
            "approval_id": self.approval_id,
            "reason": self.reason,
            "classification": self.classification.value,
        }


@dataclass(slots=True)
class RemediationGate:
    """The ``pre_tool_use`` binding that stops every unapproved production write.

    Holds the six collaborators the ordering needs and no state of its own. In
    particular it holds no memory of a previous decision: an approval is
    per-action and per-session and never generalises to a later action, and a
    gate that cached one would be the mechanism by which it did.
    """

    requests: RequestBuilder
    executor: RemediationExecutor
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    evaluator: ConditionEvaluator | None = None
    waiter: DecisionWaiter | None = None
    policy: GatingPolicy = field(default_factory=GatingPolicy)
    run: RunContext = field(default_factory=lambda: RunContext(requester=""))
    waiver: RollbackWaiver | None = None
    approval_timeout_seconds: float = 0.0
    clock: Callable[[], datetime] = field(default=utc_now)
    identifiers: Callable[[], str] = field(default=lambda: str(uuid.uuid4()))

    def register(self, hooks: HookRegistry) -> HookRegistry:
        """Attach the gate to ``hooks`` and return it."""
        hooks.register(
            HookPoint.PRE_TOOL_USE,
            self.pre_tool_use,
            name=PRE_TOOL_USE_HOOK,
            order=HOOK_ORDER,
        )
        return hooks

    async def pre_tool_use(self, call: ToolCall, context: ToolContext) -> HookResult:
        """Return whether ``call`` may run, having run it when it may.

        The gate executes rather than merely permitting, which is unusual for a
        hook and is the point: an action that ran through this path had its plan
        persisted, its conditions re-evaluated, and its result verified, and
        there is no arrangement of ``Allow`` that could promise any of that.
        A permitted action therefore comes back as a denial that carries its
        own outcome — the loop does not call the tool a second time.
        """
        level = context.registered.metadata.side_effect_level
        if not self.policy.gates(level):
            return ALLOW

        action = self.action_for(call, context)
        outcome = await self.decide(action)
        return _as_hook_result(outcome)

    async def decide(self, action: RemediationAction) -> GateOutcome:
        """Return what happens to ``action``, running it when it is permitted.

        Every entry point goes through here — the loop's hook, a console button,
        an operator's CLI — so "no write executes without an approval or a
        matching allow-list entry" is a property of one function rather than a
        rule three call sites each honour.
        """
        try:
            self.kill_switch.check(team_node_id=action.team_node_id)
        except KillSwitchEngaged as stopped:
            return GateOutcome(
                capability=action.capability,
                permitted=False,
                reason=str(stopped),
                classification=CapabilityErrorClass.PERMISSION_DENIED,
            )

        try:
            autonomous = await self._autonomous(action)
            if autonomous:
                return await self._execute(action, approval_id="", autonomous=True)
            return await self._through_approval(action)
        except RemediationError as refused:
            return GateOutcome(
                capability=action.capability,
                permitted=False,
                reason=str(refused),
                classification=_classification_of(refused),
            )

    async def _autonomous(self, action: RemediationAction) -> bool:
        """Return whether an allow-list entry permits this action right now."""
        if self.evaluator is None:
            return False
        radius = await self.requests.blast_radius(action)
        evaluation = self.evaluator.evaluate(
            action, at=self.clock(), blast_radius=radius.count if radius.known else _UNKNOWN_RADIUS
        )
        if evaluation.permitted:
            return True
        evaluation.raise_if_refused()
        return False

    async def _through_approval(self, action: RemediationAction) -> GateOutcome:
        """Queue the approval, suspend until it is decided, and execute if it was."""
        request = await self.requests.queue(action, waiver=self.waiver)
        if self.waiter is None or not request.change_id:
            return GateOutcome(
                capability=action.capability,
                permitted=False,
                approval_id=request.change_id,
                reason=(
                    f"{action.capability} on {action.target} is waiting on a human "
                    f"approval. The investigation continues without it."
                ),
            )

        decided = await self.waiter.wait(
            request.change_id, timeout_seconds=self._timeout(request.change_id)
        )
        if decided.state is not ChangeState.APPROVED:
            return GateOutcome(
                capability=action.capability,
                permitted=False,
                approval_id=request.change_id,
                reason=_refusal_reason(action, decided),
            )

        return await self._execute(action, approval_id=request.change_id, autonomous=False)

    async def _execute(
        self,
        action: RemediationAction,
        *,
        approval_id: str,
        autonomous: bool,
    ) -> GateOutcome:
        """Build the plan against fresh state and run the action through the executor."""
        request = await self.requests.build(action, waiver=self.waiver)
        radius = await self.requests.blast_radius(action)
        execution = await self.executor.execute(
            action,
            plan=request.plan,
            before=request.before,
            approval_id=approval_id,
            autonomous=autonomous,
            blast_radius=radius.count if radius.known else _UNKNOWN_RADIUS,
        )
        return GateOutcome(
            capability=action.capability,
            permitted=True,
            autonomous=autonomous,
            approval_id=approval_id,
            reason=_outcome_reason(execution),
            execution=execution,
        )

    def _timeout(self, change_id: str) -> float:
        """Return how long the loop waits for a decision on ``change_id``."""
        del change_id
        if self.approval_timeout_seconds > 0:
            return self.approval_timeout_seconds
        from config.constants.security import REMEDIATION_APPROVAL_EXPIRY_SECONDS

        return float(REMEDIATION_APPROVAL_EXPIRY_SECONDS)

    def action_for(self, call: ToolCall, context: ToolContext) -> RemediationAction:
        """Return the action ``call`` proposes, as this package's own value.

        The target comes from the arguments by convention rather than from a
        per-capability table, because seven capabilities spelling one idea seven
        ways is a table that drifts. An action whose target cannot be named
        still becomes an action — with the capability as its target — because a
        write nobody could name is a write that must still be gated.
        """
        arguments: Mapping[str, Any] = dict(call.arguments)
        return RemediationAction(
            action_id=self.identifiers(),
            capability=context.capability,
            target=RemediationTarget(
                identifier=_target_of(arguments, fallback=context.capability),
                environment=str(arguments.get(ENVIRONMENT_ARGUMENT, self.run.environment)),
                node_id=self.run.team_node_id,
            ),
            side_effect_level=context.registered.metadata.side_effect_level,
            requester=self.run.requester or context.session.id,
            intent=context.registered.metadata.approval_reason,
            arguments=arguments,
            evidence=_evidence_of(context),
            run_id=self.run.run_id or context.session.id,
            team_node_id=self.run.team_node_id,
        )


#: What a blast radius the graph could not compute counts as. Deliberately above
#: any sane ceiling: an unknown radius must fail a maximum-blast-radius
#: condition rather than pass it, because the alternative is autonomy granted on
#: the strength of an extension nobody installed.
_UNKNOWN_RADIUS = 1_000_000


def _target_of(arguments: Mapping[str, Any], *, fallback: str) -> str:
    """Return the identifier of the thing being changed, or the capability's name."""
    for name in TARGET_ARGUMENTS:
        value = arguments.get(name)
        if isinstance(value, str) and value:
            return value
    return fallback


def _evidence_of(context: ToolContext) -> tuple[RemediationEvidence, ...]:
    """Return the observations this run cited, most recent first.

    Cited entries first and only a few of them. A reviewer reads three lines of
    "here is what made the agent propose this"; a reviewer shown forty reads
    none of them, and the request degrades into the prompt people click.
    """
    entries = [entry for entry in context.session.evidence if entry.cited]
    entries.extend(entry for entry in context.session.evidence if not entry.cited)
    return tuple(
        RemediationEvidence(summary=entry.summary, reference=entry.reference)
        for entry in entries[:_LISTED_EVIDENCE]
    )


_LISTED_EVIDENCE = 5


def _classification_of(error: RemediationError) -> CapabilityErrorClass:
    """Return how a refusal is classified for the model.

    ``APPROVAL_REQUIRED`` says "a human is looking at it" and
    ``PERMISSION_DENIED`` says "do not retry this". Conflating them is how an
    agent ends up either spinning on a permanent refusal or giving up on a
    temporary one.
    """
    if isinstance(error, KillSwitchEngaged | NoRollbackPlan):
        return CapabilityErrorClass.PERMISSION_DENIED
    if isinstance(error, ConditionsNotMet):
        return CapabilityErrorClass.APPROVAL_REQUIRED
    return CapabilityErrorClass.APPROVAL_REQUIRED


def _refusal_reason(action: RemediationAction, decided: PendingChange) -> str:
    """Return the sentence the model reads when a human said no or nobody did."""
    if decided.state is ChangeState.EXPIRED:
        return (
            f"The approval for {action.capability} on {action.target} expired without a "
            f"decision, so the action did not run. Continue without it."
        )
    reason = decided.rejection_reason
    trailer = f" Reason given: {reason}" if reason else ""
    return (
        f"{action.capability} on {action.target} was declined by a human, so it did not "
        f"run.{trailer} Continue the investigation without it."
    )


def _outcome_reason(execution: Execution) -> str:
    """Return what the model is told about an action that did run."""
    record = execution.record
    verdict = (
        record.verification.describe()
        if record.verification is not None
        else "It was not verified."
    )
    changed = ", ".join(record.changed_sub_targets) or "nothing"
    return (
        f"{record.capability} on {record.target} finished as {record.outcome.value}; it "
        f"changed {changed}. {verdict} It can be rolled back with plan {record.plan_id}."
    )


def _as_hook_result(outcome: GateOutcome) -> HookResult:
    """Return what the loop does with a gate decision.

    Always a denial, including when the action ran. The loop's contract is that
    a hook may refuse a call or rewrite it and may not perform one, so an action
    the gate executed comes back as a refusal that carries the outcome — the
    model reads what happened and does not call the tool again. Allowing it
    through would run the change twice: once here, with a plan and a
    verification, and once unmediated.
    """
    return Deny(reason=outcome.reason, classification=outcome.classification)


__all__ = [
    "HOOK_ORDER",
    "PRE_TOOL_USE_HOOK",
    "TARGET_ARGUMENTS",
    "DecisionWaiter",
    "GateOutcome",
    "GatingPolicy",
    "RemediationGate",
    "RunContext",
]
