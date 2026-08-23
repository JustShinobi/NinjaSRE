"""What a surface asks about incidents and detectors, in one place.

The CLI, the REST API and the console all want the same four things — list the
incidents, open one, close one, silence one — and the same four about detectors.
Putting the transaction handling and the assembly here rather than in each
surface is what keeps a listing that means one thing in the console from meaning
something slightly different in the CLI.

**Detectors are read from configuration on every call.** There is no cached
registry behind this. A detector an operator added thirty seconds ago has to be
in the next listing, and a cache that had to be invalidated by whatever wrote
the configuration would be a cache with two owners.

**A dry run is what a "last verdict" is.** Nothing stores an observation: a
fourth table holding every verdict of every detector over every resource would
be the largest table in the deployment and would answer a question the signals
already answer. So a verdict is computed from stored signals at read time, which
is both cheaper and *more* honest — it is what the detector concludes now,
rather than what it concluded whenever something last wrote a row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from config.constants.observation import MAX_INCIDENT_PAGE_SIZE
from platform.config_service.schema.policies import ObservationPolicySettings
from platform.incidents.errors import UnknownIncident
from platform.incidents.lifecycle import IncidentLifecycle
from platform.observation.detectors import config as detector_config
from platform.observation.detectors.conditions import Observation
from platform.observation.detectors.model import DetectorDeclaration
from platform.observation.detectors.registry import DetectorRegistry, DryRun
from platform.persistence.ports.estate_repository import EstateQuery, Resource
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentQuery,
    IncidentState,
    IncidentStore,
    TimelineEntry,
    is_public_incident_id,
)
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope


async def _resolve(store: IncidentStore, candidate: str) -> Incident | None:
    """Return the incident ``candidate`` names, whichever grafia it is.

    A parameter matching the public address's own grammar resolves through
    that column; anything else — including the internal key, which stays a
    valid address on purpose — resolves through the primary key. A shape
    decision rather than two lookups tried in sequence, so an ordinary
    request costs one indexed read either way.
    """
    if is_public_incident_id(candidate):
        return await store.get_by_public_id(candidate)
    return await store.get(candidate)


#: Resources one detector listing counts its coverage over. The estate page
#: bound would be the natural number and is too large for a listing that runs a
#: dry run per detector; this is what a console table is asked for.
COVERAGE_SAMPLE = 500


@dataclass(frozen=True, slots=True)
class IncidentDetail:
    """One incident and everything its page shows."""

    incident: Incident
    timeline: tuple[TimelineEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class DetectorView:
    """One detector as a table row shows it.

    ``subjects_covered`` and ``subjects_total`` are the difference between "this
    detector exists" and "this detector is looking at 84 of 92 things", which
    are very different claims and only one of them is worth a row.
    """

    declaration: DetectorDeclaration
    subjects_covered: int = 0
    subjects_total: int = 0
    last_verdict: str = ""
    last_evaluated_at: datetime | None = None
    findings: tuple[Observation, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class IncidentService:
    """Every read and write a surface makes about incidents."""

    gateway: PersistenceGateway

    async def list(
        self,
        scope: TenantScope,
        query: IncidentQuery,
    ) -> tuple[Incident, ...]:
        """Return the incidents matching ``query``, most recently opened first."""
        async with self.gateway.begin(scope) as uow:
            return await uow.incidents.query(query)

    async def detail(self, scope: TenantScope, incident_id: str) -> IncidentDetail | None:
        """Return one incident with its timeline, or ``None``.

        ``incident_id`` may be the internal key or the incident's own short
        public address — ``_resolve`` picks the lookup by the parameter's
        shape. The timeline is always read by the *internal* key once the
        row is found, because that is the key every timeline entry actually
        carries, whichever grafia the caller asked by.
        """
        async with self.gateway.begin(scope) as uow:
            incident = await _resolve(uow.incidents, incident_id)
            if incident is None:
                return None
            return IncidentDetail(
                incident=incident, timeline=await uow.incidents.timeline(incident.incident_id)
            )

    async def close(
        self,
        scope: TenantScope,
        incident_id: str,
        *,
        reason: str,
        actor: str,
        state: IncidentState = IncidentState.CLOSED_WITHOUT_ACTION,
        now: datetime,
    ) -> Incident:
        """Close ``incident_id`` on a person's behalf, with their reason.

        ``incident_id`` may be either grafia, resolved the same way ``detail``
        resolves it — a screen that opens an incident by its public address
        must be able to act on the same address rather than needing the
        internal key for the write.
        """
        async with self.gateway.begin(scope) as uow:
            resolved = await _resolve(uow.incidents, incident_id)
            if resolved is None:
                raise UnknownIncident(incident_id)
            lifecycle = IncidentLifecycle(store=uow.incidents)
            return await lifecycle.close(
                resolved.incident_id, reason=reason, actor=actor, state=state, now=now
            )

    async def suppress(
        self,
        scope: TenantScope,
        incident_id: str,
        *,
        by: str,
        reason: str,
        actor: str,
        now: datetime,
    ) -> Incident:
        """Close ``incident_id`` as suppressed, naming what covered it.

        ``incident_id`` may be either grafia, resolved the same way ``detail``
        resolves it.
        """
        async with self.gateway.begin(scope) as uow:
            resolved = await _resolve(uow.incidents, incident_id)
            if resolved is None:
                raise UnknownIncident(incident_id)
            return await IncidentLifecycle(store=uow.incidents).suppress(
                resolved.incident_id, by=by, reason=reason, actor=actor, now=now
            )


@dataclass(frozen=True, slots=True)
class DetectorService:
    """Every read a surface makes about detectors, and the two toggles.

    Holds the resolved configuration rather than a registry, because
    configuration is where a detector comes from and a second source of truth
    for "which detectors exist" is the thing this avoids.
    """

    gateway: PersistenceGateway
    settings: ObservationPolicySettings

    @property
    def resolved(self) -> detector_config.ResolvedDetectors:
        """Return the detectors this node's configuration declares."""
        return detector_config.read(self.settings)

    @property
    def paused(self) -> bool:
        """Return whether detection is paused for this node."""
        return self.resolved.paused

    @property
    def pause_reason(self) -> str:
        """Return why detection is paused, or the empty string."""
        return self.resolved.pause_reason

    async def list(self, scope: TenantScope, *, now: datetime) -> tuple[DetectorView, ...]:
        """Return every declared detector with its coverage and its current verdict."""
        resolved = self.resolved
        registry = DetectorRegistry.of(resolved.detectors)

        async with self.gateway.begin(scope) as uow:
            estate = await uow.estate.query(EstateQuery(limit=COVERAGE_SAMPLE))
            views: list[DetectorView] = []
            for declaration in resolved.detectors:
                applicable = _applicable(estate, declaration)
                run = await registry.dry_run(
                    declaration.detector_id,
                    uow.signals,
                    now=now,
                    resource_ids=tuple(resource.resource_id for resource in applicable),
                )
                views.append(_view(declaration, run, applicable=applicable, estate=estate, now=now))
        return tuple(views)

    async def dry_run(
        self,
        scope: TenantScope,
        detector_id: str,
        *,
        now: datetime,
    ) -> DryRun:
        """Return what ``detector_id`` would conclude against stored signals.

        Fires nothing. An operator testing a threshold against last week must
        not be able to page somebody with last week's numbers, and there is no
        parameter here that would let them.
        """
        registry = DetectorRegistry.of(self.resolved.detectors)
        declaration = registry.get(detector_id)

        async with self.gateway.begin(scope) as uow:
            estate = await uow.estate.query(EstateQuery(limit=COVERAGE_SAMPLE))
            applicable = _applicable(estate, declaration)
            return await registry.dry_run(
                detector_id,
                uow.signals,
                now=now,
                resource_ids=tuple(resource.resource_id for resource in applicable),
            )

    async def observations(
        self, scope: TenantScope, *, now: datetime, limit: int = MAX_INCIDENT_PAGE_SIZE
    ) -> tuple[Observation, ...]:
        """Return what every enabled detector concludes right now.

        Computed rather than stored. A table of every verdict of every detector
        over every resource would be the largest one in the deployment and would
        answer a question the signals already answer — and it would answer it
        with what was true whenever something last wrote a row, rather than with
        what is true now.
        """
        views = await self.list(scope, now=now)
        seen: list[Observation] = []
        for view in views:
            if not view.declaration.enabled or self.paused:
                continue
            seen.extend(view.findings)
        seen.sort(key=lambda entry: (entry.observed_at, entry.detector_id, entry.resource_id))
        return tuple(seen[:limit])

    def settings_with(self, detector_id: str, *, enabled: bool) -> dict[str, object]:
        """Return the configuration patch that turns ``detector_id`` on or off.

        A patch rather than a mutation, because persisting the change is a
        configuration write and the configuration service owns those — including
        the audit line, the field locks, and the approval gate. A toggle that
        wrote around it would be an operator's decision with no record of who
        made it.

        The whole list is returned because a list replaces rather than merges,
        which is also what makes the write mean "this node's detectors are
        these" — the honest reading when a team overrides an inherited set.
        """
        registry = DetectorRegistry.of(self.resolved.detectors)
        registry.get(detector_id)
        return {
            "policies": {
                "observation": {
                    "detectors": [
                        {
                            **entry.model_dump(),
                            "enabled": enabled
                            if entry.detector_id == detector_id
                            else entry.enabled,
                        }
                        for entry in self.settings.detectors
                    ]
                }
            }
        }


def _applicable(
    estate: tuple[Resource, ...], declaration: DetectorDeclaration
) -> tuple[Resource, ...]:
    """Return the resources this detector watches."""
    return tuple(resource for resource in estate if declaration.applies_to(resource.kind))


def _view(
    declaration: DetectorDeclaration,
    run: DryRun,
    *,
    applicable: tuple[Resource, ...],
    estate: tuple[Resource, ...],
    now: datetime,
) -> DetectorView:
    """Return one detector's row, with its coverage and its current verdict."""
    verdicts = {entry.verdict.value for entry in run.observations}
    leading = run.findings[0].verdict.value if run.findings else _quietest(verdicts)
    return DetectorView(
        declaration=declaration,
        subjects_covered=len(run.observations),
        subjects_total=len(estate) or len(applicable),
        last_verdict=leading,
        last_evaluated_at=now,
        findings=run.findings,
    )


#: The verdicts a listing reports when nothing is firing, most interesting
#: first. "Pending" outranks "clear" because a condition that is true and has
#: not held long enough is news, and a row that showed it as clear would be the
#: deployment reporting health it is in the middle of doubting.
_QUIET_ORDER = ("pending", "holding", "clear", "insufficient")


def _quietest(verdicts: set[str]) -> str:
    """Return the most interesting verdict a detector reached, none of them firing.

    ``insufficient`` when it had nothing to read, and it is deliberately last:
    reporting "clear" for a detector that saw no samples would be the deployment
    claiming health it has not established.
    """
    for verdict in _QUIET_ORDER:
        if verdict in verdicts:
            return "clear" if verdict == "holding" else verdict
    return "insufficient"


__all__ = [
    "COVERAGE_SAMPLE",
    "DetectorService",
    "DetectorView",
    "IncidentDetail",
    "IncidentService",
]
