"""What a capability declares about itself, and what it is not allowed to omit.

Metadata here is not documentation. It is the input to four decisions the
system makes without asking anyone: whether a capability is relevant to this
incident, whether it may run without a human, what has to be stored before it
runs, and what the console shows an operator. A field left blank does not
degrade one of those decisions — it makes it silently wrong.

Hence the one hard rule. ``side_effect_level`` has no default, on purpose and
structurally: a tool that does not say what it does to the world cannot be
constructed at all. Every other conservative default in the system is a policy
someone could change; this one is arithmetic.

The scale itself carries the second rule. Anything above ``read_sensitive``
must also declare why a human is being asked and how the action is undone, and
that pair is checked here rather than at the approval gate — by the time the
gate runs, the tool is already in the catalogue and the omission is a runtime
surprise during an incident.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Protocol

from config.constants.autonomy import RISK_CLASSES
from config.constants.security import (
    SIDE_EFFECT_DESTRUCTIVE,
    SIDE_EFFECT_LEVELS,
    SIDE_EFFECT_READ,
    SIDE_EFFECT_READ_SENSITIVE,
    SIDE_EFFECT_WRITE_IRREVERSIBLE,
    SIDE_EFFECT_WRITE_REVERSIBLE,
)

#: A tool name as the model calls it. Lowercase with underscores, because every
#: provider dialect accepts that shape unchanged and the normaliser then has
#: nothing to rewrite — a renamed tool is a tool the trace cannot match back to
#: its declaration.
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

#: A skill name, which is an identifier rather than a callable symbol: the model
#: never emits it as a function name, so it may carry the hyphens that make a
#: directory listing of every shipped skill readable.
SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")

#: The permissive of the two, for code that has a capability of either kind.
CAPABILITY_NAME_PATTERN = SKILL_NAME_PATTERN


class CapabilityKind(StrEnum):
    """Which of the two kinds of capability a record describes."""

    TOOL = "tool"
    SKILL = "skill"


class SideEffectLevel(StrEnum):
    """What one invocation does to the world, least to most dangerous.

    The order is load-bearing. "Above ``read_sensitive``" is the line that
    decides approval and rollback, and it is expressed by comparing members
    rather than by listing them, so adding a level in the middle cannot leave
    one of the checks behind.
    """

    READ = SIDE_EFFECT_READ
    READ_SENSITIVE = SIDE_EFFECT_READ_SENSITIVE
    WRITE_REVERSIBLE = SIDE_EFFECT_WRITE_REVERSIBLE
    WRITE_IRREVERSIBLE = SIDE_EFFECT_WRITE_IRREVERSIBLE
    DESTRUCTIVE = SIDE_EFFECT_DESTRUCTIVE

    @property
    def danger(self) -> int:
        """Return the position on the scale, counting from the least dangerous."""
        return SIDE_EFFECT_LEVELS.index(self.value)

    @property
    def needs_approval(self) -> bool:
        """Return whether an invocation needs a human and a stored rollback plan."""
        return self.danger > SideEffectLevel.READ_SENSITIVE.danger

    # ``StrEnum`` inherits string comparison, which orders these alphabetically
    # — putting `destructive` first and `read` in the middle. Every ordering
    # operator is redefined rather than only ``__lt__``, because a partially
    # overridden set would leave `>=` silently comparing strings.

    def __lt__(self, other: object) -> bool:
        if isinstance(other, SideEffectLevel):
            return self.danger < other.danger
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, SideEffectLevel):
            return self.danger <= other.danger
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, SideEffectLevel):
            return self.danger > other.danger
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, SideEffectLevel):
            return self.danger >= other.danger
        return NotImplemented


class EvidenceType(StrEnum):
    """The kind of observation a capability produces.

    An investigation's conclusion is only as good as the mix of evidence behind
    it, and this is what lets the pipeline notice it has five metric readings
    and no change history.
    """

    LOG = "log"
    METRIC = "metric"
    TRACE = "trace"
    EVENT = "event"
    TOPOLOGY = "topology"
    CONFIGURATION = "configuration"
    CHANGE = "change"
    INCIDENT = "incident"
    DOCUMENT = "document"
    ANALYSIS = "analysis"


class EvidenceSource(StrEnum):
    """Names for the sources that belong to no vendor.

    Deliberately *not* the closed set of evidence sources. A vendor names its
    own — ``"datadog"``, ``"kubernetes"`` — and closing this enum would mean
    editing a central file for every integration, which is the single thing
    auto-discovery exists to avoid. These members are plain strings, so a
    declaration may use one of them or a vendor's literal interchangeably.
    """

    REASONING = "reasoning"
    MEMORY = "memory"
    KNOWLEDGE_BASE = "knowledge_base"
    RUNBOOK = "runbook"
    HUMAN = "human"
    SANDBOX = "sandbox"


def _frozen(values: Iterable[str] | None) -> tuple[str, ...]:
    """Return ``values`` as a tuple, with blanks dropped."""
    if values is None:
        return ()
    return tuple(str(value).strip() for value in values if str(value).strip())


@dataclass(frozen=True, slots=True)
class Requirements:
    """What has to be true of a deployment before a capability can run.

    Unmet requirements exclude a capability from a team's catalogue rather than
    failing it at call time. A model that can see a tool it will never be
    allowed to run wastes a turn discovering that, every turn.
    """

    integrations: tuple[str, ...] = ()
    sandbox_profiles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "integrations", _frozen(self.integrations))
        object.__setattr__(self, "sandbox_profiles", _frozen(self.sandbox_profiles))

    def __bool__(self) -> bool:
        """Return whether anything is required at all."""
        return bool(self.integrations or self.sandbox_profiles)

    def names(self) -> tuple[str, ...]:
        """Return every required name, whatever kind it is."""
        return self.integrations + self.sandbox_profiles


@dataclass(frozen=True, slots=True)
class AppliesWhen:
    """The situations a capability's author says it is for.

    Empty means "no claim", not "never" — a capability that declares nothing
    still competes on tags and use cases. Scoring reads this as evidence for,
    never as a filter, because a filter here would hide a tool the incident
    needed on the strength of an alert label somebody typed.
    """

    alert_sources: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "alert_sources", _frozen(self.alert_sources))
        object.__setattr__(self, "tags", _frozen(self.tags))
        object.__setattr__(self, "domains", _frozen(self.domains))


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """How one invocation is undone, produced before it is allowed to happen."""

    summary: str
    steps: tuple[str, ...] = ()
    reversible: bool = True

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("a rollback plan must summarise how the action is undone")
        object.__setattr__(self, "steps", _frozen(self.steps))


class RollbackPlanner(Protocol):
    """Turns one set of call arguments into the plan that undoes them.

    The contract lives here so a tool can declare it; the execution of a stored
    plan is a separate concern and a later feature. Declaring the planner at the
    same time as the side-effect level is what stops "we will add rollback
    later" from becoming a tool that ships without one.
    """

    def plan(self, arguments: Mapping[str, Any]) -> RollbackPlan:
        """Return the plan that reverses an invocation made with ``arguments``."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityMetadata:
    """What every capability declares, whichever kind it is.

    Never instantiated on its own: a capability is a tool or a skill, and the
    subclass is what fixes ``kind``. This exists so scoring, the read API, and
    the console can treat one catalogue as one catalogue.
    """

    kind: ClassVar[CapabilityKind]
    name_pattern: ClassVar[re.Pattern[str]] = CAPABILITY_NAME_PATTERN

    name: str
    display_name: str
    description: str
    domain: str = ""
    tags: tuple[str, ...] = ()
    use_cases: tuple[str, ...] = ()
    anti_examples: tuple[str, ...] = ()
    requires: Requirements = Requirements()

    def __post_init__(self) -> None:
        if not self.name_pattern.match(self.name):
            raise ValueError(
                f"capability name {self.name!r} does not match "
                f"{self.name_pattern.pattern} — it must be lowercase and start with a letter"
            )
        if not self.display_name.strip():
            raise ValueError(f"{self.name}: display_name must not be blank")
        if not self.description.strip():
            raise ValueError(f"{self.name}: description must not be blank")

        object.__setattr__(self, "domain", self.domain.strip())
        object.__setattr__(self, "tags", _frozen(self.tags))
        object.__setattr__(self, "use_cases", _frozen(self.use_cases))
        object.__setattr__(self, "anti_examples", _frozen(self.anti_examples))


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolMetadata(CapabilityMetadata):
    """A typed execution unit's declaration.

    ``side_effect_level`` and ``parallel_safe`` carry no default. Both describe
    something only the author knows, and both have a wrong answer that looks
    like a working tool right up until it is running five concurrent writes
    against production.
    """

    kind: ClassVar[CapabilityKind] = CapabilityKind.TOOL
    name_pattern: ClassVar[re.Pattern[str]] = TOOL_NAME_PATTERN

    evidence_source: str
    evidence_type: EvidenceType
    side_effect_level: SideEffectLevel
    parallel_safe: bool
    requires_approval: bool = False
    approval_reason: str = ""
    rollback_plan: str = ""
    rollback_planner: RollbackPlanner | None = None
    #: How dangerous one call is, on the closed scale the autonomy policy engine
    #: resolves against. Required of anything above ``read_sensitive`` and
    #: meaningless below it: nothing that cannot change anything is ever asked.
    #:
    #: Judged by the author, once, in code. The decision point cannot work it
    #: out — it sees a name and some arguments — and an undeclared class resolves
    #: as the top of the scale, so leaving it blank is a tool that never runs
    #: unattended rather than one that runs unexamined.
    risk_class: str = ""

    def __post_init__(self) -> None:
        CapabilityMetadata.__post_init__(self)

        if not str(self.evidence_source).strip():
            raise ValueError(f"{self.name}: evidence_source must name the system it reads")
        object.__setattr__(self, "evidence_source", str(self.evidence_source).strip())
        object.__setattr__(self, "risk_class", str(self.risk_class).strip().lower())

        # Checked whatever the level is. A typo on a read tool is an author's
        # decision that never took effect, and it would be invisible until the
        # day somebody raised that tool's level.
        if self.risk_class and self.risk_class not in RISK_CLASSES:
            raise ValueError(
                f"{self.name}: {self.risk_class!r} is not a risk class; expected one of "
                f"{', '.join(RISK_CLASSES)}"
            )

        if self.side_effect_level.needs_approval:
            self._require_approval_metadata()
        elif self.requires_approval:
            # Not pedantry. An approval prompt in front of an action that
            # changes nothing is how an operator learns to click through them,
            # and the next prompt they see is a restart.
            raise ValueError(
                f"{self.name}: a {self.side_effect_level.value} tool must not require "
                "approval — approval on a read teaches operators to dismiss it"
            )

    def _require_approval_metadata(self) -> None:
        """Raise unless everything the approval gate will need is already here."""
        if not self.requires_approval:
            raise ValueError(
                f"{self.name}: side_effect_level {self.side_effect_level.value!r} is above "
                "read_sensitive, so requires_approval must be True"
            )
        if not self.approval_reason.strip():
            raise ValueError(
                f"{self.name}: approval_reason must say what the human is being asked to accept"
            )
        if self.rollback_planner is None and not self.rollback_plan.strip():
            raise ValueError(
                f"{self.name}: a tool above read_sensitive must declare a rollback plan "
                "or a rollback_planner"
            )
        if not self.risk_class:
            raise ValueError(
                f"{self.name}: a tool above read_sensitive must declare a risk_class, one of "
                f"{', '.join(RISK_CLASSES)}. An undeclared class is treated as the most "
                f"dangerous one, so the tool would never run unattended."
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillMetadata(CapabilityMetadata):
    """A methodology document's declaration — the part that is always in context.

    Everything here is paid for on every turn, for every skill in the resolved
    catalogue. The body, which is where a skill actually says anything, is not:
    it loads only once this record has won a slot.
    """

    kind: ClassVar[CapabilityKind] = CapabilityKind.SKILL
    name_pattern: ClassVar[re.Pattern[str]] = SKILL_NAME_PATTERN

    domain: str
    applies_when: AppliesWhen = AppliesWhen()
    directs_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        CapabilityMetadata.__post_init__(self)

        if not self.domain:
            raise ValueError(f"{self.name}: domain must name the area this methodology covers")
        object.__setattr__(self, "directs_tools", _frozen(self.directs_tools))


@dataclass(frozen=True, slots=True)
class ExcludedCapability:
    """A capability a team's catalogue left out, and why.

    The reason travels with the exclusion because "not in the catalogue" and
    "not configured for this team" look identical from the console, and only one
    of them is something an operator can fix.
    """

    name: str
    kind: CapabilityKind
    unmet: tuple[str, ...] = field(default_factory=tuple)

    @property
    def reason(self) -> str:
        """Return a sentence naming what is missing."""
        return f"requires {', '.join(self.unmet)}, which this team has not configured"


def metadata_text(metadata: CapabilityMetadata) -> str:
    """Return everything about ``metadata`` the model reads, as one string.

    Token budgets are measured against this rather than against the description
    alone. The model pays for the name and the tags too, and a budget that
    ignores them is a budget that is wrong by the time a catalogue is large
    enough for it to matter.
    """
    parts: list[str] = [metadata.name, metadata.display_name, metadata.description]
    if metadata.domain:
        parts.append(metadata.domain)
    parts.extend(metadata.tags)
    parts.extend(metadata.use_cases)
    parts.extend(metadata.anti_examples)
    if isinstance(metadata, SkillMetadata):
        parts.extend(metadata.applies_when.alert_sources)
        parts.extend(metadata.applies_when.tags)
        parts.extend(metadata.directs_tools)
    return "\n".join(parts)


def sequence_or_empty(values: Sequence[str] | None) -> tuple[str, ...]:
    """Return ``values`` as a tuple, treating ``None`` as empty."""
    return _frozen(values)


__all__ = [
    "CAPABILITY_NAME_PATTERN",
    "SKILL_NAME_PATTERN",
    "TOOL_NAME_PATTERN",
    "AppliesWhen",
    "CapabilityKind",
    "CapabilityMetadata",
    "EvidenceSource",
    "EvidenceType",
    "ExcludedCapability",
    "Requirements",
    "RollbackPlan",
    "RollbackPlanner",
    "SideEffectLevel",
    "SkillMetadata",
    "ToolMetadata",
    "metadata_text",
    "sequence_or_empty",
]
