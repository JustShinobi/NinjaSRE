"""Is this cluster fit to be experimented on, asked before anything is injected.

The check exists because of one specific way a suite goes quietly wrong. An
experiment run against a cluster that was already broken produces telemetry
full of a failure nobody injected, the agent quite reasonably diagnoses that
one, and the run is scored as a miss. Repeat across fourteen experiments and
the release looks like a regression that nothing in the agent caused.

So the answer is not a boolean. It is a list of reasons, and every one of them
names the thing that has to be fixed — because the person reading it is about to
decide whether to fix the cluster or to stop trusting the suite.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.chaos import CHAOS_MAX_UNHEALTHY_PODS
from tests.chaos.framework.cluster import Cluster, ClusterHealth


@dataclass(frozen=True, slots=True)
class PreflightReport:
    """Whether the cluster is a usable baseline, and what is wrong when it is not."""

    healthy: bool
    reasons: tuple[str, ...] = ()
    health: ClusterHealth = ClusterHealth()

    @property
    def summary(self) -> str:
        """Return one line describing the verdict."""
        if self.healthy:
            return (
                f"{self.health.nodes_ready}/{self.health.nodes_total} nodes ready, "
                f"no unhealthy pods, chaos framework installed"
            )
        return "; ".join(self.reasons)


def preflight(cluster: Cluster) -> PreflightReport:
    """Return whether ``cluster`` is a healthy baseline to inject a fault into.

    A fault already applied counts as unhealthy. It means either a previous run
    was killed or another run is in progress, and injecting a second fault on
    top would produce a scenario with two causes and an answer key naming one.
    """
    health = cluster.health()
    reasons: list[str] = []

    if not health.reachable:
        reasons.append(f"the cluster did not answer: {health.detail or 'no detail'}")
        return PreflightReport(healthy=False, reasons=tuple(reasons), health=health)

    if not health.nodes_all_ready:
        reasons.append(
            f"{health.nodes_ready} of {health.nodes_total} nodes are ready; an experiment on a "
            f"degraded cluster measures the cluster"
        )
    if len(health.unhealthy_pods) > CHAOS_MAX_UNHEALTHY_PODS:
        named = ", ".join(sorted(health.unhealthy_pods))
        reasons.append(
            f"{len(health.unhealthy_pods)} pods are already unhealthy ({named}); the agent would "
            f"be scored against a failure nobody injected"
        )
    if not health.chaos_ready:
        reasons.append(
            "the chaos framework is not installed on this cluster, so no fault can be applied "
            "declaratively"
        )

    active = cluster.active_faults()
    if active:
        named = ", ".join(sorted(found.identifier for found in active))
        reasons.append(
            f"a chaos experiment is already active ({named}); either another run holds this "
            f"cluster or a previous one was killed without cleaning up"
        )

    return PreflightReport(healthy=not reasons, reasons=tuple(reasons), health=health)


__all__ = ["PreflightReport", "preflight"]
