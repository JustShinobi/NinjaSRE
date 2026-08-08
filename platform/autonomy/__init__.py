"""How much the deployment may do without asking, decided in one place.

Every actuator asks this package the same question — may this action run right
now, and if not, why not — and no actuator may answer it for itself. That is the
whole of the design; everything else here is what makes the answer defensible.

``risk``
    The closed, ordered scale an action's danger is declared on, at the
    capability, at registration. Unclassified is the top of the scale.

``levels``
    The three postures: propose only, act on low risk, act and report. There is
    no fourth, and no expression language.

``policy``
    What an operator configures: rules at seven scopes, freeze windows, budgets,
    and time-bounded overrides. Expressed through the hierarchical configuration
    service, so merge, locks, required fields and approval gating are inherited
    rather than rebuilt. ``configuration`` is the translation between the two,
    and is imported directly rather than re-exported here — it reaches the
    configuration service, and most callers of this package do not.

``resolution``
    A pure function from an action, a policy set and a clock to a level *and its
    explanation* — every rule considered, which applied, which won, and why.
    Purity is what makes the decision matrix a unit test and the policy preview
    possible at all.

``bounds``
    The four gates no level overrides: the kill switch, freeze windows, action
    budgets, and the requirement that an action have a rollback plan. Evaluated
    after the level, never as part of it, because a bound expressed as a level is
    one some configuration can out-rank.

``decision``
    The single path from a proposed action to an execution. One function, and a
    structural test that fails when an actuator reaches execution without it.
"""

from __future__ import annotations

from platform.autonomy.bounds import (
    Bound,
    BoundOutcome,
    BudgetRule,
    EmergencyStop,
    FreezeWindow,
    NoStop,
    evaluate_bounds,
)
from platform.autonomy.budget import (
    AuditSpendLedger,
    InMemorySpendLedger,
    SpendLedger,
    budget_keys,
)
from platform.autonomy.decision import (
    Actuator,
    AutonomyGate,
    Decision,
    ExhaustionListener,
    Outcome,
)
from platform.autonomy.errors import MalformedPolicy
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import (
    PolicyRule,
    PolicyScope,
    PolicySet,
    ScopeKind,
    TimedOverride,
    policy_set_of_document,
)
from platform.autonomy.preview import PolicyChange, PreviewedAction, preview_change
from platform.autonomy.resolution import ConsideredRule, Resolution, resolve
from platform.autonomy.risk import RiskClass, risk_class_of
from platform.autonomy.subjects import ProposedAction, Subject

__all__ = [
    "Actuator",
    "AuditSpendLedger",
    "AutonomyGate",
    "AutonomyLevel",
    "Bound",
    "BoundOutcome",
    "BudgetRule",
    "ConsideredRule",
    "Decision",
    "EmergencyStop",
    "ExhaustionListener",
    "FreezeWindow",
    "InMemorySpendLedger",
    "MalformedPolicy",
    "NoStop",
    "Outcome",
    "PolicyChange",
    "PolicyRule",
    "PolicyScope",
    "PolicySet",
    "PreviewedAction",
    "ProposedAction",
    "Resolution",
    "RiskClass",
    "ScopeKind",
    "SpendLedger",
    "Subject",
    "TimedOverride",
    "budget_keys",
    "evaluate_bounds",
    "policy_set_of_document",
    "preview_change",
    "resolve",
    "risk_class_of",
]
