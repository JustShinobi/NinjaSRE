"""In-memory resources, their health, their transitions, and what referenced them.

The interesting part is what this fake refuses to make easy. ``mark_absent``
takes a set of identifiers rather than a flag, so a test cannot spell "the sweep
failed" and "the sweep found nothing" the same way; and ``mark_stale`` never
touches ``absent_since``, so the bug the whole component exists to avoid cannot
be written here either.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from config.constants.estate import DEFAULT_TRANSITION_HISTORY
from platform.persistence.errors import RecordNotFound
from platform.persistence.fakes.state import TenantState, check_payload
from platform.persistence.ports.estate_repository import (
    EstateQuery,
    EstateSummary,
    HealthDerivation,
    HealthSignal,
    HealthTransition,
    ReferenceKind,
    Resource,
    ResourceHealth,
    ResourceReference,
    SweepRecord,
    check_estate_limit,
    check_maintenance_window,
    merged,
    transition_key,
)


@dataclass(slots=True)
class FakeEstateRepository:
    """The estate for one organisation."""

    org_id: str
    state: TenantState

    # --- The inventory --------------------------------------------------------

    async def upsert(self, resource: Resource) -> Resource:
        """Store ``resource``, merging it over any earlier record, and return it."""
        check_payload(resource.attributes, kind="resource attributes")
        stored = merged(self.state.resources.get(resource.resource_id), resource)
        self.state.resources[resource.resource_id] = stored
        return stored

    async def get(self, resource_id: str) -> Resource | None:
        """Return the resource with ``resource_id``, or ``None``."""
        return self.state.resources.get(resource_id)

    async def by_native_id(self, *, source: str, native_id: str) -> Resource | None:
        """Return the present resource ``source`` calls ``native_id``, or ``None``."""
        for resource in sorted(self.state.resources.values(), key=lambda found: found.resource_id):
            if (
                resource.source == source
                and resource.native_id == native_id
                and resource.absent_since is None
            ):
                return resource
        return None

    async def by_correlation_key(self, *, kind: str, correlation_key: str) -> Resource | None:
        """Return the present resource carrying ``correlation_key``, or ``None``."""
        if not correlation_key:
            return None
        for resource in sorted(self.state.resources.values(), key=lambda found: found.resource_id):
            if (
                resource.kind == kind
                and resource.correlation_key == correlation_key
                and resource.absent_since is None
            ):
                return resource
        return None

    async def query(self, query: EstateQuery) -> tuple[Resource, ...]:
        """Return the resources matching ``query``, by identifier."""
        limit = check_estate_limit(query.limit)
        matched = [
            resource for resource in self.state.resources.values() if _matches(resource, query)
        ]
        matched.sort(key=lambda resource: resource.resource_id)
        return tuple(matched[:limit])

    async def summarise(self, *, now: datetime) -> EstateSummary:
        """Return the whole estate's counts, with freshness applied at ``now``."""
        by_kind: dict[str, int] = {}
        by_health: dict[str, int] = {}
        by_source: dict[str, int] = {}
        problems = maintenance = absent = total = 0

        for resource in self.state.resources.values():
            state = resource.reported_health(now)
            by_health[state.value] = by_health.get(state.value, 0) + 1
            if state is ResourceHealth.ABSENT:
                absent += 1
                continue
            total += 1
            by_kind[resource.kind] = by_kind.get(resource.kind, 0) + 1
            by_source[resource.source] = by_source.get(resource.source, 0) + 1
            if state is ResourceHealth.MAINTENANCE:
                maintenance += 1
            if state.is_problem:
                problems += 1

        return EstateSummary(
            total=total,
            captured_at=now,
            by_kind=dict(sorted(by_kind.items())),
            by_health=dict(sorted(by_health.items())),
            by_source=dict(sorted(by_source.items())),
            problems=problems,
            maintenance=maintenance,
            absent=absent,
        )

    # --- What a sweep concluded ----------------------------------------------

    async def mark_absent(
        self,
        *,
        source: str,
        seen_ids: frozenset[str],
        at: datetime,
        since: datetime | None = None,
    ) -> tuple[str, ...]:
        """Mark ``source``'s resources absent unless seen in or since this sweep."""
        marked: list[str] = []
        for resource_id, resource in sorted(self.state.resources.items()):
            if resource.source != source or resource_id in seen_ids:
                continue
            if resource.absent_since is not None:
                continue
            if (
                since is not None
                and resource.last_seen_at is not None
                and resource.last_seen_at >= since
            ):
                continue
            self.state.resources[resource_id] = replace(resource, absent_since=at)
            self._record_transition(
                resource_id,
                state=ResourceHealth.ABSENT,
                previous=resource.health,
                at=at,
                rule="absent_from_successful_sweep",
            )
            marked.append(resource_id)
        return tuple(marked)

    async def mark_stale(
        self,
        *,
        source: str,
        at: datetime,
        reason: str,
    ) -> tuple[str, ...]:
        """Mark ``source``'s present resources stale, recording ``reason``."""
        marked: list[str] = []
        for resource_id, resource in sorted(self.state.resources.items()):
            if resource.source != source or resource.absent_since is not None:
                continue
            derivation = HealthDerivation(
                state=ResourceHealth.STALE,
                rule="discovery_sweep_failed",
                derived_at=at,
                raw_status=resource.derivation.raw_status if resource.derivation else "",
                explanation=f"the {source} discovery sweep failed: {reason}",
            )
            previous = resource.health
            self.state.resources[resource_id] = replace(
                resource, health=ResourceHealth.STALE, derivation=derivation
            )
            if previous is not ResourceHealth.STALE:
                self._record_transition(
                    resource_id,
                    state=ResourceHealth.STALE,
                    previous=previous,
                    at=at,
                    rule=derivation.rule,
                )
            marked.append(resource_id)
        return tuple(marked)

    async def record_sweep(self, record: SweepRecord) -> SweepRecord:
        """Store ``record``, replacing any earlier one with the same id."""
        self.state.sweeps[record.sweep_id] = record
        return record

    async def last_sweep(self, source: str) -> SweepRecord | None:
        """Return ``source``'s most recently started sweep, or ``None``."""
        candidates = [record for record in self.state.sweeps.values() if record.source == source]
        if not candidates:
            return None
        return max(candidates, key=lambda record: (record.started_at, record.sweep_id))

    # --- Health ---------------------------------------------------------------

    async def record_health(
        self,
        resource_id: str,
        derivation: HealthDerivation,
    ) -> Resource:
        """Store ``derivation`` as ``resource_id``'s health and return the resource."""
        resource = self._require(resource_id)
        previous = resource.health
        updated = replace(resource, health=derivation.state, derivation=derivation)
        self.state.resources[resource_id] = updated

        # An unchanged state appends nothing. A sweep every fifteen minutes
        # would otherwise write ninety-six identical rows a day per resource,
        # and a history nobody can read is a history nobody keeps.
        if previous is not derivation.state or not self._history(resource_id):
            self._record_transition(
                resource_id,
                state=derivation.state,
                previous=previous,
                at=derivation.derived_at,
                rule=derivation.rule,
                signal=derivation.signals[0] if derivation.signals else None,
            )
        return updated

    async def transitions(
        self,
        resource_id: str,
        *,
        limit: int = DEFAULT_TRANSITION_HISTORY,
    ) -> tuple[HealthTransition, ...]:
        """Return ``resource_id``'s state changes, most recent first."""
        check_estate_limit(limit)
        history = sorted(
            self._history(resource_id),
            key=lambda entry: (entry.occurred_at, entry.transition_id),
            reverse=True,
        )
        return tuple(history[:limit])

    async def set_maintenance(
        self,
        resource_id: str,
        *,
        until: datetime,
        reason: str,
        at: datetime,
    ) -> Resource:
        """Put ``resource_id`` into maintenance until ``until`` and return it."""
        resource = self._require(resource_id)
        check_maintenance_window(until=until, at=at)
        updated = replace(resource, maintenance_until=until, maintenance_reason=reason)
        self.state.resources[resource_id] = updated
        self._record_transition(
            resource_id,
            state=ResourceHealth.MAINTENANCE,
            previous=resource.health,
            at=at,
            rule="maintenance_window_opened",
        )
        return updated

    async def clear_maintenance(self, resource_id: str, *, at: datetime) -> Resource:
        """End ``resource_id``'s maintenance window now and return it."""
        resource = self._require(resource_id)
        updated = replace(resource, maintenance_until=None, maintenance_reason="")
        self.state.resources[resource_id] = updated
        if resource.maintenance_until is not None:
            self._record_transition(
                resource_id,
                state=resource.health,
                previous=ResourceHealth.MAINTENANCE,
                at=at,
                rule="maintenance_window_closed",
            )
        return updated

    # --- What referenced it ---------------------------------------------------

    async def link(self, reference: ResourceReference) -> ResourceReference:
        """Record that a run or an incident touched a resource. Idempotent."""
        key = (reference.resource_id, reference.reference_kind.value, reference.reference_id)
        self.state.resource_references.setdefault(key, reference)
        return self.state.resource_references[key]

    async def references(
        self,
        resource_id: str,
        *,
        reference_kind: ReferenceKind | None = None,
        limit: int = DEFAULT_TRANSITION_HISTORY,
    ) -> tuple[ResourceReference, ...]:
        """Return what referenced ``resource_id``, most recent first."""
        check_estate_limit(limit)
        found = [
            reference
            for reference in self.state.resource_references.values()
            if reference.resource_id == resource_id
            and (reference_kind is None or reference.reference_kind is reference_kind)
        ]
        found.sort(key=lambda entry: (entry.recorded_at, entry.reference_id), reverse=True)
        return tuple(found[:limit])

    # --- internals ------------------------------------------------------------

    def _require(self, resource_id: str) -> Resource:
        resource = self.state.resources.get(resource_id)
        if resource is None:
            raise RecordNotFound(kind="resource", identifier=resource_id)
        return resource

    def _history(self, resource_id: str) -> list[HealthTransition]:
        return [
            entry
            for entry in self.state.health_transitions.values()
            if entry.resource_id == resource_id
        ]

    def _record_transition(
        self,
        resource_id: str,
        *,
        state: ResourceHealth,
        previous: ResourceHealth | None,
        at: datetime,
        rule: str,
        signal: HealthSignal | None = None,
    ) -> None:
        transition_id = transition_key(resource_id, state, at)
        self.state.health_transitions[transition_id] = HealthTransition(
            transition_id=transition_id,
            resource_id=resource_id,
            state=state,
            occurred_at=at,
            previous_state=previous,
            rule=rule,
            signal=signal,
        )


def _matches(resource: Resource, query: EstateQuery) -> bool:
    """Return whether ``resource`` satisfies every filter ``query`` declares."""
    if not query.include_absent and resource.absent_since is not None:
        return False
    if query.kinds and resource.kind not in query.kinds:
        return False
    if query.sources and resource.source not in query.sources:
        return False
    if query.labels and not set(query.labels) <= set(resource.labels):
        return False
    if query.team_node_id is not None and resource.team_node_id != query.team_node_id:
        return False
    if query.parent_id is not None and resource.parent_id != query.parent_id:
        return False
    if query.health and resource.health not in query.health:
        return False
    if query.observed_before is not None:
        derived = resource.derivation.derived_at if resource.derivation else None
        if derived is None or derived >= query.observed_before:
            return False
    return True


def purge_estate_history(state: TenantState, cutoff: datetime) -> int:
    """Delete transitions and references older than ``cutoff`` and return the count.

    A module function rather than a repository method, because retention runs on
    the *system* unit of work and has no tenant scope to open one with. The
    existing sweeper calls it per tenant, which is what keeps estate history on
    the deployment's one retention path rather than on a second of its own.
    """
    stale_transitions = [
        key for key, entry in state.health_transitions.items() if entry.occurred_at < cutoff
    ]
    stale_references = [
        key for key, entry in state.resource_references.items() if entry.recorded_at < cutoff
    ]
    for key in stale_transitions:
        del state.health_transitions[key]
    for reference_key in stale_references:
        del state.resource_references[reference_key]
    return len(stale_transitions) + len(stale_references)


__all__ = ["FakeEstateRepository", "purge_estate_history"]
