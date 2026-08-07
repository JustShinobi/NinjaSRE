"""The cluster port, over ``kubectl``, for the runs that have a cluster.

Shelling out rather than importing a Kubernetes client library. The suite needs
five operations, ``kubectl`` is already a prerequisite for having a cluster at
all, and a client library would be a dependency in the tree the operator audits
that exists only for a test tree.

The interesting method is ``observe``. Everything above it asks in symptom
names — ``dns_lookup_fails_from_pod``, ``http_error_rate_above_threshold`` — and
this is the only place that knows how to turn one of those into a command and a
command's output back into symptoms. Keeping the translation in one module is
what lets an experiment declare its probe in a document rather than in code.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.chaos import (
    CHAOS_PREFLIGHT_TIMEOUT_SECONDS,
    CHAOS_SUITE_LABEL,
    CHAOS_SUITE_LABEL_VALUE,
)
from tests.chaos.framework.cluster import (
    KUBECTL,
    ClusterHealth,
    ClusterResource,
    ProbeReading,
)
from tests.support.commands import CommandRunner, SubprocessRunner

#: The chaos objects this suite applies, and therefore the ones a sweep looks
#: for. Listed rather than discovered, because ``kubectl get`` against every CRD
#: on a cluster is slow and this set is the set the experiments use.
CHAOS_KINDS: tuple[str, ...] = (
    "podchaos",
    "networkchaos",
    "stresschaos",
    "iochaos",
    "dnschaos",
    "httpchaos",
)

#: A pod phase or container state that means the pod is not serving.
UNHEALTHY_STATES: frozenset[str] = frozenset(
    {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "Error", "Failed", "Unknown"}
)

#: How a probe name becomes a reading. The suite's whole translation layer, in
#: one mapping, so an experiment can name a probe in a YAML document.
ProbeImplementation = Callable[["KubectlCluster", str], ProbeReading]


@dataclass(frozen=True, slots=True)
class KubectlCluster:
    """A live cluster, reached through ``kubectl``."""

    runner: CommandRunner = field(default_factory=SubprocessRunner)
    context: str = ""
    kubeconfig: str = ""
    chaos_namespace: str = "chaos-testing"
    probes: Mapping[str, ProbeImplementation] = field(default_factory=lambda: PROBES)

    @property
    def name(self) -> str:
        """Return the context this cluster is addressed by."""
        return self.context or "current-context"

    # -- plumbing -------------------------------------------------------------

    def argv(self, *arguments: str) -> tuple[str, ...]:
        """Return ``kubectl`` invoked with this cluster's addressing options."""
        prefix = [KUBECTL]
        if self.kubeconfig:
            prefix += ["--kubeconfig", self.kubeconfig]
        if self.context:
            prefix += ["--context", self.context]
        return (*prefix, *arguments)

    def _json(self, *arguments: str) -> dict[str, Any]:
        """Return the JSON document ``kubectl`` printed, or an empty mapping."""
        result = self.runner.run(
            self.argv(*arguments, "-o", "json"), timeout=CHAOS_PREFLIGHT_TIMEOUT_SECONDS
        )
        if not result.ok:
            return {}
        try:
            document = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return {}
        return document if isinstance(document, dict) else {}

    # -- the port -------------------------------------------------------------

    def health(self) -> ClusterHealth:
        """Return the cluster's health, as the preflight check reads it."""
        reachable = self.runner.run(
            self.argv("cluster-info"), timeout=CHAOS_PREFLIGHT_TIMEOUT_SECONDS
        )
        if not reachable.ok:
            return ClusterHealth(reachable=False, detail=reachable.message)

        nodes = self._json("get", "nodes").get("items") or []
        ready = sum(1 for node in nodes if _node_ready(node))

        pods = self._json("get", "pods", "--all-namespaces").get("items") or []
        unhealthy = tuple(f"{_namespace(pod)}/{_name(pod)}" for pod in pods if _pod_unhealthy(pod))

        crds = self.runner.run(
            self.argv("get", "crd", "podchaos.chaos-mesh.org"),
            timeout=CHAOS_PREFLIGHT_TIMEOUT_SECONDS,
        )
        return ClusterHealth(
            nodes_ready=ready,
            nodes_total=len(nodes),
            unhealthy_pods=unhealthy,
            chaos_ready=crds.ok,
            reachable=True,
        )

    def apply(self, manifest: Mapping[str, Any]) -> ClusterResource:
        """Apply ``manifest`` and return the resource it created."""
        result = self.runner.run(self.argv("apply", "-f", "-"), stdin=json.dumps(manifest))
        if not result.ok:
            raise RuntimeError(result.message)
        metadata = dict(manifest.get("metadata") or {})
        return ClusterResource(
            kind=str(manifest.get("kind", "")),
            name=str(metadata.get("name", "")),
            namespace=str(metadata.get("namespace", "")),
            labels=dict(metadata.get("labels") or {}),
        )

    def delete(self, resource: ClusterResource) -> None:
        """Remove ``resource``, raising when the cluster refused."""
        arguments = ["delete", resource.kind.lower(), resource.name, "--ignore-not-found"]
        if resource.namespace:
            arguments += ["-n", resource.namespace]
        result = self.runner.run(self.argv(*arguments))
        if not result.ok:
            raise RuntimeError(result.message)

    def active_faults(self) -> tuple[ClusterResource, ...]:
        """Return every chaos object carrying this suite's label."""
        found: list[ClusterResource] = []
        for kind in CHAOS_KINDS:
            document = self._json(
                "get",
                kind,
                "--all-namespaces",
                "-l",
                f"{CHAOS_SUITE_LABEL}={CHAOS_SUITE_LABEL_VALUE}",
            )
            for item in document.get("items") or []:
                metadata = dict(item.get("metadata") or {})
                found.append(
                    ClusterResource(
                        kind=str(item.get("kind", kind)),
                        name=str(metadata.get("name", "")),
                        namespace=str(metadata.get("namespace", "")),
                        labels=dict(metadata.get("labels") or {}),
                    )
                )
        return tuple(found)

    def observe(self, probe: str, *, namespace: str = "") -> ProbeReading:
        """Return the symptoms ``probe`` can see right now."""
        implementation = self.probes.get(probe)
        if implementation is None:
            return ProbeReading(
                probe=probe,
                detail=(
                    f"no implementation for probe {probe!r}; an experiment declaring one nothing "
                    f"answers is reported as inconclusive rather than scored"
                ),
            )
        return implementation(self, namespace)

    # -- what the probes are built from ---------------------------------------

    def pods(self, namespace: str) -> Sequence[Mapping[str, Any]]:
        """Return the pods in ``namespace``."""
        items = self._json("get", "pods", "-n", namespace or "default").get("items") or []
        return [item for item in items if isinstance(item, dict)]

    def exec_in_first_pod(self, namespace: str, *command: str) -> tuple[bool, str]:
        """Run ``command`` in the first pod of ``namespace`` and return how it went."""
        found = self.pods(namespace)
        if not found:
            return False, f"no pods in namespace {namespace!r} to run the probe from"
        result = self.runner.run(
            self.argv("exec", "-n", namespace, _name(found[0]), "--", *command), timeout=30.0
        )
        return result.ok, (result.stdout or result.stderr).strip()


# -- probe implementations ------------------------------------------------------


def _restarts_rising(cluster: KubectlCluster, namespace: str) -> ProbeReading:
    """Return whether any container in ``namespace`` has restarted."""
    restarts = 0
    backing_off = False
    for pod in cluster.pods(namespace):
        for status in (pod.get("status") or {}).get("containerStatuses") or []:
            restarts += int(status.get("restartCount", 0) or 0)
            waiting = ((status.get("state") or {}).get("waiting") or {}).get("reason", "")
            backing_off = backing_off or waiting in UNHEALTHY_STATES
    observed: list[str] = []
    if restarts:
        observed += ["pod_restarts", "container_restarts", "requests_failing"]
    if backing_off:
        observed.append("back_off_restarting")
    return ProbeReading(probe="restarts", observed=tuple(observed), detail=f"{restarts} restarts")


def _dns_fails(cluster: KubectlCluster, namespace: str) -> ProbeReading:
    """Return whether a name lookup from inside the namespace fails."""
    ok, detail = cluster.exec_in_first_pod(
        namespace, "sh", "-c", "getent hosts payments || echo LOOKUP_FAILED"
    )
    if not ok:
        return ProbeReading(probe="dns", detail=detail)
    if "LOOKUP_FAILED" in detail:
        return ProbeReading(
            probe="dns",
            observed=("service_unreachable", "connection_timeout_errors"),
            detail=detail,
        )
    return ProbeReading(probe="dns", observed=(), detail=detail)


def _dns_unexpected(cluster: KubectlCluster, namespace: str) -> ProbeReading:
    """Return whether a name lookup answers with an address nobody expected."""
    ok, detail = cluster.exec_in_first_pod(
        namespace, "sh", "-c", "getent hosts payments || echo LOOKUP_FAILED"
    )
    if not ok:
        return ProbeReading(probe="dns", detail=detail)
    if "LOOKUP_FAILED" in detail or detail.startswith("10."):
        return ProbeReading(probe="dns", observed=(), detail=detail)
    return ProbeReading(
        probe="dns",
        observed=("connection_refused_errors", "misrouted_requests"),
        detail=detail,
    )


def _peer_unreachable(cluster: KubectlCluster, namespace: str) -> ProbeReading:
    """Return whether the partitioned peer can still be reached."""
    ok, detail = cluster.exec_in_first_pod(
        namespace, "sh", "-c", "nc -z -w 2 payments 8080 || echo UNREACHABLE"
    )
    if not ok:
        return ProbeReading(probe="peer", detail=detail)
    if "UNREACHABLE" in detail:
        return ProbeReading(
            probe="peer",
            observed=("service_unreachable", "connection_refused_errors"),
            detail=detail,
        )
    return ProbeReading(probe="peer", observed=(), detail=detail)


def _pod_condition(symptoms: tuple[str, ...]) -> ProbeImplementation:
    """Return a probe reporting ``symptoms`` when any pod is not serving.

    The honest general case. A resource, storage, or bandwidth fault shows up in
    a metric this suite reads through Prometheus during the run itself; what
    ``kubectl`` can confirm cheaply is that the workload stopped being healthy,
    which is enough to separate "the fault bit" from "nothing happened".
    """

    def probe(cluster: KubectlCluster, namespace: str) -> ProbeReading:
        pods = cluster.pods(namespace)
        if not pods:
            return ProbeReading(probe="workload", detail=f"no pods in {namespace!r}")
        degraded = [pod for pod in pods if _pod_unhealthy(pod) or _pod_restarted(pod)]
        return ProbeReading(
            probe="workload",
            observed=symptoms if degraded else (),
            detail=f"{len(degraded)} of {len(pods)} pods degraded",
        )

    return probe


#: Which probe answers which name. An experiment names one of these keys in its
#: ``validity_probe.check``; a name that is not here is reported as inconclusive
#: rather than being guessed at.
PROBES: Mapping[str, ProbeImplementation] = {
    "pod_restart_count_rises": _restarts_rising,
    "container_restart_count_rises": _restarts_rising,
    "dns_lookup_fails_from_pod": _dns_fails,
    "dns_lookup_returns_unexpected_address": _dns_unexpected,
    "peer_unreachable_from_pod": _peer_unreachable,
    "cpu_utilisation_above_threshold": _pod_condition(("cpu_saturated", "latency_rising")),
    "memory_utilisation_above_threshold": _pod_condition(("memory_saturated", "oom_kills")),
    "io_latency_above_threshold": _pod_condition(("disk_latency_rising", "slow_writes")),
    "request_latency_above_threshold": _pod_condition(
        ("request_latency_rising", "upstream_timeouts")
    ),
    "http_latency_above_threshold": _pod_condition(("request_latency_rising", "upstream_timeouts")),
    "http_error_rate_above_threshold": _pod_condition(
        ("http_5xx_rising", "connection_resets", "error_rate_rising")
    ),
    "packet_loss_above_threshold": _pod_condition(("connection_resets", "retransmissions_rising")),
    "throughput_below_threshold": _pod_condition(("throughput_collapsed", "transfer_timeouts")),
}


def _name(item: Mapping[str, Any]) -> str:
    return str((item.get("metadata") or {}).get("name", ""))


def _namespace(item: Mapping[str, Any]) -> str:
    return str((item.get("metadata") or {}).get("namespace", ""))


def _node_ready(node: Mapping[str, Any]) -> bool:
    conditions = (node.get("status") or {}).get("conditions") or []
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in conditions
    )


def _pod_unhealthy(pod: Mapping[str, Any]) -> bool:
    status = pod.get("status") or {}
    if str(status.get("phase", "")) in {"Failed", "Unknown"}:
        return True
    for container in status.get("containerStatuses") or []:
        waiting = ((container.get("state") or {}).get("waiting") or {}).get("reason", "")
        if waiting in UNHEALTHY_STATES:
            return True
    return False


def _pod_restarted(pod: Mapping[str, Any]) -> bool:
    status = pod.get("status") or {}
    return any(
        int(container.get("restartCount", 0) or 0) > 0
        for container in status.get("containerStatuses") or []
    )


__all__ = ["CHAOS_KINDS", "PROBES", "UNHEALTHY_STATES", "KubectlCluster", "ProbeImplementation"]
