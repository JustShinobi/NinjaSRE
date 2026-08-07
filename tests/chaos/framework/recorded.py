"""A cluster that remembers, so the framework can be proven without one.

Every property the chaos framework claims — that cleanup survives a signal,
that an invalid experiment is not scored as an agent failure, that a second run
waits for the lock — is a property of the framework, not of Kubernetes. Asserting
them against a real cluster would make them assertions nobody runs, which is the
condition infrastructure code is usually in and the reason it breaks when it is
finally needed.

So this is a cluster with the same five operations and none of the network. It
can be told to be unhealthy, to fail a deletion, and to reveal a symptom only
after the third look — the three things that separate a framework that works
from one that has only ever been run on a good day.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tests.chaos.framework.cluster import (
    ClusterHealth,
    ClusterResource,
    ProbeReading,
    is_suite_resource,
    suite_labels,
)


class RecordedClusterError(RuntimeError):
    """The recorded cluster was told to refuse this operation."""


@dataclass(slots=True)
class RecordedCluster:
    """An in-memory cluster with a scripted health and scripted observations."""

    name: str = "kind-ninjasre"
    nodes_ready: int = 3
    nodes_total: int = 3
    unhealthy_pods: tuple[str, ...] = ()
    chaos_ready: bool = True
    reachable: bool = True
    #: Symptom names each probe sees, per look. A probe reads the next entry
    #: each time and stays on the last one, which is how "the fault took a
    #: moment to bite" is expressed without a clock.
    readings: Mapping[str, Sequence[Sequence[str]]] = field(default_factory=dict)
    #: Names whose deletion fails, so the report-rather-than-swallow path is real.
    delete_failures: frozenset[str] = frozenset()
    #: An apply failure message, when the cluster is meant to refuse.
    apply_failure: str = ""
    applied: list[ClusterResource] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    _looks: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.delete_failures, set | list | tuple):
            self.delete_failures = frozenset(self.delete_failures)

    def health(self) -> ClusterHealth:
        """Return the scripted health."""
        return ClusterHealth(
            nodes_ready=self.nodes_ready,
            nodes_total=self.nodes_total,
            unhealthy_pods=tuple(self.unhealthy_pods),
            chaos_ready=self.chaos_ready,
            reachable=self.reachable,
        )

    def apply(self, manifest: Mapping[str, Any]) -> ClusterResource:
        """Record ``manifest`` as applied and return the resource it describes."""
        if self.apply_failure:
            raise RecordedClusterError(self.apply_failure)
        metadata = dict(manifest.get("metadata") or {})
        labels = dict(metadata.get("labels") or {})
        resource = ClusterResource(
            kind=str(manifest.get("kind", "")),
            name=str(metadata.get("name", "")),
            namespace=str(metadata.get("namespace", "")),
            labels=labels or suite_labels(),
        )
        self.applied.append(resource)
        return resource

    def delete(self, resource: ClusterResource) -> None:
        """Remove ``resource``, unless this cluster was told to refuse it."""
        if resource.name in self.delete_failures:
            raise RecordedClusterError(f"{resource.identifier}: webhook denied the delete")
        self.applied = [found for found in self.applied if found.name != resource.name]
        self.deleted.append(resource.identifier)

    def active_faults(self) -> tuple[ClusterResource, ...]:
        """Return every fault this suite currently has applied."""
        return tuple(found for found in self.applied if is_suite_resource(found))

    def observe(self, probe: str, *, namespace: str = "") -> ProbeReading:
        """Return the next scripted reading for ``probe``."""
        script = self.readings.get(probe)
        if not script:
            return ProbeReading(probe=probe, detail="no reading was scripted for this probe")
        index = min(self._looks.get(probe, 0), len(script) - 1)
        self._looks[probe] = self._looks.get(probe, 0) + 1
        return ProbeReading(probe=probe, observed=tuple(script[index]))


__all__ = ["RecordedCluster", "RecordedClusterError"]
