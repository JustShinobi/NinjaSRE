"""Opt-in autonomy, the conditions on it, and the switch that overrides both.

Three modules, in the order the gate consults them — which is the reverse of the
order they were designed in, and deliberately so. The kill switch is checked
first because it has to override everything, including an approval that has
already been granted. Only then is the allow-list consulted, and only then are
its conditions evaluated against the moment the action would actually run.

Nothing here decides that an action is *safe*. What it decides is that a team
has explicitly said this action type, on these targets, in this window, within
this rate, does not need to interrupt a person — and that the statement still
holds now rather than when it was written.
"""

from __future__ import annotations

from platform.remediation.autonomy.allow_list import (
    AllowList,
    AllowListEntry,
    Condition,
    ConditionContext,
    EnvironmentIs,
    MaximumBlastRadius,
    RateLimit,
    TargetPattern,
    TimeWindow,
)
from platform.remediation.autonomy.evaluation import (
    ConditionEvaluator,
    Evaluation,
    ExecutionLedger,
)
from platform.remediation.autonomy.kill_switch import (
    ORGANISATION_SCOPE,
    KillSwitch,
    KillSwitchState,
)

__all__ = [
    "ORGANISATION_SCOPE",
    "AllowList",
    "AllowListEntry",
    "Condition",
    "ConditionContext",
    "ConditionEvaluator",
    "EnvironmentIs",
    "Evaluation",
    "ExecutionLedger",
    "KillSwitch",
    "KillSwitchState",
    "MaximumBlastRadius",
    "RateLimit",
    "TargetPattern",
    "TimeWindow",
]
