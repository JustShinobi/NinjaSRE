"""The eight mechanisms that can be removed, and what removing each one touches.

Every switch here reaches a control its owning feature already publishes. That
is not tidiness — it is the difference between measuring the mechanism and
measuring a second implementation of it. Four of the eight ship a named switch
of their own (``MemoryPolicy``, ``StrategyPolicy``, ``KnowledgePolicy``); the
other four have a documented "off" position that predates this harness: masking
has a level, the ranker has a neutral port, the seed catalogue ships empty, and
a deployment with no specialists passes none.

**The trace is the proof.** Each mechanism declares which keys it moves in the
run's configuration summary, and SC-004 is asserted by flipping one switch and
checking that exactly those keys moved. An arm that differed from the baseline in
two respects would attribute the sum of both contributions to one mechanism, and
nothing in the resulting table would say so.

**Nothing here is global.** ``MechanismSwitches`` is frozen and ``without``
returns a new one, so an arm cannot leave a switch flipped for the arm after it —
which is exactly the bug that would make a results table quietly wrong.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Final, TypeVar

from config.constants.evaluation import ABLATION_MECHANISMS
from core.agent.seed_calls import EMPTY_SEED_CATALOGUE, SeedCatalogue
from core.pipeline.ports import UNRANKED
from platform.knowledge.policy import KNOWLEDGE_SWITCH, TOPOLOGY_SWITCH, KnowledgePolicy
from platform.masking.policy import MaskingLevel, MaskingPolicy
from platform.memory.policy import MEMORY_READ_SWITCH, MemoryPolicy
from platform.memory.strategy.policy import STRATEGY_SWITCH, StrategyPolicy

#: The three mechanisms whose control is a runtime construction argument rather
#: than a published policy object. Named here so the switch table can say so.
SUBAGENTS_SWITCH: Final = "subagents"
SEED_CALLS_SWITCH: Final = "seed_calls"
CAPABILITY_PLANNING_SWITCH: Final = "capability_planning"
MASKING_SWITCH: Final = "masking"


class UnknownMechanism(ValueError):
    """A mechanism nobody defined was asked to be switched off.

    Raised rather than ignored, for the reason each owning feature already
    raises: an ablation that silently skipped an axis would publish a table
    saying it measured something it never varied, which is worse than not
    measuring it at all.
    """

    def __init__(self, names: Sequence[str]) -> None:
        self.names = tuple(names)
        super().__init__(
            f"unknown ablation mechanism(s) {', '.join(sorted(self.names))}; expected one of "
            f"{', '.join(ABLATION_MECHANISMS)}"
        )


@dataclass(frozen=True, slots=True)
class Mechanism:
    """One thing that can be removed, and everything a reader needs about it."""

    name: str
    summary: str
    control: str
    owner: str
    trace_keys: tuple[str, ...]


#: The eight, in the order a report lists them: the three learning mechanisms
#: first, because they are what Article VII is about, then the stores, then the
#: runtime's own economies.
MECHANISMS: Final[tuple[Mechanism, ...]] = (
    Mechanism(
        name=MEMORY_READ_SWITCH,
        summary="Recalling previous investigations of the same failure.",
        control="MemoryPolicy.read_enabled — the guidance hook is not installed",
        owner="platform.memory",
        trace_keys=("memory_read_enabled",),
    ),
    Mechanism(
        name=STRATEGY_SWITCH,
        summary="Synthesising a playbook from the episodes and serving it with recall.",
        control="StrategyPolicy.enabled — generation and retrieval together",
        owner="platform.memory.strategy",
        trace_keys=("memory_strategy_enabled",),
    ),
    Mechanism(
        name=TOPOLOGY_SWITCH,
        summary="Consulting the service dependency graph when scoping an incident.",
        control="KnowledgePolicy.topology_enabled — the retrieval path is unreachable",
        owner="platform.knowledge",
        trace_keys=("topology_enabled",),
    ),
    Mechanism(
        name=KNOWLEDGE_SWITCH,
        summary="Searching the runbook and documentation corpus.",
        control="KnowledgePolicy.knowledge_enabled — the guidance is not appended",
        owner="platform.knowledge",
        trace_keys=("knowledge_enabled",),
    ),
    Mechanism(
        name=MASKING_SWITCH,
        summary="Replacing infrastructure identifiers before they reach the model.",
        control="MaskingPolicy at level 'off' — nothing is replaced",
        owner="platform.masking",
        trace_keys=("masking_level",),
    ),
    Mechanism(
        name=SUBAGENTS_SWITCH,
        summary="Dispatching a specialist to look at one thing in its own context.",
        control="no specialists are offered to the loop, so dispatch is not a tool",
        owner="core.agent.subagents",
        trace_keys=("subagents_enabled",),
    ),
    Mechanism(
        name=SEED_CALLS_SWITCH,
        summary="Deterministic first calls implied by the alert's source.",
        control="the empty seed catalogue — every source starts cold",
        owner="core.agent.seed_calls",
        trace_keys=("seed_calls_enabled",),
    ),
    Mechanism(
        name=CAPABILITY_PLANNING_SWITCH,
        summary="Ranking the catalogue before the loop sees it.",
        control="the unranked capability port — the catalogue arrives in its own order",
        owner="core.pipeline.stages.plan_evidence",
        trace_keys=("capability_planning_enabled",),
    ),
)

_BY_NAME: Final[dict[str, Mechanism]] = {found.name: found for found in MECHANISMS}


def mechanism(name: str) -> Mechanism:
    """Return the mechanism called ``name``.

    Raises:
        UnknownMechanism: naming what was asked for and what exists.
    """
    found = _BY_NAME.get(name)
    if found is None:
        raise UnknownMechanism((name,))
    return found


def check_mechanisms(names: Sequence[str]) -> tuple[str, ...]:
    """Return ``names``, or raise naming every one of them that is not a mechanism."""
    unknown = [name for name in names if name not in _BY_NAME]
    if unknown:
        raise UnknownMechanism(unknown)
    return tuple(names)


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class MechanismSwitches:
    """One arm's configuration: which of the eight are on, expressed as controls.

    Frozen, and ``without`` returns a new value. An arm that could flip a switch
    in place would leave it flipped for the arm after it, and the resulting table
    would attribute one mechanism's absence to another.
    """

    memory: MemoryPolicy = MemoryPolicy()
    strategies: StrategyPolicy = StrategyPolicy()
    knowledge: KnowledgePolicy = KnowledgePolicy()
    masking: MaskingPolicy = MaskingPolicy()
    subagents_enabled: bool = True
    seed_calls_enabled: bool = True
    capability_planning_enabled: bool = True

    def without(self, *names: str) -> MechanismSwitches:
        """Return this configuration with each named mechanism switched off.

        Raises:
            UnknownMechanism: one of ``names`` is not a mechanism.
        """
        wanted = set(check_mechanisms(names))
        return replace(
            self,
            memory=(
                self.memory.without(MEMORY_READ_SWITCH)
                if MEMORY_READ_SWITCH in wanted
                else self.memory
            ),
            strategies=(
                self.strategies.without(STRATEGY_SWITCH)
                if STRATEGY_SWITCH in wanted
                else self.strategies
            ),
            knowledge=self.knowledge.without(
                *(name for name in (TOPOLOGY_SWITCH, KNOWLEDGE_SWITCH) if name in wanted)
            ),
            masking=(
                MaskingPolicy.from_level(
                    MaskingLevel.OFF.value, custom_patterns=self.masking.custom_patterns
                )
                if MASKING_SWITCH in wanted
                else self.masking
            ),
            subagents_enabled=self.subagents_enabled and SUBAGENTS_SWITCH not in wanted,
            seed_calls_enabled=self.seed_calls_enabled and SEED_CALLS_SWITCH not in wanted,
            capability_planning_enabled=(
                self.capability_planning_enabled and CAPABILITY_PLANNING_SWITCH not in wanted
            ),
        )

    def enabled(self, name: str) -> bool:
        """Return whether the mechanism called ``name`` is on under this configuration."""
        mechanism(name)
        return {
            MEMORY_READ_SWITCH: self.memory.read_enabled,
            STRATEGY_SWITCH: self.strategies.enabled,
            TOPOLOGY_SWITCH: self.knowledge.topology_enabled,
            KNOWLEDGE_SWITCH: self.knowledge.knowledge_enabled,
            MASKING_SWITCH: self.masking.level is not MaskingLevel.OFF,
            SUBAGENTS_SWITCH: self.subagents_enabled,
            SEED_CALLS_SWITCH: self.seed_calls_enabled,
            CAPABILITY_PLANNING_SWITCH: self.capability_planning_enabled,
        }[name]

    def disabled_mechanisms(self) -> tuple[str, ...]:
        """Return every mechanism this configuration has switched off, in table order."""
        return tuple(found.name for found in MECHANISMS if not self.enabled(found.name))

    # -- reaching the owning feature's control ---------------------------------

    def seed_catalogue(self, catalogue: SeedCatalogue) -> SeedCatalogue:
        """Return the seed catalogue this arm's loop is built with.

        The empty one when seeds are off, which is the catalogue every source had
        before the feature existed — not a populated one the loop declines to
        read.
        """
        return catalogue if self.seed_calls_enabled else EMPTY_SEED_CATALOGUE

    def ranker(self, ranker: T) -> T | Any:
        """Return the capability ranker this arm's pipeline is built with.

        The neutral port when planning is off. A ranker that returned its input
        unchanged would still be a stage doing work, and the point of the arm is
        the code path a deployment without planning takes.
        """
        return ranker if self.capability_planning_enabled else UNRANKED

    def subagents(self, definitions: Sequence[T]) -> tuple[T, ...]:
        """Return the specialists this arm's loop is offered.

        None when sub-agents are off, so ``dispatch_subagent`` is not among the
        tools rather than being a tool that refuses.
        """
        return tuple(definitions) if self.subagents_enabled else ()

    # -- the trace -------------------------------------------------------------

    def trace_summary(self) -> dict[str, Any]:
        """Return the configuration this arm ran under, for comparison against another.

        The configuration, never the outcome. "Recall was off" and "recall found
        nothing" are different facts, and an ablation table that could not tell
        them apart would be unreadable — which is why each owning feature already
        draws that line and this merges what they say rather than restating it.
        """
        return {
            **self.memory.trace_summary(),
            **self.strategies.trace_summary(),
            **self.knowledge.trace_summary(),
            "masking_level": self.masking.level.value,
            "subagents_enabled": self.subagents_enabled,
            "seed_calls_enabled": self.seed_calls_enabled,
            "capability_planning_enabled": self.capability_planning_enabled,
        }


__all__ = [
    "CAPABILITY_PLANNING_SWITCH",
    "MASKING_SWITCH",
    "MECHANISMS",
    "SEED_CALLS_SWITCH",
    "SUBAGENTS_SWITCH",
    "Mechanism",
    "MechanismSwitches",
    "UnknownMechanism",
    "check_mechanisms",
    "mechanism",
]
