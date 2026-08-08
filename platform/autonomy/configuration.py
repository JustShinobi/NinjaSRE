"""Turning a resolved configuration into the policy set a decision reads.

Autonomy is configured through the hierarchical configuration service and not
beside it. That is the whole reason this module is thin: the merge, the locked
fields, the approval-gated fields, the provenance and the audit line all already
exist there and are already tested, and a second configuration mechanism for the
most safety-critical setting in the system would be the wrong place to save
effort.

So the schema does the validating and this does the translating. A team's
effective configuration is a `PoliciesConfig`; what resolution needs is a
`PolicySet`; the two are the same facts in two shapes, and keeping the shapes
separate is what stops the resolver depending on pydantic and the configuration
depending on the resolver.

**Nothing here validates.** Everything it could reject was rejected at save
time, by the section's own validators, using the same closed sets this module
reads. Re-checking here would be a second opinion that could differ from the
first, and the only way to find out would be an action that did not happen.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from platform.autonomy.bounds import BudgetRule, FreezeWindow
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicyRule, PolicySet, TimedOverride
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.config_service.schema.policies import (
    AutonomyBudgetSettings,
    AutonomyOverrideSettings,
    AutonomyRuleSettings,
    AutonomyScopeSettings,
    FreezeWindowSettings,
    PoliciesConfig,
)


def policy_set_of(policies: PoliciesConfig, *, source: str = "") -> PolicySet:
    """Return the policy set a team's resolved configuration describes.

    ``source`` is the node the configuration resolved at. It goes on every rule
    so an explanation can say *where* a rule came from — which, in a four-level
    hierarchy with a deep merge behind it, is most of the answer to "why is this
    the level".
    """
    settings = policies.autonomy
    return PolicySet(
        dry_run=settings.dry_run,
        rules=tuple(_rule(entry, source) for entry in settings.rules),
        freezes=tuple(_freeze(entry) for entry in settings.freezes),
        budgets=tuple(_budget(entry) for entry in settings.budgets),
        overrides=tuple(_override(entry) for entry in settings.overrides),
    )


def _scope(settings: AutonomyScopeSettings) -> PolicyScope:
    """Return the scope ``settings`` names."""
    return PolicyScope(
        kind=ScopeKind(settings.kind),
        team_node_id=settings.team_node_id,
        resource_kind=settings.resource_kind,
        resource_id=settings.resource_id,
        capability=settings.capability,
        labels={label.name: label.value for label in settings.labels},
    )


def _rule(settings: AutonomyRuleSettings, source: str) -> PolicyRule:
    """Return the rule ``settings`` states."""
    return PolicyRule(
        scope=_scope(settings.scope),
        level=AutonomyLevel(settings.level),
        risk_bound=RiskClass(settings.risk_bound),
        dry_run=settings.dry_run,
        source=source,
    )


def _freeze(settings: FreezeWindowSettings) -> FreezeWindow:
    """Return the freeze window ``settings`` declares."""
    return FreezeWindow(
        name=settings.name,
        scope=_scope(settings.scope),
        start=time.fromisoformat(settings.start),
        end=time.fromisoformat(settings.end),
        timezone=settings.timezone,
        reason=settings.reason,
    )


def _budget(settings: AutonomyBudgetSettings) -> BudgetRule:
    """Return the budget ``settings`` declares."""
    return BudgetRule(
        name=settings.name,
        counted_by=settings.counted_by,
        limit=settings.limit,
        interval_seconds=settings.interval_seconds,
        scope=_scope(settings.scope) if settings.scope is not None else None,
    )


def _override(settings: AutonomyOverrideSettings) -> TimedOverride:
    """Return the time-bounded override ``settings`` grants."""
    return TimedOverride(
        name=settings.name,
        scope=_scope(settings.scope),
        level=AutonomyLevel(settings.level),
        expires_at=datetime.fromisoformat(settings.expires_at),
        risk_bound=RiskClass(settings.risk_bound),
        granted_by=settings.granted_by,
        reason=settings.reason,
    )


def settings_of(policies: PolicySet) -> dict[str, Any]:
    """Return the configuration patch ``policies`` would be written back as.

    The other direction, and the one an import uses: a reviewed document becomes
    a configuration write, which is what makes it inherit the locks and the
    approval gate instead of going round them.

    Built from the typed values rather than from ``to_document`` because the two
    shapes differ in one place — a scope's labels are a mapping in the document
    and a list of pairs in the configuration, since a section with
    operator-chosen keys is not a closed schema.
    """
    return {
        "dry_run": policies.dry_run,
        "rules": [_rule_settings(rule) for rule in policies.rules],
        "freezes": [_freeze_settings(window) for window in policies.freezes],
        "budgets": [_budget_settings(budget) for budget in policies.budgets],
        "overrides": [_override_settings(override) for override in policies.overrides],
    }


def _scope_settings(scope: PolicyScope) -> dict[str, Any]:
    """Return one scope in the configuration's shape."""
    written: dict[str, Any] = {"kind": scope.kind.value}
    for name in ("team_node_id", "resource_kind", "resource_id", "capability"):
        value = getattr(scope, name)
        if value:
            written[name] = value
    if scope.labels:
        written["labels"] = [
            {"name": name, "value": value} for name, value in sorted(scope.labels.items())
        ]
    return written


def _rule_settings(rule: PolicyRule) -> dict[str, Any]:
    """Return one rule in the configuration's shape."""
    return {
        "scope": _scope_settings(rule.scope),
        "level": rule.level.value,
        "risk_bound": rule.risk_bound.value,
        "dry_run": rule.dry_run,
    }


def _freeze_settings(window: FreezeWindow) -> dict[str, Any]:
    """Return one freeze window in the configuration's shape."""
    return {
        "name": window.name,
        "scope": _scope_settings(window.scope),
        "start": window.start.isoformat("minutes"),
        "end": window.end.isoformat("minutes"),
        "timezone": window.timezone,
        "reason": window.reason,
    }


def _budget_settings(budget: BudgetRule) -> dict[str, Any]:
    """Return one budget in the configuration's shape."""
    written: dict[str, Any] = {
        "name": budget.name,
        "counted_by": budget.counted_by,
        "limit": budget.limit,
        "interval_seconds": budget.interval_seconds,
    }
    if budget.scope is not None:
        written["scope"] = _scope_settings(budget.scope)
    return written


def _override_settings(override: TimedOverride) -> dict[str, Any]:
    """Return one override in the configuration's shape."""
    return {
        "name": override.name,
        "scope": _scope_settings(override.scope),
        "level": override.level.value,
        "risk_bound": override.risk_bound.value,
        "expires_at": override.expires_at.isoformat(),
        "granted_by": override.granted_by,
        "reason": override.reason,
    }


__all__ = [
    "policy_set_of",
    "settings_of",
]
