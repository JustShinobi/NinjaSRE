"""Noticing that the deployment is a guest of the cluster it is watching.

Most homelab operators will run this on the cluster it watches, because a
homelab has one set of hardware. That is a supported configuration and a real
hazard, and the two facts are not in tension: the hazard is not that it might
fail, it is that the failure it most needs to report is the one that takes it
down with everything else.

There are exactly two honest responses and this module is both of them.

**Say so.** A deployment that knows it is a guest of the cluster it manages can
put that in front of the operator, alongside the fact that an external heartbeat
is what closes the gap.

**Report a problem affecting itself plainly.** When the incident is about the
node this process is running on, or the datastore its database is written to, a
health report that says "healthy" is worse than one that says nothing — and
"nothing" is what a stopped process says anyway. So the report names the
overlap: *this problem is about the node I am running on*.

The detection is deliberately simple. It compares what the process knows about
where it is — its hostname, and the resource identifier a first-run setup
recorded for it — against the estate. There is no probing, no ARP, and no
sweeping every guest for its addresses; the cost of a wrong answer here is a
warning that does not apply, and the cost of a sweep is a system that surveys
the network it was invited onto.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from platform.persistence.ports.estate_repository import Resource


@dataclass(frozen=True, slots=True)
class SelfPlacement:
    """Where this deployment is running, as far as it can honestly tell.

    ``resource`` is the estate resource this process believes it is. ``None``
    means it is not in the estate at all, which is the good case — the
    deployment is on hardware the cluster does not own.
    """

    hostname: str
    resource_id: str = ""
    display_name: str = ""
    #: The node the resource sits on, when it sits on one. The most useful
    #: single fact here: it is what a node-level incident is compared against.
    node_id: str = ""

    @property
    def on_managed_estate(self) -> bool:
        """Return whether this deployment is a resource in the estate it watches."""
        return bool(self.resource_id)

    def describe(self) -> str:
        """Return the paragraph shown at setup and in every health report."""
        if not self.on_managed_estate:
            return (
                f"This deployment is running on {self.hostname}, which is not part of the "
                f"estate it watches. An outage of the cluster does not take the guardian "
                f"with it."
            )
        where = f" on {self.node_id}" if self.node_id else ""
        return (
            f"This deployment is running as {self.display_name or self.resource_id}{where}, "
            f"inside the estate it watches. That is supported and it is also the hazard "
            f"worth naming: the failure it most needs to report is the one that takes it "
            f"down. The external heartbeat is what covers that, and it is why there is no "
            f"setting that turns it off."
        )

    def to_record(self) -> dict[str, Any]:
        """Return what a health endpoint and the console both render."""
        return {
            "hostname": self.hostname,
            "resource_id": self.resource_id,
            "display_name": self.display_name,
            "node_id": self.node_id,
            "on_managed_estate": self.on_managed_estate,
            "description": self.describe(),
        }


@dataclass(frozen=True, slots=True)
class SelfAffectingProblem:
    """An incident that is about the infrastructure this deployment is running on.

    Reported as a distinct thing rather than folded into the incident, because
    the operator's next action differs: an incident about somebody else's guest
    is something the deployment can work on, and an incident about the node
    underneath the deployment is something it may stop being able to work on
    halfway through.
    """

    incident_id: str
    title: str
    #: Which of this deployment's own resources the incident names.
    overlapping_resource_id: str
    #: How the overlap arises: the deployment itself, or the node it sits on.
    relation: str = "the node this deployment runs on"

    def describe(self) -> str:
        """Return the sentence that replaces "healthy" in a report."""
        return (
            f"{self.title} is about {self.relation}. This deployment is therefore reporting "
            f"a problem that affects itself: anything it concludes from here may be "
            f"incomplete, and if the problem gets worse it will stop reporting rather than "
            f"report that all is well. The external heartbeat is the reading to trust."
        )

    def to_record(self) -> dict[str, Any]:
        """Return the document a health report carries for this overlap."""
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "overlapping_resource_id": self.overlapping_resource_id,
            "relation": self.relation,
            "description": self.describe(),
        }


def locate(hostname: str, *, resources: Iterable[Resource]) -> SelfPlacement:
    """Return where this deployment is, by matching ``hostname`` against the estate.

    Matched on the estate's own display names, which is what a homelab operator
    names a container and the one correlation available without asking every
    guest for its addresses. A wrong answer here costs a warning that does not
    apply; a sweep would cost the operator a system that surveys their network.
    """
    wanted = hostname.strip().lower()
    if not wanted:
        return SelfPlacement(hostname=hostname)

    for resource in resources:
        name = (resource.display_name or "").strip().lower()
        if name and name == wanted:
            return SelfPlacement(
                hostname=hostname,
                resource_id=resource.resource_id,
                display_name=resource.display_name,
                node_id=resource.parent_id or "",
            )
    return SelfPlacement(hostname=hostname)


def problems_affecting_self(
    placement: SelfPlacement,
    incidents: Sequence[tuple[str, str, tuple[str, ...]]],
) -> tuple[SelfAffectingProblem, ...]:
    """Return the incidents whose subjects include this deployment or its node.

    ``incidents`` is ``(incident_id, title, subject_resource_ids)`` — a shape
    rather than the stored type, because this is a comparison and taking the
    repository's record would make a pure function need a database.
    """
    if not placement.on_managed_estate:
        return ()

    mine = {placement.resource_id}
    node = placement.node_id
    found: list[SelfAffectingProblem] = []
    for incident_id, title, subjects in incidents:
        overlap = mine.intersection(subjects)
        if overlap:
            found.append(
                SelfAffectingProblem(
                    incident_id=incident_id,
                    title=title,
                    overlapping_resource_id=next(iter(sorted(overlap))),
                    relation="this deployment itself",
                )
            )
        elif node and node in subjects:
            found.append(
                SelfAffectingProblem(
                    incident_id=incident_id,
                    title=title,
                    overlapping_resource_id=node,
                    relation="the node this deployment runs on",
                )
            )
    return tuple(found)


__all__ = [
    "SelfAffectingProblem",
    "SelfPlacement",
    "locate",
    "problems_affecting_self",
]
