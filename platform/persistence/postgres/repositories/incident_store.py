"""Incidents in PostgreSQL, with correlation as an indexed lookup.

The one query that has to be fast is "is there already a live incident for this
cause", because the tick asks it once per finding. A partial index on
``(org_id, correlation_key) WHERE closed_at IS NULL`` makes it a lookup over the
open incidents alone — which is a handful of rows in a healthy deployment and
stays a handful however much history accumulates.

Subjects are JSONB and runs and actions are arrays. They are read only with
their incident and never queried across incidents, so three child tables would
be three joins to render one screen and no query would ever use the
normalisation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from config.constants.observation import MAX_INCIDENT_TIMELINE
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentOrigin,
    IncidentQuery,
    IncidentState,
    IncidentSubject,
    TimelineEntry,
    TimelineKind,
    check_incident_limit,
    check_timeline_limit,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_list,
    as_tuple,
    as_utc,
    rows_affected,
)

#: The key the subject list lives under inside the JSONB column. A named
#: constant because the column holds an object rather than an array — a bare
#: JSONB array is awkward to extend and this one will be.
_SUBJECTS = "subjects"


class PostgresIncidentStore(TenantBound):
    """One organisation's incidents, inside one transaction."""

    async def upsert(self, incident: Incident) -> Incident:
        """Store ``incident``, replacing any earlier record with the same id."""
        values = _row(self.org_id, incident)
        statement = insert(models.IncidentRow).values(**values)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org_id", "incident_id"],
                set_={
                    key: statement.excluded[key]
                    for key in values
                    if key not in {"org_id", "incident_id"}
                },
            )
        )
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        """Return the incident with ``incident_id``, or ``None``."""
        found = await self.session.execute(
            select(models.IncidentRow).where(
                models.IncidentRow.org_id == self.org_id,
                models.IncidentRow.incident_id == incident_id,
            )
        )
        row = found.scalar_one_or_none()
        return None if row is None else _incident(row)

    async def open_for(self, correlation_key: str) -> Incident | None:
        """Return the live incident for ``correlation_key``, or ``None``."""
        found = await self.session.execute(
            select(models.IncidentRow)
            .where(
                models.IncidentRow.org_id == self.org_id,
                models.IncidentRow.correlation_key == correlation_key,
                models.IncidentRow.closed_at.is_(None),
            )
            .order_by(models.IncidentRow.opened_at.desc(), models.IncidentRow.incident_id.desc())
            .limit(1)
        )
        row = found.scalar_one_or_none()
        return None if row is None else _incident(row)

    async def find_by_run(self, run_id: str) -> Incident | None:
        """Return the incident ``run_id`` is attached to, or ``None``.

        A containment lookup over the GIN index on ``run_ids``, not a scan —
        the same reasoning ``episodes.components`` already uses.
        """
        found = await self.session.execute(
            select(models.IncidentRow).where(
                models.IncidentRow.org_id == self.org_id,
                models.IncidentRow.run_ids.contains([run_id]),
            )
        )
        row = found.scalars().first()
        return None if row is None else _incident(row)

    async def query(self, query: IncidentQuery) -> tuple[Incident, ...]:
        """Return the incidents matching ``query``, most recently opened first."""
        limit = check_incident_limit(query.limit)
        statement = select(models.IncidentRow).where(models.IncidentRow.org_id == self.org_id)

        if query.live_only:
            statement = statement.where(models.IncidentRow.closed_at.is_(None))
        if query.states:
            statement = statement.where(
                models.IncidentRow.state.in_([state.value for state in query.states])
            )
        if query.origins:
            statement = statement.where(
                models.IncidentRow.origin.in_([origin.value for origin in query.origins])
            )
        if query.severities:
            statement = statement.where(models.IncidentRow.severity.in_(query.severities))
        if query.detector_ids:
            statement = statement.where(models.IncidentRow.origin_id.in_(query.detector_ids))
        if query.team_node_id is not None:
            statement = statement.where(models.IncidentRow.team_node_id == query.team_node_id)
        if query.opened_after is not None:
            statement = statement.where(models.IncidentRow.opened_at >= query.opened_after)

        statement = statement.order_by(
            models.IncidentRow.opened_at.desc(), models.IncidentRow.incident_id.desc()
        )
        found = await self.session.execute(statement)
        incidents = [_incident(row) for row in found.scalars()]

        # Applied here rather than in SQL: a subject filter over a JSONB list
        # needs a containment operator and an index nothing else would use, and
        # the page is already bounded by the time it reaches this line.
        if query.subject_id:
            incidents = [
                incident for incident in incidents if query.subject_id in incident.subject_ids
            ]
        return tuple(incidents[:limit])

    async def append(self, entries: tuple[TimelineEntry, ...]) -> tuple[TimelineEntry, ...]:
        """Append ``entries`` to their incidents' timelines and return them."""
        if not entries:
            return ()
        statement = insert(models.IncidentTimelineRow).values(
            [_entry_row(self.org_id, entry) for entry in entries]
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["org_id", "entry_id"],
                set_={
                    "cause": statement.excluded.cause,
                    "detail": statement.excluded.detail,
                    "actor": statement.excluded.actor,
                    "query": statement.excluded.query,
                    "result": statement.excluded.result,
                },
            )
        )
        return entries

    async def timeline(
        self,
        incident_id: str,
        *,
        limit: int = MAX_INCIDENT_TIMELINE,
    ) -> tuple[TimelineEntry, ...]:
        """Return ``incident_id``'s history, oldest first."""
        check_timeline_limit(limit)
        found = await self.session.execute(
            select(models.IncidentTimelineRow)
            .where(
                models.IncidentTimelineRow.org_id == self.org_id,
                models.IncidentTimelineRow.incident_id == incident_id,
            )
            .order_by(models.IncidentTimelineRow.at, models.IncidentTimelineRow.entry_id)
            .limit(limit)
        )
        return tuple(_entry(row) for row in found.scalars())

    async def purge(self, *, before: datetime) -> int:
        """Delete incidents closed before ``before`` and return how many went."""
        removed = await self.session.execute(
            delete(models.IncidentRow).where(
                models.IncidentRow.org_id == self.org_id,
                models.IncidentRow.closed_at.is_not(None),
                models.IncidentRow.closed_at < before,
            )
        )
        return rows_affected(removed)


def _row(org_id: str, incident: Incident) -> dict[str, Any]:
    """Return ``incident`` as the column values one row binds from."""
    return {
        "org_id": org_id,
        "incident_id": incident.incident_id,
        "correlation_key": incident.correlation_key,
        "title": incident.title,
        "summary": incident.summary,
        "origin": incident.origin.value,
        "origin_id": incident.origin_id,
        "severity": incident.severity,
        "state": incident.state.value,
        "opened_at": incident.opened_at,
        "closed_at": incident.closed_at,
        "team_node_id": incident.team_node_id,
        "subjects": {_SUBJECTS: [_subject_json(subject) for subject in incident.subjects]},
        "run_ids": as_list(incident.run_ids),
        "actions": as_list(incident.actions),
        "close_reason": incident.close_reason,
        "self_resolved": incident.self_resolved,
        "suppressed_by": incident.suppressed_by,
    }


def _subject_json(subject: IncidentSubject) -> dict[str, Any]:
    """Return one subject as the object stored inside the JSONB column."""
    return {
        "resource_id": subject.resource_id,
        "detail": subject.detail,
        "evidence": dict(subject.evidence),
        "observed_at": subject.observed_at.isoformat() if subject.observed_at else None,
        "absent_since": subject.absent_since.isoformat() if subject.absent_since else None,
    }


def _subject(stored: Any) -> IncidentSubject:
    """Return one stored subject as the record callers hold."""
    return IncidentSubject(
        resource_id=str(stored.get("resource_id", "")),
        detail=str(stored.get("detail", "")),
        evidence={str(key): str(value) for key, value in dict(stored.get("evidence", {})).items()},
        observed_at=_instant(stored.get("observed_at")),
        absent_since=_instant(stored.get("absent_since")),
    )


def _instant(raw: Any) -> datetime | None:
    """Return the instant ``raw`` names, or ``None``."""
    if not raw:
        return None
    return as_utc(datetime.fromisoformat(str(raw)))


def _incident(row: models.IncidentRow) -> Incident:
    """Return the stored row as the record callers hold."""
    return Incident(
        incident_id=row.incident_id,
        correlation_key=row.correlation_key,
        title=row.title,
        summary=row.summary,
        origin=IncidentOrigin(row.origin),
        origin_id=row.origin_id,
        severity=row.severity,
        state=IncidentState(row.state),
        opened_at=as_utc(row.opened_at) or row.opened_at,
        subjects=tuple(_subject(entry) for entry in row.subjects.get(_SUBJECTS, [])),
        closed_at=as_utc(row.closed_at),
        team_node_id=row.team_node_id,
        run_ids=as_tuple(row.run_ids),
        actions=as_tuple(row.actions),
        close_reason=row.close_reason,
        self_resolved=row.self_resolved,
        suppressed_by=row.suppressed_by,
    )


def _entry_row(org_id: str, entry: TimelineEntry) -> dict[str, Any]:
    """Return ``entry`` as the column values one row binds from."""
    return {
        "org_id": org_id,
        "entry_id": entry.entry_id,
        "incident_id": entry.incident_id,
        "kind": entry.kind.value,
        "at": entry.at,
        "actor": entry.actor,
        "cause": entry.cause,
        "detail": entry.detail,
        "query": entry.query,
        "result": entry.result,
    }


def _entry(row: models.IncidentTimelineRow) -> TimelineEntry:
    """Return the stored row as the record callers hold."""
    return TimelineEntry(
        entry_id=row.entry_id,
        incident_id=row.incident_id,
        kind=TimelineKind(row.kind),
        at=as_utc(row.at) or row.at,
        actor=row.actor,
        cause=row.cause,
        detail=row.detail,
        query=row.query,
        result=row.result,
    )


__all__ = ["PostgresIncidentStore"]
