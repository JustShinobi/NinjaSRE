"""The estate over PostgreSQL.

The derivation and the per-source contributions are stored as JSONB rather than
normalised into tables, and the reason is what queries them: nothing. No read in
this package joins on a signal or on a contributing integration — every read
that wants either wants the whole resource — so normalising would buy two joins
per row and a migration every time a signal grows a field.

What *is* a column is everything the estate is filtered by: kind, source,
health, parent, team, and the timestamps. Those have indexes, and the summary
reads them without touching the JSONB at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select

from config.constants.estate import DEFAULT_TRANSITION_HISTORY
from platform.persistence.errors import RecordNotFound
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
    ResourceSource,
    SweepOutcome,
    SweepRecord,
    check_estate_limit,
    check_maintenance_window,
    merged,
    transition_key,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_list,
    as_tuple,
    as_utc,
    translating,
)
from platform.persistence.postgres.repositories.run_trace_store import check_payload


def _signal_to_json(signal: HealthSignal) -> dict[str, Any]:
    return {
        "name": signal.name,
        "value": signal.value,
        "observed_at": signal.observed_at.isoformat(),
        "source": signal.source,
    }


def _signal_from_json(payload: Mapping[str, Any]) -> HealthSignal:
    return HealthSignal(
        name=str(payload["name"]),
        value=str(payload["value"]),
        observed_at=datetime.fromisoformat(str(payload["observed_at"])),
        source=str(payload.get("source", "")),
    )


def _derivation_to_json(derivation: HealthDerivation) -> dict[str, Any]:
    return {
        "state": derivation.state.value,
        "rule": derivation.rule,
        "derived_at": derivation.derived_at.isoformat(),
        "signals": [_signal_to_json(signal) for signal in derivation.signals],
        "raw_status": derivation.raw_status,
        "explanation": derivation.explanation,
    }


def _derivation_from_json(payload: Mapping[str, Any] | None) -> HealthDerivation | None:
    if not payload:
        return None
    return HealthDerivation(
        state=ResourceHealth(payload["state"]),
        rule=str(payload["rule"]),
        derived_at=datetime.fromisoformat(str(payload["derived_at"])),
        signals=tuple(_signal_from_json(signal) for signal in payload.get("signals", [])),
        raw_status=str(payload.get("raw_status", "")),
        explanation=str(payload.get("explanation", "")),
    )


def _source_to_json(source: ResourceSource) -> dict[str, Any]:
    return {
        "integration": source.integration,
        "native_id": source.native_id,
        "display_name": source.display_name,
        "attributes": dict(source.attributes),
        "observed_at": source.observed_at.isoformat() if source.observed_at else None,
    }


def _source_from_json(payload: Mapping[str, Any]) -> ResourceSource:
    observed = payload.get("observed_at")
    return ResourceSource(
        integration=str(payload["integration"]),
        native_id=str(payload["native_id"]),
        display_name=str(payload.get("display_name", "")),
        attributes=dict(payload.get("attributes", {})),
        observed_at=datetime.fromisoformat(str(observed)) if observed else None,
    )


def _to_resource(row: models.EstateResource) -> Resource:
    return Resource(
        resource_id=row.resource_id,
        kind=row.kind,
        source=row.source,
        native_id=row.native_id,
        display_name=row.display_name,
        correlation_key=row.correlation_key,
        parent_id=row.parent_id,
        team_node_id=row.team_node_id,
        attributes=dict(row.attributes),
        labels=as_tuple(row.labels),
        sources=tuple(_source_from_json(entry) for entry in row.sources),
        health=ResourceHealth(row.health),
        derivation=_derivation_from_json(row.derivation),
        first_seen_at=as_utc(row.first_seen_at),
        last_seen_at=as_utc(row.last_seen_at),
        absent_since=as_utc(row.absent_since),
        maintenance_until=as_utc(row.maintenance_until),
        maintenance_reason=row.maintenance_reason,
    )


def _to_transition(row: models.HealthTransitionRow) -> HealthTransition:
    return HealthTransition(
        transition_id=row.transition_id,
        resource_id=row.resource_id,
        state=ResourceHealth(row.state),
        occurred_at=as_utc(row.occurred_at) or row.occurred_at,
        previous_state=ResourceHealth(row.previous_state) if row.previous_state else None,
        rule=row.rule,
        signal=_signal_from_json(row.signal) if row.signal else None,
    )


def _to_reference(row: models.ResourceReferenceRow) -> ResourceReference:
    return ResourceReference(
        resource_id=row.resource_id,
        reference_kind=ReferenceKind(row.reference_kind),
        reference_id=row.reference_id,
        recorded_at=as_utc(row.recorded_at) or row.recorded_at,
        summary=row.summary,
    )


def _to_sweep(row: models.DiscoverySweep) -> SweepRecord:
    return SweepRecord(
        sweep_id=row.sweep_id,
        source=row.source,
        started_at=as_utc(row.started_at) or row.started_at,
        outcome=SweepOutcome(row.outcome),
        completed_at=as_utc(row.completed_at),
        seen_count=row.seen_count,
        provider_calls=row.provider_calls,
        cursor=row.cursor,
        reason=row.reason,
        findings=dict(row.findings or {}),
    )


@dataclass(slots=True)
class PostgresEstateRepository(TenantBound):
    """The estate for one organisation."""

    # --- The inventory --------------------------------------------------------

    async def upsert(self, resource: Resource) -> Resource:
        """Store ``resource``, merging it over any earlier record, and return it."""
        check_payload(resource.attributes, kind="resource attributes")
        row = await self.session.get(models.EstateResource, (self.org_id, resource.resource_id))
        stored = merged(_to_resource(row) if row is not None else None, resource)

        if row is None:
            row = models.EstateResource(org_id=self.org_id, resource_id=stored.resource_id)
            self.session.add(row)

        row.kind = stored.kind
        row.source = stored.source
        row.native_id = stored.native_id
        row.display_name = stored.display_name
        row.correlation_key = stored.correlation_key
        row.parent_id = stored.parent_id
        row.team_node_id = stored.team_node_id
        row.attributes = dict(stored.attributes)
        row.labels = as_list(stored.labels)
        row.sources = [_source_to_json(entry) for entry in stored.sources]
        row.health = stored.health.value
        row.derivation = (
            _derivation_to_json(stored.derivation) if stored.derivation is not None else None
        )
        row.first_seen_at = stored.first_seen_at
        row.last_seen_at = stored.last_seen_at
        row.absent_since = stored.absent_since
        row.maintenance_until = stored.maintenance_until
        row.maintenance_reason = stored.maintenance_reason

        with translating(kind="resource", identifier=stored.resource_id):
            await self.session.flush()
        return stored

    async def get(self, resource_id: str) -> Resource | None:
        """Return the resource with ``resource_id``, or ``None``."""
        row = await self.session.get(models.EstateResource, (self.org_id, resource_id))
        return None if row is None else _to_resource(row)

    async def get_many(self, resource_ids: tuple[str, ...]) -> Mapping[str, Resource]:
        """Return the resources with these ids, keyed by id."""
        if not resource_ids:
            return {}
        statement = self._resources().where(models.EstateResource.resource_id.in_(resource_ids))
        rows = (await self.session.execute(statement)).scalars().all()
        return {row.resource_id: _to_resource(row) for row in rows}

    async def by_native_id(self, *, source: str, native_id: str) -> Resource | None:
        """Return the present resource ``source`` calls ``native_id``, or ``None``."""
        statement = self._resources().where(
            models.EstateResource.source == source,
            models.EstateResource.native_id == native_id,
            models.EstateResource.absent_since.is_(None),
        )
        row = (await self.session.execute(statement)).scalars().first()
        return None if row is None else _to_resource(row)

    async def by_correlation_key(self, *, kind: str, correlation_key: str) -> Resource | None:
        """Return the present resource carrying ``correlation_key``, or ``None``."""
        if not correlation_key:
            return None
        statement = (
            self._resources()
            .where(
                models.EstateResource.kind == kind,
                models.EstateResource.correlation_key == correlation_key,
                models.EstateResource.absent_since.is_(None),
            )
            .order_by(models.EstateResource.resource_id)
        )
        row = (await self.session.execute(statement)).scalars().first()
        return None if row is None else _to_resource(row)

    async def query(self, query: EstateQuery) -> tuple[Resource, ...]:
        """Return the resources matching ``query``, by identifier."""
        limit = check_estate_limit(query.limit)
        statement = self._filtered(query).order_by(models.EstateResource.resource_id).limit(limit)
        if query.after:
            statement = statement.where(models.EstateResource.resource_id > query.after)
        rows = (await self.session.execute(statement)).scalars().all()
        return tuple(_to_resource(row) for row in rows)

    async def summarise(self, *, now: datetime) -> EstateSummary:
        """Return the whole estate's counts, with freshness applied at ``now``."""
        # One pass, and the freshness overlay applied in Python rather than in
        # SQL. A CASE expression could compute it, and would then have to be
        # kept in step with ``Resource.reported_health`` — two spellings of one
        # precedence rule, which is the way an operator ends up shown a state no
        # code path could explain.
        rows = (await self.session.execute(self._resources())).scalars().all()

        by_kind: dict[str, int] = {}
        by_health: dict[str, int] = {}
        by_source: dict[str, int] = {}
        problems = maintenance = absent = total = 0

        for row in rows:
            resource = _to_resource(row)
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
        statement = (
            self._resources()
            .where(models.EstateResource.source == source)
            .where(models.EstateResource.absent_since.is_(None))
            .order_by(models.EstateResource.resource_id)
        )
        rows = (await self.session.execute(statement)).scalars().all()

        marked: list[str] = []
        for row in rows:
            if row.resource_id in seen_ids:
                continue
            last_seen = as_utc(row.last_seen_at)
            if since is not None and last_seen is not None and last_seen >= since:
                continue
            previous = ResourceHealth(row.health)
            row.absent_since = at
            await self._append_transition(
                row.resource_id,
                state=ResourceHealth.ABSENT,
                previous=previous,
                at=at,
                rule="absent_from_successful_sweep",
            )
            marked.append(row.resource_id)

        await self.session.flush()
        return tuple(marked)

    async def mark_stale(
        self,
        *,
        source: str,
        at: datetime,
        reason: str,
    ) -> tuple[str, ...]:
        """Mark ``source``'s present resources stale, recording ``reason``."""
        statement = (
            self._resources()
            .where(models.EstateResource.source == source)
            .where(models.EstateResource.absent_since.is_(None))
            .order_by(models.EstateResource.resource_id)
        )
        rows = (await self.session.execute(statement)).scalars().all()

        marked: list[str] = []
        for row in rows:
            previous = ResourceHealth(row.health)
            existing = _derivation_from_json(row.derivation)
            derivation = HealthDerivation(
                state=ResourceHealth.STALE,
                rule="discovery_sweep_failed",
                derived_at=at,
                raw_status=existing.raw_status if existing else "",
                explanation=f"the {source} discovery sweep failed: {reason}",
            )
            row.health = ResourceHealth.STALE.value
            row.derivation = _derivation_to_json(derivation)
            if previous is not ResourceHealth.STALE:
                await self._append_transition(
                    row.resource_id,
                    state=ResourceHealth.STALE,
                    previous=previous,
                    at=at,
                    rule=derivation.rule,
                )
            marked.append(row.resource_id)

        await self.session.flush()
        return tuple(marked)

    async def record_sweep(self, record: SweepRecord) -> SweepRecord:
        """Store ``record``, replacing any earlier one with the same id."""
        row = await self.session.get(models.DiscoverySweep, (self.org_id, record.sweep_id))
        if row is None:
            row = models.DiscoverySweep(org_id=self.org_id, sweep_id=record.sweep_id)
            self.session.add(row)
        row.source = record.source
        row.started_at = record.started_at
        row.completed_at = record.completed_at
        row.outcome = record.outcome.value
        row.seen_count = record.seen_count
        row.provider_calls = record.provider_calls
        row.cursor = record.cursor
        row.reason = record.reason
        row.findings = dict(record.findings) or None
        with translating(kind="discovery sweep", identifier=record.sweep_id):
            await self.session.flush()
        return record

    async def last_sweep(self, source: str) -> SweepRecord | None:
        """Return ``source``'s most recently started sweep, or ``None``."""
        statement = (
            select(models.DiscoverySweep)
            .where(models.DiscoverySweep.org_id == self.org_id)
            .where(models.DiscoverySweep.source == source)
            .order_by(
                models.DiscoverySweep.started_at.desc(),
                models.DiscoverySweep.sweep_id.desc(),
            )
            .limit(1)
        )
        row = (await self.session.execute(statement)).scalars().first()
        return None if row is None else _to_sweep(row)

    # --- Health ---------------------------------------------------------------

    async def record_health(
        self,
        resource_id: str,
        derivation: HealthDerivation,
    ) -> Resource:
        """Store ``derivation`` as ``resource_id``'s health and return the resource."""
        row = await self._require(resource_id)
        previous = ResourceHealth(row.health)
        row.health = derivation.state.value
        row.derivation = _derivation_to_json(derivation)

        if previous is not derivation.state or not await self._has_history(resource_id):
            await self._append_transition(
                resource_id,
                state=derivation.state,
                previous=previous,
                at=derivation.derived_at,
                rule=derivation.rule,
                signal=derivation.signals[0] if derivation.signals else None,
            )

        await self.session.flush()
        return _to_resource(row)

    async def transitions(
        self,
        resource_id: str,
        *,
        limit: int = DEFAULT_TRANSITION_HISTORY,
    ) -> tuple[HealthTransition, ...]:
        """Return ``resource_id``'s state changes, most recent first."""
        check_estate_limit(limit)
        statement = (
            select(models.HealthTransitionRow)
            .where(models.HealthTransitionRow.org_id == self.org_id)
            .where(models.HealthTransitionRow.resource_id == resource_id)
            .order_by(
                models.HealthTransitionRow.occurred_at.desc(),
                models.HealthTransitionRow.transition_id.desc(),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).scalars().all()
        return tuple(_to_transition(row) for row in rows)

    async def unhealthy_since(
        self,
        resource_ids: tuple[str, ...],
    ) -> Mapping[str, datetime]:
        """Return, for each id currently on an unhealthy streak, when it began."""
        if not resource_ids:
            return {}
        statement = (
            select(
                models.HealthTransitionRow.resource_id,
                models.HealthTransitionRow.occurred_at,
            )
            .where(models.HealthTransitionRow.org_id == self.org_id)
            .where(models.HealthTransitionRow.resource_id.in_(resource_ids))
            .where(models.HealthTransitionRow.state == ResourceHealth.UNHEALTHY.value)
            .distinct(models.HealthTransitionRow.resource_id)
            .order_by(
                models.HealthTransitionRow.resource_id,
                models.HealthTransitionRow.occurred_at.desc(),
            )
        )
        rows = (await self.session.execute(statement)).all()
        return {
            resource_id: as_utc(occurred_at) or occurred_at for resource_id, occurred_at in rows
        }

    async def set_maintenance(
        self,
        resource_id: str,
        *,
        until: datetime,
        reason: str,
        at: datetime,
    ) -> Resource:
        """Put ``resource_id`` into maintenance until ``until`` and return it."""
        row = await self._require(resource_id)
        check_maintenance_window(until=until, at=at)
        row.maintenance_until = until
        row.maintenance_reason = reason
        await self._append_transition(
            resource_id,
            state=ResourceHealth.MAINTENANCE,
            previous=ResourceHealth(row.health),
            at=at,
            rule="maintenance_window_opened",
        )
        await self.session.flush()
        return _to_resource(row)

    async def clear_maintenance(self, resource_id: str, *, at: datetime) -> Resource:
        """End ``resource_id``'s maintenance window now and return it."""
        row = await self._require(resource_id)
        was_in_maintenance = row.maintenance_until is not None
        row.maintenance_until = None
        row.maintenance_reason = ""
        if was_in_maintenance:
            await self._append_transition(
                resource_id,
                state=ResourceHealth(row.health),
                previous=ResourceHealth.MAINTENANCE,
                at=at,
                rule="maintenance_window_closed",
            )
        await self.session.flush()
        return _to_resource(row)

    # --- What referenced it ---------------------------------------------------

    async def link(self, reference: ResourceReference) -> ResourceReference:
        """Record that a run or an incident touched a resource. Idempotent."""
        key = (
            self.org_id,
            reference.resource_id,
            reference.reference_kind.value,
            reference.reference_id,
        )
        existing = await self.session.get(models.ResourceReferenceRow, key)
        if existing is not None:
            return _to_reference(existing)

        row = models.ResourceReferenceRow(
            org_id=self.org_id,
            resource_id=reference.resource_id,
            reference_kind=reference.reference_kind.value,
            reference_id=reference.reference_id,
            recorded_at=reference.recorded_at,
            summary=reference.summary,
        )
        self.session.add(row)
        with translating(
            kind="resource reference",
            identifier=reference.reference_id,
            referenced="resource",
            referenced_id=reference.resource_id,
        ):
            await self.session.flush()
        return reference

    async def references(
        self,
        resource_id: str,
        *,
        reference_kind: ReferenceKind | None = None,
        limit: int = DEFAULT_TRANSITION_HISTORY,
    ) -> tuple[ResourceReference, ...]:
        """Return what referenced ``resource_id``, most recent first."""
        check_estate_limit(limit)
        statement = (
            select(models.ResourceReferenceRow)
            .where(models.ResourceReferenceRow.org_id == self.org_id)
            .where(models.ResourceReferenceRow.resource_id == resource_id)
            .order_by(
                models.ResourceReferenceRow.recorded_at.desc(),
                models.ResourceReferenceRow.reference_id.desc(),
            )
            .limit(limit)
        )
        if reference_kind is not None:
            statement = statement.where(
                models.ResourceReferenceRow.reference_kind == reference_kind.value
            )
        rows = (await self.session.execute(statement)).scalars().all()
        return tuple(_to_reference(row) for row in rows)

    # --- internals ------------------------------------------------------------

    def _resources(self) -> Select[tuple[models.EstateResource]]:
        return select(models.EstateResource).where(models.EstateResource.org_id == self.org_id)

    def _filtered(self, query: EstateQuery) -> Select[tuple[models.EstateResource]]:
        statement = self._resources()
        if not query.include_absent:
            statement = statement.where(models.EstateResource.absent_since.is_(None))
        if query.kinds:
            statement = statement.where(models.EstateResource.kind.in_(query.kinds))
        if query.sources:
            statement = statement.where(models.EstateResource.source.in_(query.sources))
        if query.health:
            statement = statement.where(
                models.EstateResource.health.in_([state.value for state in query.health])
            )
        if query.labels:
            statement = statement.where(
                models.EstateResource.labels.contains(as_list(query.labels))
            )
        if query.team_node_id is not None:
            statement = statement.where(models.EstateResource.team_node_id == query.team_node_id)
        if query.parent_id is not None:
            statement = statement.where(models.EstateResource.parent_id == query.parent_id)
        if query.observed_before is not None:
            # The derivation's own instant, read out of the JSONB as text. ISO
            # 8601 in UTC sorts lexicographically in the same order it sorts
            # chronologically, which is what makes the comparison correct
            # without casting every row to a timestamp.
            statement = statement.where(
                models.EstateResource.derivation["derived_at"].astext
                < query.observed_before.isoformat()
            )
        return statement

    async def _require(self, resource_id: str) -> models.EstateResource:
        row = await self.session.get(models.EstateResource, (self.org_id, resource_id))
        if row is None:
            raise RecordNotFound(kind="resource", identifier=resource_id)
        return row

    async def _has_history(self, resource_id: str) -> bool:
        statement = (
            select(models.HealthTransitionRow.transition_id)
            .where(models.HealthTransitionRow.org_id == self.org_id)
            .where(models.HealthTransitionRow.resource_id == resource_id)
            .limit(1)
        )
        return (await self.session.execute(statement)).scalars().first() is not None

    async def _append_transition(
        self,
        resource_id: str,
        *,
        state: ResourceHealth,
        previous: ResourceHealth | None,
        at: datetime,
        rule: str,
        signal: HealthSignal | None = None,
    ) -> None:
        """Add one transition row, keyed so a repeated conclusion is one row.

        ``merge`` rather than ``add``, because the key is deterministic: two
        replicas that both concluded a resource went absent at the same sweep
        instant produce the same row, and the second must land on the first
        rather than raise a unique violation that fails an otherwise correct
        sweep.
        """
        transition_id = transition_key(resource_id, state, at)
        await self.session.merge(
            models.HealthTransitionRow(
                org_id=self.org_id,
                transition_id=transition_id,
                resource_id=resource_id,
                state=state.value,
                previous_state=previous.value if previous is not None else None,
                occurred_at=at,
                rule=rule,
                signal=_signal_to_json(signal) if signal is not None else None,
            )
        )


def sources_of(resource: Resource) -> Sequence[str]:
    """Return the integrations that have described ``resource``, in order.

    A module function because both the gateway view and the CLI table want the
    same list and neither should be reaching into ``sources`` to build it.
    """
    return [contribution.integration for contribution in resource.sources]


__all__ = ["PostgresEstateRepository", "sources_of"]
