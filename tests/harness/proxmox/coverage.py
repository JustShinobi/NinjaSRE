"""Every hypervisor write, exercised by a scenario — asserted rather than intended.

Feature 046 ships thirteen actions that write to somebody's hypervisor. An
action with no scenario is an action nobody has scored, and under deadline that
is the one that ships. So coverage is a test rather than a convention.

The second function here is what stops the first from being satisfied by editing
a list. A scenario's ``exercises`` is a claim, and a claim is only worth
something if it can be false: an entry counts when the scenario *asks* for that
capability, when a red herring's temptation is to run it, or when one of the
recorded runs proposed it and was scored for doing so. Anything else is a name in
a file, and a coverage number built out of names in files is the most
comfortable kind of wrong.
"""

from __future__ import annotations

from collections.abc import Sequence

from tests.harness.proxmox.declaration import Scenario, declared_capabilities
from tests.harness.proxmox.transcripts import RecordedRun
from tests.harness.proxmox.verdicts import ResponseKind

#: One loaded scenario and every run recorded against it, as the suite yields it.
Entry = tuple[Scenario, tuple[RecordedRun, ...]]


def touched(scenario: Scenario, runs: Sequence[RecordedRun]) -> frozenset[str]:
    """Return every capability this scenario genuinely brings into a score."""
    names: set[str] = set()
    if scenario.response.kind is ResponseKind.ACT:
        names.add(scenario.response.capability)
    names.update(found.tempting for found in scenario.red_herrings if found.tempting)
    names.update(run.action.capability for run in runs if run.action.capability)
    return frozenset(names)


def exercised(corpus: Sequence[Entry]) -> frozenset[str]:
    """Return every hypervisor write some scenario in ``corpus`` actually scores."""
    covered: set[str] = set()
    for scenario, runs in corpus:
        covered |= touched(scenario, runs) & declared_capabilities()
    return frozenset(covered)


def uncovered(corpus: Sequence[Entry]) -> tuple[str, ...]:
    """Return the declared writes no scenario exercises, in name order."""
    return tuple(sorted(declared_capabilities() - exercised(corpus)))


def unjustified_claims(corpus: Sequence[Entry]) -> tuple[str, ...]:
    """Return every ``scenario: capability`` claimed and not brought into a score."""
    problems: list[str] = []
    for scenario, runs in corpus:
        real = touched(scenario, runs)
        problems.extend(
            f"{scenario.scenario_id}: {name}" for name in sorted(set(scenario.exercises) - real)
        )
    return tuple(problems)


def describe(corpus: Sequence[Entry]) -> str:
    """Return the block a coverage report prints: each write and where it is scored."""
    where: dict[str, list[str]] = {name: [] for name in sorted(declared_capabilities())}
    for scenario, runs in corpus:
        for name in sorted(touched(scenario, runs) & declared_capabilities()):
            where[name].append(scenario.scenario_id)
    return "\n".join(
        f"{name}: {', '.join(found) if found else 'NO SCENARIO'}" for name, found in where.items()
    )


__all__ = ["Entry", "describe", "exercised", "touched", "uncovered", "unjustified_claims"]
