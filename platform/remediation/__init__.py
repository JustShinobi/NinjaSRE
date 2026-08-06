"""Where the system is permitted to change production, and what stops it otherwise.

Read-only is the default. A write needs an explicit human approval *and* a
rollback plan recorded before execution. Autonomy is opt-in per action type,
scoped per team, conditional, and killable in one action. Nothing in this
package makes an action safe — what it does is make every step between "the
agent proposed it" and "production changed" something a person decided or a
person could have stopped.

What a caller reaches for:

``RemediationGate``
    The ``pre_tool_use`` binding. Every write goes through it, whatever runtime
    is driving the loop and whichever surface started the run.
``RequestBuilder``
    Turns a proposed action into what a human is shown: current state, blast
    radius, rollback plan, evidence.
``PlanFactory`` and ``RollbackExecutor``
    The undo — derived before the action, checked against the target before it
    is applied, loud when it fails.
``RemediationExecutor``
    The action itself: isolated, serialised per target, recorded per sub-target,
    verified by reading the result back.
``KillSwitch``, ``AllowList``, ``ConditionEvaluator``
    Opt-in autonomy and the switch above it.

The one ordering worth memorising, because everything else here follows from it:
kill switch, allow-list, approval, **plan persisted**, conditions re-evaluated,
execute, verify.
"""

from __future__ import annotations

from platform.remediation.audit import RemediationAuditor, TeamNotifier
from platform.remediation.autonomy import (
    AllowList,
    AllowListEntry,
    ConditionEvaluator,
    EnvironmentIs,
    Evaluation,
    KillSwitch,
    KillSwitchState,
    MaximumBlastRadius,
    RateLimit,
    TargetPattern,
    TimeWindow,
)
from platform.remediation.components import (
    ChangeApplier,
    ComponentRegistry,
    OutcomeVerifier,
    PlanGenerator,
    RemediationComponents,
    StateReader,
    registry_of,
)
from platform.remediation.errors import (
    ApprovalRefused,
    ConditionsNotMet,
    KillSwitchEngaged,
    NoRollbackPlan,
    RemediationError,
    RollbackFailed,
    RollbackTargetMismatch,
    RollbackWindowClosed,
    TargetLocked,
    UnknownRemediationCapability,
)
from platform.remediation.execution import (
    Execution,
    ExecutionEnvironment,
    RemediationApplier,
    RemediationExecutor,
    SandboxIsolation,
    TargetLocks,
)
from platform.remediation.gating import (
    DecisionWaiter,
    GateOutcome,
    GatingPolicy,
    RemediationGate,
    RunContext,
)
from platform.remediation.models import (
    Divergence,
    ExecutionOutcome,
    ExecutionRecord,
    RemediationAction,
    RemediationEvidence,
    RemediationTarget,
    RollbackPlan,
    RollbackStep,
    StateSnapshot,
    SubTargetResult,
    VerificationReport,
)
from platform.remediation.request import BlastRadius, RemediationRequest, RequestBuilder
from platform.remediation.rollback import (
    PlanFactory,
    RollbackExecutor,
    RollbackResult,
    RollbackWaiver,
    StepRunner,
)
from platform.remediation.verification import OutcomeVerification, divergences_between

__all__ = [
    "AllowList",
    "AllowListEntry",
    "ApprovalRefused",
    "BlastRadius",
    "ChangeApplier",
    "ComponentRegistry",
    "ConditionEvaluator",
    "ConditionsNotMet",
    "DecisionWaiter",
    "Divergence",
    "EnvironmentIs",
    "Evaluation",
    "Execution",
    "ExecutionEnvironment",
    "ExecutionOutcome",
    "ExecutionRecord",
    "GateOutcome",
    "GatingPolicy",
    "KillSwitch",
    "KillSwitchEngaged",
    "KillSwitchState",
    "MaximumBlastRadius",
    "NoRollbackPlan",
    "OutcomeVerification",
    "OutcomeVerifier",
    "PlanFactory",
    "PlanGenerator",
    "RateLimit",
    "RemediationAction",
    "RemediationApplier",
    "RemediationAuditor",
    "RemediationComponents",
    "RemediationError",
    "RemediationEvidence",
    "RemediationExecutor",
    "RemediationGate",
    "RemediationRequest",
    "RemediationTarget",
    "RequestBuilder",
    "RollbackExecutor",
    "RollbackFailed",
    "RollbackPlan",
    "RollbackResult",
    "RollbackStep",
    "RollbackTargetMismatch",
    "RollbackWaiver",
    "RollbackWindowClosed",
    "RunContext",
    "SandboxIsolation",
    "StateReader",
    "StateSnapshot",
    "StepRunner",
    "SubTargetResult",
    "TargetLocked",
    "TargetLocks",
    "TargetPattern",
    "TeamNotifier",
    "TimeWindow",
    "UnknownRemediationCapability",
    "VerificationReport",
    "divergences_between",
    "registry_of",
]
