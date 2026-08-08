"""What every surface asks the estate, and the one place freshness is applied.

The repository stores what was observed. This applies what the deployment knows
on top of it — the per-kind freshness interval, the parent rollup rule, the
maintenance window — and it is deliberately the *only* place that does. A
console that applied freshness itself and a CLI that did not would show an
operator two different estates and both would be defensible.

Three things this owns and nothing else does.

**Freshness comes from the kind.** ``kinds.freshness_for`` decides how long an
observation of a node stands versus one of a nightly backup job, and
``Resource.reported_health`` applies it at read time. A resource past its
interval reports ``stale`` rather than its last known state — which is the
difference between "the guest was healthy an hour ago" and "the guest is
healthy".

**Rollup is computed on read, not stored.** A parent's state depends on its
children's *current* reported states, and those change with the clock even when
nothing was written. Storing a rolled-up state would mean a node that was
degraded at 09:00 still saying so at 11:00 after every guest recovered and
nothing swept.

**Maintenance is bounded and audited by the transition log.** Opening a window
records a transition; so does closing one. An operator asking "who suppressed
this and when" reads the same history that answers "when did it start failing".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from config.constants.estate import DEFAULT_TRANSITION_HISTORY
from platform.estate.health.rollup import RollupRule, roll_up, rule_for
from platform.estate.kinds import KindRegistry
from platform.persistence.ports.estate_repository import (
    EstateQuery,
    EstateSummary,
    HealthDerivation,
    HealthTransition,
    ReferenceKind,
    Resource,
    ResourceHealth,
    ResourceReference,
)
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope


@dataclass(frozen=True, slots=True)
class ResourceView:
    """A resource as a surface shows it: what it is, and what it is doing now.

    ``health`` is the *reported* state — absence, maintenance and freshness
    already applied — and ``stored_health`` is what was last derived. Both are
    present because an operator who sees ``stale`` needs to be able to ask what
    it was stale *at*, and a view that only carried one of them would make that
    a second request.
    """

    resource: Resource
    health: ResourceHealth
    stored_health: ResourceHealth
    is_stale: bool
    freshness_seconds: int
    rollup_rule: RollupRule
    children: int = 0
    derivation: HealthDerivation | None = None
    #: The parent's display name, when the same read produced it. Resolved from
    #: what came back rather than by a lookup per row: a listing is what a table
    #: pages through, and one round trip per row is how a hundred-row page
    #: becomes a hundred queries. Empty when the parent is outside the page,
    #: which a surface renders as "no parent shown" rather than as "no parent".
    parent_name: str = ""

    @property
    def explanation(self) -> str:
        """Return why this resource is in the state it is in, in one sentence."""
        if self.health is ResourceHealth.ABSENT:
            return "This resource was not reported by a successful sweep, so it is gone."
        if self.health is ResourceHealth.MAINTENANCE:
            reason = self.resource.maintenance_reason or "no reason was given"
            return f"An operator put this into maintenance: {reason}."
        if self.is_stale:
            return (
                f"The last observation is older than this kind's {self.freshness_seconds}s "
                f"freshness interval, so its state is reported as stale rather than as what "
                f"it was."
            )
        return (
            self.derivation.explanation
            if self.derivation is not None
            else ("Nothing has been observed about this resource, so its state is unknown.")
        )


@dataclass(frozen=True, slots=True)
class ResourceDetail:
    """Everything one resource's page needs, in one read."""

    view: ResourceView
    transitions: tuple[HealthTransition, ...] = ()
    references: tuple[ResourceReference, ...] = ()
    children: tuple[ResourceView, ...] = ()
    parent: ResourceView | None = None


@dataclass(slots=True)
class EstateService:
    """The estate as every surface sees it.

    Holds the store and the kinds. Not a repository: everything here is a read
    the repository cannot answer alone, because answering it needs to know what
    kinds exist and what their intervals are.
    """

    gateway: PersistenceGateway
    kinds: KindRegistry = field(default_factory=KindRegistry)

    # --- Reads ----------------------------------------------------------------

    async def query(
        self,
        scope: TenantScope,
        query: EstateQuery,
        *,
        now: datetime,
    ) -> tuple[ResourceView, ...]:
        """Return the resources matching ``query``, with freshness applied."""
        async with self.gateway.begin(scope) as uow:
            found = await uow.estate.query(query)
        names = {resource.resource_id: resource.display_name for resource in found}
        return tuple([self._view(resource, now=now, parent_names=names) for resource in found])

    async def summarise(self, scope: TenantScope, *, now: datetime) -> EstateSummary:
        """Return the estate in the numbers a dashboard tile shows."""
        async with self.gateway.begin(scope) as uow:
            return await uow.estate.summarise(now=now)

    async def detail(
        self,
        scope: TenantScope,
        resource_id: str,
        *,
        now: datetime,
        history: int = DEFAULT_TRANSITION_HISTORY,
    ) -> ResourceDetail | None:
        """Return everything one resource's page needs, or ``None``.

        Acceptance scenario 6 in one call: the current state, the recent state
        changes, the incidents that referenced it and the runs that touched it,
        plus the children whose health it accounts for. Four round trips would
        be four chances for a screen to render half of them.
        """
        async with self.gateway.begin(scope) as uow:
            resource = await uow.estate.get(resource_id)
            if resource is None:
                return None
            children = await uow.estate.query(
                EstateQuery(parent_id=resource_id, include_absent=False, limit=200)
            )
            parent = (
                await uow.estate.get(resource.parent_id) if resource.parent_id is not None else None
            )
            transitions = await uow.estate.transitions(resource_id, limit=history)
            references = await uow.estate.references(resource_id, limit=history)

        return ResourceDetail(
            view=self._view(
                resource,
                now=now,
                children=children,
                parent_names=(
                    {parent.resource_id: parent.display_name} if parent is not None else {}
                ),
            ),
            transitions=transitions,
            references=references,
            children=tuple([self._view(child, now=now) for child in children]),
            parent=self._view(parent, now=now) if parent is not None else None,
        )

    async def references_for(
        self,
        scope: TenantScope,
        resource_id: str,
        *,
        reference_kind: ReferenceKind | None = None,
        limit: int = DEFAULT_TRANSITION_HISTORY,
    ) -> tuple[ResourceReference, ...]:
        """Return the runs and incidents that touched ``resource_id``."""
        async with self.gateway.begin(scope) as uow:
            return await uow.estate.references(
                resource_id, reference_kind=reference_kind, limit=limit
            )

    # --- Writes ---------------------------------------------------------------

    async def enter_maintenance(
        self,
        scope: TenantScope,
        resource_id: str,
        *,
        until: datetime,
        reason: str,
        at: datetime,
    ) -> ResourceView:
        """Put a resource into maintenance and return it as it now reads."""
        async with self.gateway.begin(scope) as uow:
            updated = await uow.estate.set_maintenance(
                resource_id, until=until, reason=reason, at=at
            )
        return self._view(updated, now=at)

    async def leave_maintenance(
        self,
        scope: TenantScope,
        resource_id: str,
        *,
        at: datetime,
    ) -> ResourceView:
        """End a maintenance window and return the resource as it now reads."""
        async with self.gateway.begin(scope) as uow:
            updated = await uow.estate.clear_maintenance(resource_id, at=at)
        return self._view(updated, now=at)

    async def link(
        self,
        scope: TenantScope,
        reference: ResourceReference,
    ) -> ResourceReference:
        """Record that a run or an incident touched a resource."""
        async with self.gateway.begin(scope) as uow:
            return await uow.estate.link(reference)

    async def apply_rollups(
        self,
        scope: TenantScope,
        *,
        now: datetime,
        parent_kinds: Sequence[str] = (),
    ) -> tuple[str, ...]:
        """Recompute and store every aggregating parent's state, and return the ids.

        Stored as well as computed, and the two are not in tension: reads
        compute the rollup so an operator never sees a stale aggregate, and this
        stores it so a *query by health* can find a degraded node without
        loading the whole estate. The stored value is a materialisation, and the
        derivation it carries names the rule that produced it.
        """
        kinds = tuple(parent_kinds) or tuple(
            kind.name for kind in self.kinds.all() if rule_for(kind.name) is not RollupRule.OWN_ONLY
        )
        if not kinds:
            return ()

        updated: list[str] = []
        async with self.gateway.begin(scope) as uow:
            parents = await uow.estate.query(EstateQuery(kinds=kinds, limit=500))
            for parent in parents:
                children = await uow.estate.query(
                    EstateQuery(parent_id=parent.resource_id, limit=500)
                )
                derivation = roll_up(parent, list(children), now=now)
                if parent.derivation is not None and derivation.state is parent.health:
                    continue
                await uow.estate.record_health(parent.resource_id, derivation)
                updated.append(parent.resource_id)
        return tuple(updated)

    # --- internals ------------------------------------------------------------

    def _view(
        self,
        resource: Resource,
        *,
        now: datetime,
        children: Sequence[Resource] = (),
        parent_names: Mapping[str, str] | None = None,
    ) -> ResourceView:
        """Return ``resource`` with this deployment's freshness and rules applied."""
        interval = self.kinds.freshness_for(resource.kind)
        rule = rule_for(resource.kind)
        rolled = (
            roll_up(resource, list(children), now=now, rule=rule)
            if children and rule is not RollupRule.OWN_ONLY
            else None
        )
        reported = resource.reported_health(now, freshness_seconds=interval)
        if rolled is not None and reported not in {
            ResourceHealth.ABSENT,
            ResourceHealth.MAINTENANCE,
            ResourceHealth.STALE,
        }:
            reported = rolled.state

        return ResourceView(
            resource=resource,
            health=reported,
            stored_health=resource.health,
            is_stale=resource.is_stale_at(now, freshness_seconds=interval),
            freshness_seconds=interval,
            rollup_rule=rule,
            children=len(children),
            derivation=rolled if rolled is not None else resource.derivation,
            parent_name=(parent_names or {}).get(resource.parent_id or "", ""),
        )


__all__ = ["EstateService", "ResourceDetail", "ResourceView"]
