"""The two-node cluster the destructive scenarios need, and getting it back.

Some of these scenarios cannot be faked. A thin pool whose metadata is genuinely
exhausted behaves differently from a recording of one, and the difference is
exactly where a system that acts is most likely to be wrong. So they run against
a laboratory — before a release, not on every commit — and the suite states which
of them ran for real.

Three properties make that a laboratory somebody keeps rather than one that rots.

**The definition is a value.** Two nodes, their addresses, and the snapshot that
is the known state. A laboratory described in a runbook is a laboratory whose
description is wrong within a month.

**Restore happens between scenarios, not after the suite.** A destructive
scenario that leaves the cluster in a state the next one reads would make the
second scenario's readings a function of the first's, which is the end of
reproducibility.

**A scenario that leaves the cluster unusable is recovered from, or the suite
stops.** Carrying on after a failed restore produces a run whose remaining
results are all measurements of a broken cluster, reported as measurements of the
system. Stopping is the honest answer, and it names the scenario that did it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.hypervisor_scenarios import SCENARIO_MODE_LABORATORY
from tests.harness.proxmox.declaration import Scenario


class LaboratoryUnusable(Exception):
    """The laboratory did not come back, so nothing after this is a measurement."""

    def __init__(self, scenario_id: str, detail: str) -> None:
        self.scenario_id = scenario_id
        self.detail = detail
        super().__init__(
            f"the laboratory cluster did not return to its known state after {scenario_id}: "
            f"{detail}. Every scenario after this one would be measuring a broken cluster, so "
            f"the run stops here."
        )


@dataclass(frozen=True, slots=True)
class LaboratoryNode:
    """One node of the laboratory, as the suite addresses it."""

    name: str
    address: str
    role: str = "member"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.address.strip():
            raise ValueError("a laboratory node needs a name and an address")


@dataclass(frozen=True, slots=True)
class LaboratoryCluster:
    """The cluster the destructive scenarios are run against.

    Two nodes rather than three, deliberately. The interesting failures of a
    homelab hypervisor are the ones a two-node cluster has and a three-node one
    does not — a quorum margin of zero, an unreachable peer that cannot be told
    from a dead one — and a laboratory with a comfortable majority would score
    the system on a cluster nobody has.
    """

    name: str
    nodes: tuple[LaboratoryNode, ...]
    #: The snapshot every destructive scenario is restored to. Named rather than
    #: implied, because "the known state" has to be a thing somebody can point at.
    known_state: str
    #: Whether a quorum device contributes a vote. False on the reference
    #: cluster, and that is the condition several scenarios turn on.
    quorum_device: bool = False

    def __post_init__(self) -> None:
        if len(self.nodes) != 2:
            raise ValueError(
                f"{self.name}: the laboratory is a two-node cluster and this one has "
                f"{len(self.nodes)}. The failures worth measuring here are the ones a majority "
                f"would hide."
            )
        if not self.known_state.strip():
            raise ValueError(
                f"{self.name}: a laboratory needs the named state it is restored to between "
                f"destructive scenarios, or the second scenario reads the first one's damage"
            )

    @property
    def addresses(self) -> tuple[str, ...]:
        """Return every node's address, in declared order."""
        return tuple(node.address for node in self.nodes)


#: The laboratory this repository's destructive scenarios are written against.
#: Two nodes, no contributing quorum device, and one snapshot per node that both
#: are rolled back to. It mirrors the reference cluster because a laboratory that
#: differed from the estate would measure a system nobody runs.
LABORATORY: LaboratoryCluster = LaboratoryCluster(
    name="HAL9000-lab",
    nodes=(
        LaboratoryNode(name="lab01", address="192.168.90.11", role="primary"),
        LaboratoryNode(name="lab02", address="192.168.90.12", role="secondary"),
    ),
    known_state="scenario-baseline",
)


@dataclass(frozen=True, slots=True)
class ClusterHealth:
    """Whether the laboratory is in a state the next scenario can be run from."""

    reachable: bool
    quorate: bool
    detail: str = ""

    @property
    def usable(self) -> bool:
        """Return whether a scenario may be started against this cluster."""
        return self.reachable and self.quorate

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the laboratory report carries."""
        return {"reachable": self.reachable, "quorate": self.quorate, "detail": self.detail}


@runtime_checkable
class LaboratoryDriver(Protocol):
    """What the suite needs a real laboratory to be able to do.

    A protocol rather than a class, because the thing on the other end is a
    cluster in somebody's rack and the suite must be able to run against a
    recorded stand-in without either half knowing which it has.
    """

    async def health(self) -> ClusterHealth:
        """Return whether the cluster is in a state a scenario can start from."""

    async def apply(self, fault: str) -> None:
        """Put the cluster into the state ``fault`` describes."""

    async def restore(self, known_state: str) -> None:
        """Return the cluster to ``known_state``, whatever was done to it."""

    async def capture(self, paths: Sequence[str]) -> dict[str, Any]:
        """Return the cluster's current answer to each of ``paths``."""


@dataclass(frozen=True, slots=True)
class LaboratoryOutcome:
    """What happened to the cluster while one destructive scenario ran."""

    scenario_id: str
    mode: str = SCENARIO_MODE_LABORATORY
    before: ClusterHealth = ClusterHealth(reachable=True, quorate=True)
    after_fault: ClusterHealth = ClusterHealth(reachable=True, quorate=True)
    after_restore: ClusterHealth = ClusterHealth(reachable=True, quorate=True)
    #: Whether the restore had to be repeated because the first one did not take.
    recovered: bool = False

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the laboratory report carries."""
        return {
            "scenario": self.scenario_id,
            "mode": self.mode,
            "before": self.before.to_record(),
            "after_fault": self.after_fault.to_record(),
            "after_restore": self.after_restore.to_record(),
            "recovered": self.recovered,
        }


@dataclass(slots=True)
class RecordedLaboratory:
    """A laboratory that is not there, answering from the recorded cluster.

    This is what makes FR-003 true of the destructive scenarios as well: every
    scenario runs from fixtures with no cluster, and the ones that also run
    against hardware say so. It is also what exercises the restore path on the
    pull-request machine, so a broken restore is found before a release rather
    than during one.
    """

    known_state: str = LABORATORY.known_state
    #: Faults this stand-in refuses to come back from on the first attempt, which
    #: is how the recovery path is exercised rather than merely present.
    stubborn: frozenset[str] = frozenset()
    #: Faults nothing recovers from, which is the case the suite has to stop on.
    unrecoverable: frozenset[str] = frozenset()
    applied: list[str] = field(default_factory=list)
    restores: list[str] = field(default_factory=list)
    _broken: str = ""
    _attempts: int = 0

    async def health(self) -> ClusterHealth:
        """Return whether the stand-in believes the cluster is usable."""
        if not self._broken:
            return ClusterHealth(reachable=True, quorate=True)
        return ClusterHealth(
            reachable=False,
            quorate=False,
            detail=f"the cluster is still holding the fault {self._broken!r}",
        )

    async def apply(self, fault: str) -> None:
        """Record that ``fault`` was applied, and hold it."""
        self.applied.append(fault)
        self._broken = fault
        self._attempts = 0

    async def restore(self, known_state: str) -> None:
        """Roll back to ``known_state``, stubbornly where the fault says so."""
        self.restores.append(known_state)
        self._attempts += 1
        if self._broken in self.unrecoverable:
            return
        if self._broken in self.stubborn and self._attempts < 2:
            return
        self._broken = ""

    async def capture(self, paths: Sequence[str]) -> dict[str, Any]:
        """Return the recorded cluster's answer to each of ``paths``."""
        from tests.support.proxmox import ClusterState, recorded

        corpus = recorded(ClusterState.HEALTHY)
        captured: dict[str, Any] = {}
        for path in paths:
            try:
                captured[path] = corpus.payload(path)
            except KeyError:
                continue
        return captured


async def run_destructive(
    scenarios: Sequence[Scenario],
    *,
    driver: LaboratoryDriver,
    cluster: LaboratoryCluster = LABORATORY,
) -> tuple[LaboratoryOutcome, ...]:
    """Run each destructive scenario against the laboratory, restoring between them.

    Ordered as given, and the ordering matters: a scenario that takes the API
    away has to be followed by a restore before anything else reads. The restore
    is attempted twice before the run is abandoned, because a cluster that needs
    a second rollback is ordinary and one that needs a third is broken.

    Raises:
        LaboratoryUnusable: the cluster did not return to its known state, so
            nothing after this scenario would be a measurement.
    """
    outcomes: list[LaboratoryOutcome] = []
    for scenario in scenarios:
        if scenario.laboratory is None:  # pragma: no cover - refused at declaration
            continue

        before = await driver.health()
        if not before.usable:
            raise LaboratoryUnusable(scenario.scenario_id, f"before it ran: {before.detail}")

        await driver.apply(scenario.laboratory.fault)
        after_fault = await driver.health()

        await driver.restore(cluster.known_state)
        after_restore = await driver.health()
        recovered = False
        if not after_restore.usable:
            await driver.restore(cluster.known_state)
            after_restore = await driver.health()
            recovered = after_restore.usable
        if not after_restore.usable:
            raise LaboratoryUnusable(scenario.scenario_id, after_restore.detail)

        outcomes.append(
            LaboratoryOutcome(
                scenario_id=scenario.scenario_id,
                before=before,
                after_fault=after_fault,
                after_restore=after_restore,
                recovered=recovered,
            )
        )
    return tuple(outcomes)


__all__ = [
    "LABORATORY",
    "ClusterHealth",
    "LaboratoryCluster",
    "LaboratoryDriver",
    "LaboratoryNode",
    "LaboratoryOutcome",
    "LaboratoryUnusable",
    "RecordedLaboratory",
    "run_destructive",
]
