"""The pieces every autonomy test builds an action or a policy set out of."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicyRule, PolicySet
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.autonomy.subjects import ProposedAction, Subject

#: A fixed instant well outside every window the suite declares, so a test that
#: does not care about the clock does not accidentally sit inside a freeze.
NOON: datetime = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)


def subject(
    resource_id: str = "ct-101",
    *,
    kind: str = "container",
    labels: Mapping[str, str] | None = None,
    team: str = "platform",
) -> Subject:
    """Return one resource an action could name."""
    return Subject(resource_id=resource_id, kind=kind, labels=dict(labels or {}), team_node_id=team)


def action(
    *,
    capability: str = "restart_workload",
    subjects: tuple[Subject, ...] = (),
    risk: RiskClass = RiskClass.LOW,
    rollback: bool = True,
    team: str = "platform",
    action_id: str = "act-1",
    operation: str = "",
) -> ProposedAction:
    """Return one proposed action, with a rollback plan unless told otherwise."""
    return ProposedAction(
        action_id=action_id,
        capability=capability,
        subjects=subjects or (subject(team=team),),
        risk_class=risk,
        has_rollback_plan=rollback,
        requester="ada",
        team_node_id=team,
        operation=operation,
    )


def rule(
    kind: ScopeKind,
    level: AutonomyLevel,
    *,
    risk_bound: RiskClass = RiskClass.LOW,
    dry_run: bool = False,
    **scope: Any,
) -> PolicyRule:
    """Return one policy rule at ``kind``'s scope."""
    return PolicyRule(
        scope=PolicyScope(kind=kind, **scope),
        level=level,
        risk_bound=risk_bound,
        dry_run=dry_run,
    )


@pytest.fixture
def nothing_configured() -> PolicySet:
    """Return the posture of a deployment that has decided nothing."""
    return PolicySet()
