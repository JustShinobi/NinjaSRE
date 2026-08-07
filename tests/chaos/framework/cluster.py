"""The cluster, as everything above it needs to see one — and whether there is one.

Five operations, which is all a chaos experiment needs: read the cluster's
health, apply a fault, list what this suite has applied, remove one, and observe
whether a named symptom is showing. Anything richer would be a Kubernetes
client, and writing one of those into a test tree is how a suite acquires a
dependency it then has to keep current with an API that moves.

``observe`` is the one that looks unusual. A validity probe does not want a pod
list; it wants an answer to "is DNS resolution failing from inside the mesh
right now", and the shape of the question is the same whichever fault raised
it. So the port answers in symptom names, the same vocabulary an experiment's
``expected.yml`` declares, and the translation from "what the cluster says" to
"which symptom that is" lives in the one implementation that talks to a real
cluster.

Availability is here rather than in the runner because the answer has to be
readable *before* anything is constructed. A suite that discovers it has no
cluster half way through injection has already done something it now has to
undo.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.chaos import (
    CHAOS_EXPERIMENT_LABEL,
    CHAOS_PREFLIGHT_TIMEOUT_SECONDS,
    CHAOS_SUITE_LABEL,
    CHAOS_SUITE_LABEL_VALUE,
)
from tests.support.commands import CommandRunner, SubprocessRunner

#: The command every implementation of this port is written against.
KUBECTL = "kubectl"

#: What an operator is told to run when there is no cluster. One command, and
#: naming it in the skip message is the difference between a skip somebody acts
#: on and one they scroll past.
CHAOS_SETUP_COMMAND = "make chaos-setup"


@dataclass(frozen=True, slots=True)
class ClusterResource:
    """One object this suite put on a cluster, as cleanup needs to see it."""

    kind: str
    name: str
    namespace: str = ""
    labels: Mapping[str, str] = field(default_factory=dict)

    @property
    def identifier(self) -> str:
        """Return the string a report names this resource by."""
        return (
            f"{self.kind}/{self.namespace}/{self.name}"
            if self.namespace
            else (f"{self.kind}/{self.name}")
        )

    @property
    def experiment_id(self) -> str:
        """Return the experiment this resource belongs to, if it says."""
        return self.labels.get(CHAOS_EXPERIMENT_LABEL, "")


@dataclass(frozen=True, slots=True)
class ClusterHealth:
    """What the cluster looks like at one moment, at the resolution preflight needs."""

    nodes_ready: int = 0
    nodes_total: int = 0
    unhealthy_pods: tuple[str, ...] = ()
    chaos_ready: bool = False
    reachable: bool = True
    detail: str = ""

    @property
    def nodes_all_ready(self) -> bool:
        """Return whether every node the cluster has is ready."""
        return self.nodes_total > 0 and self.nodes_ready == self.nodes_total


@dataclass(frozen=True, slots=True)
class ProbeReading:
    """What one observation of the cluster saw, in symptom names."""

    probe: str
    observed: tuple[str, ...] = ()
    detail: str = ""


@runtime_checkable
class SymptomSource(Protocol):
    """Whatever can be asked whether a named symptom is showing.

    Separate from ``Cluster`` because the cloud suite has no cluster and the
    same validity question: "did the fault this run injected actually produce
    what it said it would". One protocol means one probe implementation serves
    both, and neither suite gets to answer that question its own way.
    """

    def observe(self, probe: str, *, namespace: str = "") -> ProbeReading:
        """Return the symptoms ``probe`` can see right now."""


@runtime_checkable
class Cluster(SymptomSource, Protocol):
    """The cluster operations one chaos experiment needs, and no others."""

    @property
    def name(self) -> str:
        """Return the context this cluster is addressed by."""

    def health(self) -> ClusterHealth:
        """Return the cluster's health, as the preflight check reads it."""

    def apply(self, manifest: Mapping[str, Any]) -> ClusterResource:
        """Apply ``manifest`` and return the resource it created."""

    def delete(self, resource: ClusterResource) -> None:
        """Remove ``resource``, raising when it is still there afterwards."""

    def active_faults(self) -> tuple[ClusterResource, ...]:
        """Return every fault this suite currently has applied."""

    def observe(self, probe: str, *, namespace: str = "") -> ProbeReading:
        """Return the symptoms ``probe`` can see right now."""


def suite_labels(experiment_id: str = "") -> dict[str, str]:
    """Return the labels every resource this suite applies must carry.

    The sweep in ``cleanup`` finds orphans by these and nothing else, so a
    manifest that reaches the cluster without them is a fault no killed run can
    be recovered from.
    """
    labels = {CHAOS_SUITE_LABEL: CHAOS_SUITE_LABEL_VALUE}
    if experiment_id:
        labels[CHAOS_EXPERIMENT_LABEL] = experiment_id
    return labels


def is_suite_resource(resource: ClusterResource) -> bool:
    """Return whether ``resource`` was applied by this suite."""
    return resource.labels.get(CHAOS_SUITE_LABEL) == CHAOS_SUITE_LABEL_VALUE


# --- availability ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Availability:
    """Whether the chaos suite can run at all, and why not when it cannot."""

    available: bool
    reason: str = ""
    context: str = ""


#: How availability finds an executable. Injectable so the decision can be
#: asserted on a machine that happens to have — or not have — the real one.
Which = Callable[[str], str | None]

#: How availability asks whether the cluster answers: ``(reachable, detail)``,
#: where the detail is the context name when it did and the error when it did not.
Reach = Callable[[], tuple[bool, str]]


def _kubectl_reach(runner: CommandRunner, *, kubeconfig: str = "", context: str = "") -> Reach:
    """Return a reach probe that asks the real cluster whether it is there."""

    def reach() -> tuple[bool, str]:
        argv = [KUBECTL]
        if kubeconfig:
            argv += ["--kubeconfig", kubeconfig]
        if context:
            argv += ["--context", context]
        result = runner.run([*argv, "cluster-info"], timeout=CHAOS_PREFLIGHT_TIMEOUT_SECONDS)
        if not result.ok:
            return False, result.message
        named = runner.run([*argv, "config", "current-context"], timeout=10.0)
        return True, (named.stdout.strip() if named.ok else context)

    return reach


def cluster_availability(
    *,
    which: Which = shutil.which,
    reach: Reach | None = None,
    runner: CommandRunner | None = None,
    kubeconfig: str = "",
    context: str = "",
) -> Availability:
    """Return whether a cluster is there, with a sentence saying what to do if not.

    The two failure modes are reported apart because the remedies differ: no
    ``kubectl`` is something to install, and an unreachable cluster is something
    to start. A single "no cluster available" would send half the people who
    read it to the wrong place.
    """
    if which(KUBECTL) is None:
        return Availability(
            available=False,
            reason=(
                f"the chaos suite needs a Kubernetes cluster and {KUBECTL!r} is not on PATH; "
                f"run {CHAOS_SETUP_COMMAND!r} to create a local one"
            ),
        )

    probe = (
        reach
        if reach is not None
        else _kubectl_reach(
            runner if runner is not None else SubprocessRunner(),
            kubeconfig=kubeconfig,
            context=context,
        )
    )
    reachable, detail = probe()
    if not reachable:
        return Availability(
            available=False,
            reason=(
                f"the chaos suite needs a reachable Kubernetes cluster and {KUBECTL} could not "
                f"talk to one: {detail}; run {CHAOS_SETUP_COMMAND!r} to create a local one"
            ),
        )
    return Availability(available=True, context=detail)


def skip_reason(availability: Availability) -> str:
    """Return the message a suite skips with, or ``""`` when it can run.

    One function so the decision and the message cannot drift apart: a module
    that skipped on its own condition and printed this one's sentence would
    eventually print a reason that was not the reason.
    """
    return "" if availability.available else availability.reason


__all__ = [
    "CHAOS_SETUP_COMMAND",
    "KUBECTL",
    "Availability",
    "Cluster",
    "ClusterHealth",
    "ClusterResource",
    "ProbeReading",
    "Reach",
    "SymptomSource",
    "Which",
    "cluster_availability",
    "is_suite_resource",
    "skip_reason",
    "suite_labels",
]
