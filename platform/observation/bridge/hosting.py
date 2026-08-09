"""Noticing that the monitoring runs inside the thing it is monitoring.

On the cluster this wave was built for, Prometheus, Alertmanager, Grafana, the
blackbox exporter and Loki all run as containers on one node. During that
cluster's only total outage — both nodes lost networking after a kernel upgrade
renamed the interfaces — **not one alert fired**. The monitors went down with the
thing they were monitoring, and the outage was diagnosed by carrying a keyboard
and a monitor to the machines.

That arrangement is extremely common and it is not, by itself, wrong: a homelab
has one set of hardware. What is wrong is not knowing. So this module answers one
question — is the stack we are reading hosted inside the estate we are reading it
about — and names the resources involved, so the answer can be put in front of an
operator alongside the fact that a watcher outside the cluster is the fix.

**It reports; it does not refuse.** Refusing to use a self-hosted Prometheus
would leave the deployment with less information than it had. The bridge uses it
and says what it is.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from platform.incidents.lifecycle import IncidentRaise
from platform.notifications.models import Severity
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentSubject

#: The pieces of an observability stack this deployment might be pointed at. Not
#: a taxonomy — this is what a homelab actually runs, and each name is one an
#: operator would recognise on a container.
OBSERVABILITY_COMPONENTS: Final[tuple[str, ...]] = (
    "prometheus",
    "alertmanager",
    "grafana",
    "loki",
    "blackbox-exporter",
    "victoriametrics",
    "victorialogs",
)

#: What the incident about a self-hosted stack correlates on. Its own namespace,
#: because it is a standing architectural fact rather than an event, and it must
#: not correlate onto whatever outage eventually proves it.
HOSTING_PREFIX: Final = "bridge-hosting"


@dataclass(frozen=True, slots=True)
class HostedComponent:
    """One piece of the observability stack, running inside the observed estate."""

    component: str
    resource_id: str
    display_name: str
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class SelfHostingReport:
    """Which parts of the stack run inside the estate, and where they all sit."""

    components: tuple[HostedComponent, ...] = ()
    #: Parents carrying more than one component. One entry here is the whole
    #: finding: losing that single resource takes the monitoring with the estate.
    shared_parents: tuple[str, ...] = ()

    @property
    def self_hosted(self) -> bool:
        """Return whether any part of the stack is inside the estate it observes."""
        return bool(self.components)

    @property
    def summary(self) -> str:
        """Return the paragraph an operator reads about this arrangement."""
        if not self.self_hosted:
            return (
                "the observability stack is not running inside the estate it observes, "
                "so an outage of the estate does not take the monitoring with it"
            )
        named = ", ".join(
            f"{entry.component} ({entry.display_name or entry.resource_id})"
            for entry in self.components
        )
        line = (
            f"the observability stack is hosted inside the estate it observes: {named}. "
            f"An outage of the estate takes the monitoring with it, so the alert that "
            f"would tell somebody is the one that will not arrive"
        )
        if self.shared_parents:
            return (
                f"{line}. Worse, {len(self.components)} of them sit on "
                f"{', '.join(self.shared_parents)}, so one resource carries the whole of it. "
                f"A watcher outside the cluster is the fix"
            )
        return f"{line}. A watcher outside the cluster is the fix"

    def as_incident(self, *, team_node_id: str = "") -> IncidentRaise:
        """Return the incident this arrangement opens, through the one lifecycle."""
        return IncidentRaise(
            correlation_key=f"{HOSTING_PREFIX}:self-hosted",
            title="the observability stack runs inside the estate it observes",
            summary=self.summary,
            origin=IncidentOrigin.DETECTOR,
            origin_id=HOSTING_PREFIX,
            severity=Severity.HIGH.value,
            subjects=tuple(
                IncidentSubject(
                    resource_id=entry.resource_id,
                    detail=f"runs {entry.component}",
                    evidence={"component": entry.component, "parent": entry.parent_id or ""},
                )
                for entry in self.components
            ),
            team_node_id=team_node_id,
            cause=self.summary,
        )


def detect_self_hosting(
    endpoints: Mapping[str, str],
    *,
    resources: Iterable[Resource],
) -> SelfHostingReport:
    """Return which of ``endpoints`` resolve to resources inside ``resources``.

    ``endpoints`` maps a component name to the host this deployment reaches it
    at, with or without a port. The match is on the estate's own display names,
    because that is what a homelab operator names a container and it is the one
    correlation available without asking every guest for its addresses — which
    would be a sweep this feature has no business making.
    """
    by_name: dict[str, Resource] = {}
    for resource in resources:
        if resource.display_name:
            by_name.setdefault(resource.display_name.strip().lower(), resource)

    found: list[HostedComponent] = []
    for component, endpoint in sorted(endpoints.items()):
        host = endpoint.split("://")[-1].split("/")[0].split(":")[0].strip().lower()
        hosted = by_name.get(host)
        if hosted is None:
            continue
        found.append(
            HostedComponent(
                component=component,
                resource_id=hosted.resource_id,
                display_name=hosted.display_name,
                parent_id=hosted.parent_id,
            )
        )

    counts: dict[str, int] = {}
    for entry in found:
        if entry.parent_id:
            counts[entry.parent_id] = counts.get(entry.parent_id, 0) + 1

    return SelfHostingReport(
        components=tuple(found),
        shared_parents=tuple(sorted(parent for parent, count in counts.items() if count > 1)),
    )


__all__ = [
    "HOSTING_PREFIX",
    "OBSERVABILITY_COMPONENTS",
    "HostedComponent",
    "SelfHostingReport",
    "detect_self_hosting",
]
