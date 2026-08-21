"""The operations every surface performs on a deployment's posture.

The API, the CLI and the console all ask the same six questions — what is the
policy, change it, what would that change do, why was this decided, what is
bounding us, and stop everything — and they ask them here rather than each
composing a configuration service, a resolver and a history reader. Three
compositions is three chances for one of them to skip the audit line.

**Reading and writing both go through the configuration service.** A write is a
configuration write, so it inherits the merge, the locked fields, the approval
gate, the provenance and the audit row. That is the whole reason the policy
lives there, and a service that wrote directly to storage would be the thing
that reason exists to prevent.

**The kill switch does not.** It is deliberately not a policy setting: a policy
change goes through validation and possibly an approval, which needs a reviewer,
which is the thing an operator does not have during the ten seconds in which the
switch matters. It is held in the process and read at the moment of the check.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from config.constants.autonomy import (
    DEFAULT_AUTONOMY_OVERRIDE_SECONDS,
    MAX_AUTONOMY_PREVIEW_ACTIONS,
)
from platform.autonomy.bounds import BudgetState, EmergencyStop, NoStop
from platform.autonomy.budget import InMemorySpendLedger, SpendLedger, read_budgets
from platform.autonomy.configuration import policy_set_of, settings_of
from platform.autonomy.decision import AutonomyGate, Decision
from platform.autonomy.history import DecisionHistory
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet, TimedOverride, override_expiring
from platform.autonomy.preview import PolicyChange, preview_change
from platform.autonomy.scopes import PolicyScope
from platform.autonomy.subjects import ProposedAction
from platform.config_service.service import ConfigService
from platform.persistence.ports import ActorKind, PersistenceGateway, TenantScope

#: Where the policy sits in a node's settings. One path, named once, because a
#: second spelling of it is a write the read never sees.
AUTONOMY_SETTINGS_PATH: tuple[str, str] = ("policies", "autonomy")


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class BoundsView:
    """What is currently bounding this node, whatever its levels say."""

    stopped: bool
    stop_reason: str
    freezes: tuple[Mapping[str, Any], ...]
    budgets: tuple[Mapping[str, Any], ...]
    overrides: tuple[Mapping[str, Any], ...]
    expired_overrides: tuple[str, ...]


@dataclass(slots=True)
class AutonomyService:
    """Read, change, preview and explain one deployment's posture."""

    gateway: PersistenceGateway
    scope: TenantScope
    config: ConfigService
    stop: EmergencyStop = field(default_factory=NoStop)
    ledger: SpendLedger = field(default_factory=InMemorySpendLedger)
    clock: Callable[[], datetime] = field(default=_utc_now)

    async def policy(self, node_id: str) -> PolicySet:
        """Return the policy set ``node_id`` resolves to, inheritance applied."""
        effective = await self.config.resolve(node_id)
        return policy_set_of(effective.config.policies, source=effective.node_id)

    async def save(
        self,
        node_id: str,
        policies: PolicySet,
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
    ) -> PolicySet:
        """Write ``policies`` to ``node_id``'s own settings and return what it resolves to.

        ``replace`` is not used: the patch is the whole autonomy section, and a
        merge onto a list is a replacement anyway. What a merge preserves is
        everything *else* under ``policies``, which a caller changing autonomy
        did not ask to touch.
        """
        section, name = AUTONOMY_SETTINGS_PATH
        await self.config.set_settings(
            node_id,
            {section: {name: settings_of(policies)}},
            actor_id=actor_id,
            actor_kind=actor_kind,
        )
        return await self.policy(node_id)

    async def preview(
        self,
        node_id: str,
        proposed: PolicySet,
        *,
        since: datetime | None = None,
        limit: int = MAX_AUTONOMY_PREVIEW_ACTIONS,
    ) -> PolicyChange:
        """Return what ``proposed`` would have decided differently, and store nothing."""
        current = await self.policy(node_id)
        history = await DecisionHistory(gateway=self.gateway, scope=self.scope).recent(
            since=since, limit=limit
        )
        return preview_change(current, proposed, history, limit=limit)

    async def explain(self, node_id: str, action: ProposedAction) -> Decision:
        """Return what would happen to ``action``, having performed nothing.

        The ``why`` command, the console's badge, and the gate's own first step
        are this one call. A surface that computed its own answer would be a
        second resolver, and the day it drifted an operator would be shown a
        level the deployment does not act on.
        """
        return await self.gate(await self.policy(node_id)).decide(action)

    def gate(self, policies: PolicySet) -> AutonomyGate:
        """Return the gate this service's collaborators make over ``policies``."""
        return AutonomyGate(
            policies=policies,
            stop=self.stop,
            ledger=self.ledger,
            clock=self.clock,
        )

    async def set_dry_run(
        self,
        node_id: str,
        enabled: bool,
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
    ) -> PolicySet:
        """Turn simulation on or off for everything ``node_id`` resolves."""
        section, name = AUTONOMY_SETTINGS_PATH
        await self.config.set_settings(
            node_id,
            {section: {name: {"dry_run": enabled}}},
            actor_id=actor_id,
            actor_kind=actor_kind,
        )
        return await self.policy(node_id)

    async def grant_override(
        self,
        node_id: str,
        *,
        name: str,
        scope: PolicyScope,
        level: AutonomyLevel,
        seconds: float = DEFAULT_AUTONOMY_OVERRIDE_SECONDS,
        reason: str = "",
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
    ) -> TimedOverride:
        """Raise autonomy in ``scope`` until it expires, and record who did it."""
        granted = override_expiring(
            name=name,
            scope=scope,
            level=level,
            granted_at=self.clock(),
            seconds=seconds,
            granted_by=actor_id,
            reason=reason,
        )
        current = await self.own_policy(node_id)
        kept = tuple(held for held in current.overrides if held.name != name)
        await self.save(
            node_id,
            _with_overrides(current, (*kept, granted)),
            actor_id=actor_id,
            actor_kind=actor_kind,
        )
        return granted

    async def own_policy(self, node_id: str) -> PolicySet:
        """Return the policy ``node_id`` itself declares, inheritance not applied.

        What a write is built on. Editing the *resolved* set would silently copy
        every inherited rule into the node's own document, which is how a
        hierarchy stops being one.
        """
        document = await self.config.document(node_id)
        section, name = AUTONOMY_SETTINGS_PATH
        settings = document.settings.get(section, {})
        own = settings.get(name, {}) if isinstance(settings, Mapping) else {}
        from platform.config_service.schema.policies import (
            AutonomyPolicySettings,
            PoliciesConfig,
        )

        return policy_set_of(
            PoliciesConfig(autonomy=AutonomyPolicySettings.model_validate(own or {})),
            source=node_id,
        )

    async def bounds(self, node_id: str, team_node_id: str | None = None) -> BoundsView:
        """Return everything currently bounding ``node_id``, and what has expired."""
        policies = await self.policy(node_id)
        at = self.clock()
        return BoundsView(
            stopped=self.stop.is_engaged(team_node_id=team_node_id),
            stop_reason=self.stop.describe_for(team_node_id=team_node_id),
            freezes=tuple(window.to_record() for window in policies.freezes),
            budgets=tuple(budget.to_record() for budget in policies.budgets),
            overrides=tuple(
                override.to_record() for override in policies.overrides if override.active_at(at)
            ),
            expired_overrides=tuple(override.name for override in policies.expired(at)),
        )

    async def spent(self, node_id: str, action: ProposedAction) -> tuple[BudgetState, ...]:
        """Return what each budget covering ``action`` has already spent."""
        policies = await self.policy(node_id)
        return await read_budgets(action, policies.budgets, at=self.clock(), ledger=self.ledger)

    def since(self, days: float) -> datetime:
        """Return the instant ``days`` ago, for a preview over a recorded window."""
        return self.clock() - timedelta(days=days)


def _with_overrides(policies: PolicySet, overrides: tuple[TimedOverride, ...]) -> PolicySet:
    """Return ``policies`` carrying ``overrides`` in place of its own."""
    return PolicySet(
        rules=policies.rules,
        freezes=policies.freezes,
        budgets=policies.budgets,
        overrides=overrides,
        dry_run=policies.dry_run,
    )


__all__ = [
    "AUTONOMY_SETTINGS_PATH",
    "AutonomyService",
    "BoundsView",
]
