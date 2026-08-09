"""What a hypervisor scenario has to declare before it may be scored.

The specification's first requirement is a list of six things — the situation,
the fixtures or the laboratory setup that produces it, the true root cause, the
evidence a correct diagnosis rests on, the correct response, and the red
herrings. This module is that list, made unskippable: a scenario missing any of
them raises where it is written rather than scoring against a gap.

**The correct response is declared, not derived.** It is reviewed once, when the
scenario is written, by somebody thinking about the cluster rather than about the
run in front of them. Deriving it at scoring time would make every argument about
a score an argument about what should have happened, which is how a suite stops
being useful and becomes a thing people relitigate.

**A capability a scenario names has to be one this deployment ships.** The
hypervisor write set is thirteen actions with a risk table behind it; a scenario
naming a fourteenth is either a typo or an action nobody classified, and both
should fail at load.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.constants.hypervisor_scenarios import (
    HYPERVISOR_SCENARIO_DOMAINS,
    SCENARIO_MODE_FIXTURE,
    SCENARIO_MODE_LABORATORY,
    SCENARIO_MODES,
)
from tests.harness.proxmox.verdicts import ResponseKind


def declared_capabilities() -> frozenset[str]:
    """Return every hypervisor write this deployment declares.

    Read from the shipped declarations rather than restated here, because the
    coverage test's whole claim is that a capability cannot be added without a
    scenario — and a second list would let it be added to only one of them.
    """
    from capabilities.tools.remediation.proxmox import DECLARATIONS

    return frozenset(DECLARATIONS)


class ScenarioError(Exception):
    """A scenario declaration is incomplete or names something that is not there.

    Carries the scenario it belongs to so a corpus-wide load failure says which
    directory to open, rather than which field of which anonymous document.
    """

    def __init__(self, scenario_id: str, problem: str) -> None:
        self.scenario_id = scenario_id
        self.problem = problem
        super().__init__(f"{scenario_id or '<unnamed scenario>'}: {problem}")


@dataclass(frozen=True, slots=True)
class Truth:
    """The cause, and the readings a correct diagnosis has to have rested on.

    ``insufficient`` is a first-class answer rather than an absent one. A
    scenario whose readings genuinely do not support a conclusion is one where
    saying so is correct and a confident diagnosis is wrong, and without it every
    scoring scheme rewards confidence.
    """

    root_cause: str = ""
    #: Substrings of what the run cited. Substrings rather than identifiers,
    #: because the thing being asserted is that the conclusion quoted the reading
    #: — "quorate: no" — and an identifier would let a run cite the tool without
    #: citing anything it said.
    evidence: tuple[str, ...] = ()
    insufficient: bool = False
    summary: str = ""

    def __post_init__(self) -> None:
        if self.insufficient:
            if self.root_cause or self.evidence:
                raise ValueError(
                    "a scenario whose evidence is insufficient cannot also declare the cause "
                    "that evidence would have established; declare one or the other"
                )
            return
        if not self.root_cause.strip():
            raise ValueError("a scenario needs the true root cause it is scored against")
        if not self.evidence:
            raise ValueError(
                "a scenario needs the evidence a correct diagnosis rests on; without it a "
                "right answer from a lucky prior scores as a right answer"
            )


@dataclass(frozen=True, slots=True)
class CorrectResponse:
    """What the system should have done, and why that is the answer.

    ``why`` is required. The reasoning is what a reviewer checks the
    classification against a year later, and a scenario that asserts "escalate"
    with no argument is one nobody can defend when somebody wants the number to
    move.
    """

    kind: ResponseKind
    why: str
    capability: str = ""

    def __post_init__(self) -> None:
        if not self.why.strip():
            raise ValueError("a correct response needs the reasoning behind it")
        if self.kind is ResponseKind.ACT:
            if not self.capability:
                raise ValueError("a response of 'act' has to name the capability that acts")
            if self.capability not in declared_capabilities():
                raise ValueError(
                    f"{self.capability!r} is not a hypervisor write this deployment declares; "
                    f"it declares {', '.join(sorted(declared_capabilities()))}"
                )
        elif self.capability:
            raise ValueError(
                f"a response of {self.kind.value!r} names {self.capability!r}, which is a "
                f"capability it would not run; a response either acts or does not"
            )


@dataclass(frozen=True, slots=True)
class RedHerring:
    """A plausible wrong path the scenario plants on purpose.

    ``tempting`` names what taking the bait would lead somebody to do. It is not
    scored directly — the run says which herrings it followed — but it is what
    makes a red herring reviewable: a confounder nobody could say what it would
    cause is a decoration rather than a trap.
    """

    name: str
    why: str
    tempting: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.why.strip():
            raise ValueError("a red herring needs a name and the reason it is tempting")


@dataclass(frozen=True, slots=True)
class Fixtures:
    """Which recorded cluster a scenario reads, and what it overlays on it.

    The baseline is the reference cluster in one of its recorded states; the
    overlay is the one or two readings this scenario is actually about. Writing
    each scenario's whole cluster out would make a change to the reference
    cluster a change to twenty-eight files, most of which nobody would re-check.
    """

    cluster_state: str = "healthy"
    responses: Mapping[str, Any] = field(default_factory=dict)
    unreachable: bool = False

    def overlaid(self) -> dict[str, Any]:
        """Return the overlay as a plain mutable mapping the transport takes."""
        return dict(self.responses)


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One investigation tool a scenario runs, and the arguments it runs it with."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReadingsPlan:
    """The tools that produce this scenario's readings, and what they must say.

    ``must_report`` is what makes the corpus load-bearing rather than decorative.
    The tools are the shipped ones and they run for real over the recorded
    responses, so a change to a tool's synthesis that stops it reporting "quorum
    margin 0" fails here, in the change that caused it, naming the scenario.
    """

    tools: tuple[ToolCall, ...] = ()
    must_report: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LaboratorySetup:
    """How a destructive scenario is produced on a real cluster, and undone.

    Both halves are required. A fault with no restore is a scenario that can be
    run once, and a laboratory that ends every release cycle needing a rebuild is
    a laboratory nobody keeps.
    """

    fault: str
    restore: str
    #: What the cluster is left unable to do while the fault is in place, so the
    #: suite can order the destructive scenarios rather than discovering halfway
    #: through that the previous one took the API away.
    disables: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.fault.strip() or not self.restore.strip():
            raise ValueError(
                "a laboratory scenario needs both the fault that produces it and the restore "
                "that undoes it; a fault with no restore can be run once"
            )


@dataclass(frozen=True, slots=True)
class Scenario:
    """One hypervisor failure: what it is, what can be seen, and what to do.

    Everything the specification's first requirement lists, in one value, with
    the checking in ``__post_init__`` rather than in a validator somebody has to
    remember to call.
    """

    scenario_id: str
    domain: str
    title: str
    situation: str
    truth: Truth
    response: CorrectResponse
    difficulty: int = 2
    modes: tuple[str, ...] = (SCENARIO_MODE_FIXTURE,)
    fixtures: Fixtures = field(default_factory=Fixtures)
    readings: ReadingsPlan = field(default_factory=ReadingsPlan)
    laboratory: LaboratorySetup | None = None
    red_herrings: tuple[RedHerring, ...] = ()
    #: The hypervisor writes this scenario scores, whether by asking for one or
    #: by scoring a run that proposed one. This is what the coverage test reads.
    exercises: tuple[str, ...] = ()
    #: The dated incident this scenario was drawn from, where one exists. Real
    #: incidents come with a known cause, a known correct response, and a record
    #: of what the responders tried first — which is the part nobody synthesises.
    postmortem: str = ""
    directory: Path | None = None

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ScenarioError("", "a scenario needs an identifier")
        if self.domain not in HYPERVISOR_SCENARIO_DOMAINS:
            raise ScenarioError(
                self.scenario_id,
                f"domain {self.domain!r} is not one of {', '.join(HYPERVISOR_SCENARIO_DOMAINS)}",
            )
        if not self.situation.strip():
            raise ScenarioError(self.scenario_id, "a scenario needs the situation it describes")
        for mode in self.modes:
            if mode not in SCENARIO_MODES:
                raise ScenarioError(
                    self.scenario_id, f"mode {mode!r} is not one of {SCENARIO_MODES}"
                )
        if SCENARIO_MODE_FIXTURE not in self.modes:
            raise ScenarioError(
                self.scenario_id,
                "every scenario has to be runnable from recorded fixtures; a scenario only the "
                "laboratory can run is one CI never sees",
            )
        if self.destructive and self.laboratory is None:
            raise ScenarioError(
                self.scenario_id,
                "a scenario declared runnable against the laboratory has to say which fault "
                "produces it and how the cluster is restored afterwards",
            )
        unknown = sorted(set(self.exercises) - declared_capabilities())
        if unknown:
            raise ScenarioError(
                self.scenario_id,
                f"exercises {unknown}, which this deployment does not declare as a hypervisor "
                f"write; it declares {', '.join(sorted(declared_capabilities()))}",
            )
        if (
            self.response.kind is ResponseKind.ACT
            and self.response.capability not in self.exercises
        ):
            raise ScenarioError(
                self.scenario_id,
                f"asks for {self.response.capability!r} and does not list it under 'exercises', "
                f"so the coverage test would not count it",
            )

    @property
    def destructive(self) -> bool:
        """Return whether this scenario also runs against the laboratory cluster."""
        return SCENARIO_MODE_LABORATORY in self.modes

    @property
    def red_herring_names(self) -> frozenset[str]:
        """Return every confounder this scenario planted, by name."""
        return frozenset(found.name for found in self.red_herrings)

    def describe(self) -> str:
        """Return the one line a report prints above a failing score."""
        return f"{self.domain}/{self.scenario_id} — {self.title}"


def scenarios_by_id(scenarios: Sequence[Scenario]) -> dict[str, Scenario]:
    """Return ``scenarios`` keyed by identifier, refusing a duplicate.

    Raises:
        ScenarioError: two scenarios share an identifier, which would make one of
            them invisible in every report that keys by it.
    """
    found: dict[str, Scenario] = {}
    for scenario in scenarios:
        if scenario.scenario_id in found:
            raise ScenarioError(scenario.scenario_id, "is declared twice in the corpus")
        found[scenario.scenario_id] = scenario
    return found


__all__ = [
    "CorrectResponse",
    "Fixtures",
    "LaboratorySetup",
    "ReadingsPlan",
    "RedHerring",
    "Scenario",
    "ScenarioError",
    "ToolCall",
    "Truth",
    "declared_capabilities",
    "scenarios_by_id",
]
