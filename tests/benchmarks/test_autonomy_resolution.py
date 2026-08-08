"""What one autonomy resolution costs against a thousand configured rules.

Resolution sits in front of every action a deployment takes, so its cost is paid
on the path where a human is already waiting. The number in
``config.constants.autonomy`` is a budget rather than a measurement of the
current implementation: a failure here means resolution has started doing
something quadratic in the rule count, not that CI was busy.

A thousand rules is the configured ceiling, which is far more than any real
deployment carries. Measuring at the ceiling is the point — a policy set that
grows to it must still decide in the same order of time as one with six rules
in it.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from config.constants.autonomy import (
    AUTONOMY_RESOLUTION_BUDGET_SECONDS,
    MAX_AUTONOMY_RULES,
)
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicyRule, PolicySet
from platform.autonomy.resolution import resolve
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.autonomy.subjects import ProposedAction, Subject

pytestmark = [pytest.mark.benchmark]

#: How many resolutions each measurement averages over. Enough that one
#: scheduling hiccup does not decide the result.
REPEATS = 200

AT = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)


def a_thousand_rules() -> PolicySet:
    """Return the largest policy set a deployment may configure.

    Every scope kind is represented and only one rule names the resource the
    benchmark asks about, so the walk really does look at all thousand.
    """
    rules: list[PolicyRule] = [
        PolicyRule(
            scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
            level=AutonomyLevel.PROPOSE_ONLY,
        )
    ]
    for index in range(MAX_AUTONOMY_RULES - 2):
        rules.append(
            PolicyRule(
                scope=PolicyScope(kind=ScopeKind.RESOURCE, resource_id=f"ct-{index:04d}"),
                level=AutonomyLevel.ACT_ON_LOW_RISK,
            )
        )
    rules.append(
        PolicyRule(
            scope=PolicyScope(
                kind=ScopeKind.CAPABILITY_RESOURCE,
                capability="restart_workload",
                resource_id="ct-target",
            ),
            level=AutonomyLevel.ACT_AND_REPORT,
        )
    )
    return PolicySet(rules=tuple(rules))


def an_action() -> ProposedAction:
    """Return the action every measurement resolves."""
    return ProposedAction(
        action_id="act-benchmark",
        capability="restart_workload",
        subjects=(Subject(resource_id="ct-target", kind="container", team_node_id="platform"),),
        risk_class=RiskClass.LOW,
        has_rollback_plan=True,
        requester="ada",
        team_node_id="platform",
    )


def test_resolution_stays_inside_its_budget_at_a_thousand_rules() -> None:
    policies = a_thousand_rules()
    action = an_action()
    assert len(policies.rules) == MAX_AUTONOMY_RULES

    # Warm the interpreter's caches so the first call does not carry import cost.
    assert resolve(action, policies, at=AT).level is AutonomyLevel.ACT_AND_REPORT

    started = time.perf_counter()
    for _ in range(REPEATS):
        resolve(action, policies, at=AT)
    each = (time.perf_counter() - started) / REPEATS

    assert each < AUTONOMY_RESOLUTION_BUDGET_SECONDS, (
        f"one resolution over {MAX_AUTONOMY_RULES} rules took {each * 1000:.2f}ms, above the "
        f"{AUTONOMY_RESOLUTION_BUDGET_SECONDS * 1000:.0f}ms budget"
    )


def test_the_cost_grows_with_the_rule_count_and_not_faster() -> None:
    """A linear walk stays linear. Quadratic growth is what this catches."""
    action = an_action()

    def cost(rules: int) -> float:
        policies = PolicySet(
            rules=tuple(
                PolicyRule(
                    scope=PolicyScope(kind=ScopeKind.RESOURCE, resource_id=f"ct-{index:05d}"),
                    level=AutonomyLevel.ACT_ON_LOW_RISK,
                )
                for index in range(rules)
            )
        )
        resolve(action, policies, at=AT)
        started = time.perf_counter()
        for _ in range(REPEATS):
            resolve(action, policies, at=AT)
        return (time.perf_counter() - started) / REPEATS

    small = cost(100)
    large = cost(1_000)

    # Ten times the rules, generously under a hundred times the cost. A
    # quadratic implementation would be around a hundred; a linear one is around
    # ten, and the slack is for a machine that is doing something else.
    assert large < small * 40, (
        f"100 rules cost {small * 1000:.3f}ms and 1,000 cost {large * 1000:.3f}ms — "
        f"resolution is growing faster than the rule count"
    )
