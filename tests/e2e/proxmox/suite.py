"""Running the destructive half, and saying which of it was real.

The one thing this suite must never do is let a reader believe a number came
from hardware when it came from a recording. So every outcome carries its mode,
the report states both sets by name, and the mode is decided by whether a
laboratory was configured rather than by a flag somebody can pass.

Restore happens between scenarios rather than after the suite, and a cluster
that does not come back stops the run — because everything after that point
would be a measurement of a broken cluster, reported as a measurement of the
system.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from config.constants.hypervisor_scenarios import (
    NINJASRE_PROXMOX_LABORATORY_ENV,
    SCENARIO_MODE_FIXTURE,
    SCENARIO_MODE_LABORATORY,
)
from tests.e2e.proxmox.rehearsal import REHEARSALS, Rehearsal, unknown_rehearsals, unrehearsed
from tests.harness.proxmox.declaration import Scenario
from tests.harness.proxmox.laboratory import (
    LABORATORY,
    LaboratoryCluster,
    LaboratoryDriver,
    LaboratoryOutcome,
    RecordedLaboratory,
    run_destructive,
)
from tests.harness.proxmox.suite import CORPUS_ROOT, load_corpus


def configured_laboratory() -> str:
    """Return the laboratory this machine may break, or the empty string."""
    return os.environ.get(NINJASRE_PROXMOX_LABORATORY_ENV, "").strip()


def skip_reason() -> str:
    """Return why the real laboratory cannot be used here, or the empty string.

    A sentence rather than a boolean, because "no infrastructure" sends somebody
    who has a cluster and no environment variable to the wrong place.
    """
    if configured_laboratory():
        return ""
    return (
        f"no laboratory cluster is configured: set {NINJASRE_PROXMOX_LABORATORY_ENV} to the "
        f"cluster this machine is allowed to break, or run 'make e2e-proxmox-laboratory', "
        f"which reports what it would do against the recorded stand-in instead"
    )


@dataclass(frozen=True, slots=True)
class RehearsalOutcome:
    """One hypervisor write, run against something, and what happened."""

    capability: str
    mode: str
    performed: bool = False
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the report carries."""
        return {
            "capability": self.capability,
            "mode": self.mode,
            "performed": self.performed,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class LaboratoryReport:
    """What the destructive half did, and which of it touched hardware."""

    mode: str = SCENARIO_MODE_FIXTURE
    cluster: LaboratoryCluster = LABORATORY
    scenarios: tuple[LaboratoryOutcome, ...] = ()
    rehearsals: tuple[RehearsalOutcome, ...] = ()
    unrehearsed_capabilities: tuple[str, ...] = field(default=())

    @property
    def real(self) -> bool:
        """Return whether this run touched the laboratory cluster."""
        return self.mode == SCENARIO_MODE_LABORATORY

    @property
    def simulated_scenarios(self) -> tuple[str, ...]:
        """Return the scenarios that ran against the recorded stand-in."""
        return () if self.real else tuple(found.scenario_id for found in self.scenarios)

    @property
    def real_scenarios(self) -> tuple[str, ...]:
        """Return the scenarios that ran against the cluster."""
        return tuple(found.scenario_id for found in self.scenarios) if self.real else ()

    def describe(self) -> str:
        """Return the statement a release note quotes: what was real, what was not."""
        heading = (
            f"laboratory: {self.cluster.name} ({', '.join(self.cluster.addresses)})"
            if self.real
            else "laboratory: none configured — every scenario below was simulated"
        )
        lines = [
            heading,
            f"destructive scenarios: {len(self.scenarios)} "
            f"({len(self.real_scenarios)} real, {len(self.simulated_scenarios)} simulated)",
            f"recovered from a failed first restore: "
            f"{sum(1 for found in self.scenarios if found.recovered)}",
            f"hypervisor writes rehearsed: "
            f"{sum(1 for found in self.rehearsals if found.performed)} of {len(REHEARSALS)}",
        ]
        if self.unrehearsed_capabilities:
            lines.append(f"writes with no rehearsal at all: {self.unrehearsed_capabilities}")
        lines.extend(f"  {found.scenario_id}: {self.mode}" for found in self.scenarios)
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable report."""
        return {
            "mode": self.mode,
            "cluster": self.cluster.name,
            "real_scenarios": list(self.real_scenarios),
            "simulated_scenarios": list(self.simulated_scenarios),
            "scenarios": [found.to_record() for found in self.scenarios],
            "rehearsals": [found.to_record() for found in self.rehearsals],
            "unrehearsed": list(self.unrehearsed_capabilities),
        }


def destructive_scenarios(root: Path = CORPUS_ROOT) -> tuple[Scenario, ...]:
    """Return the corpus scenarios that also run against the laboratory."""
    return tuple(scenario for scenario, _ in load_corpus(root) if scenario.destructive)


async def rehearse(
    rehearsals: Sequence[Rehearsal],
    *,
    driver: LaboratoryDriver,
    cluster: LaboratoryCluster,
    mode: str,
) -> tuple[RehearsalOutcome, ...]:
    """Run each write's rehearsal, restoring the cluster after every one.

    Raises:
        LaboratoryUnusable: the cluster did not return to its known state.
    """
    from tests.harness.proxmox.laboratory import LaboratoryUnusable

    outcomes: list[RehearsalOutcome] = []
    for found in rehearsals:
        before = await driver.health()
        if not before.usable:
            raise LaboratoryUnusable(found.capability, f"before it ran: {before.detail}")

        await driver.apply(found.arrange)
        await driver.restore(cluster.known_state)
        after = await driver.health()
        if not after.usable:
            await driver.restore(cluster.known_state)
            after = await driver.health()
        if not after.usable:
            raise LaboratoryUnusable(found.capability, after.detail)

        outcomes.append(
            RehearsalOutcome(
                capability=found.capability,
                mode=mode,
                performed=True,
                detail=found.expects,
            )
        )
    return tuple(outcomes)


async def run_laboratory(
    root: Path = CORPUS_ROOT,
    *,
    driver: LaboratoryDriver | None = None,
    cluster: LaboratoryCluster = LABORATORY,
) -> LaboratoryReport:
    """Run every destructive scenario and every rehearsal, and report the mode.

    ``driver`` of ``None`` means "decide from the environment": a configured
    laboratory is used, and otherwise the recorded stand-in is, which is what
    keeps the restore path exercised on a machine that has no rack.
    """
    mode = SCENARIO_MODE_LABORATORY if configured_laboratory() else SCENARIO_MODE_FIXTURE
    if driver is None:
        driver = RecordedLaboratory(known_state=cluster.known_state)
        mode = SCENARIO_MODE_FIXTURE

    scenarios = await run_destructive(destructive_scenarios(root), driver=driver, cluster=cluster)
    rehearsals = await rehearse(REHEARSALS, driver=driver, cluster=cluster, mode=mode)
    return LaboratoryReport(
        mode=mode,
        cluster=cluster,
        # The mode is stamped on every outcome rather than left to the report's
        # header, because an outcome is the thing that gets quoted out of
        # context — and an outcome that does not say whether it was real is
        # exactly the sentence somebody repeats wrongly.
        scenarios=tuple(replace(found, mode=mode) for found in scenarios),
        rehearsals=rehearsals,
        unrehearsed_capabilities=unrehearsed() + unknown_rehearsals(),
    )


__all__ = [
    "LaboratoryReport",
    "RehearsalOutcome",
    "configured_laboratory",
    "destructive_scenarios",
    "rehearse",
    "run_laboratory",
    "skip_reason",
]
