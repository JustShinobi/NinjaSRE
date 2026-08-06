"""The switches that decide what the platform is allowed to do, and to learn from.

Six sections, and the shape they share is the interesting part: every learning
mechanism has its own switch, separately. Article VII forbids claiming a
mechanism that has not been measured, and the only honest measurement is the
same scenarios with it and without it. One switch covering memory, strategy, and
knowledge would answer none of the three questions — "does recall help", "do
playbooks help given the episodes were already there", and "does the operator's
own topology help" are three experiments.

Reading and writing switch separately in ``memory`` for the same reason: the
ablation worth running is a populated corpus the agent may not consult, which
isolates recall while leaving the corpus intact for the run after.

The masking and guardrail sections carry the one asymmetry in the package.
``guardrails.mode`` may be set to observe-only, which downgrades every action to
audit — nothing altered, nothing blocked, everything still recorded. There is no
value that removes the engine, because the constitution's claim is that it
cannot be removed from the boundary, and a configuration field that could
remove it would make the claim a preference.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from config.constants.security import (
    DEFAULT_MASKING_POLICY,
    MASKING_POLICY_LEVELS,
    SIDE_EFFECT_LEVELS,
    SIDE_EFFECT_WRITE_REVERSIBLE,
)
from platform.config_service.schema.reader import Reader

#: Guardrails run, or guardrails run and record without altering anything.
#: There is deliberately no third value.
GUARDRAIL_MODE_ENFORCING = "enforcing"
GUARDRAIL_MODE_OBSERVING = "observing"
GUARDRAIL_MODES: tuple[str, ...] = (GUARDRAIL_MODE_ENFORCING, GUARDRAIL_MODE_OBSERVING)

MEMORY_FIELDS: tuple[str, ...] = ("read_enabled", "write_enabled")
STRATEGY_FIELDS: tuple[str, ...] = ("enabled",)
KNOWLEDGE_FIELDS: tuple[str, ...] = ("topology_enabled", "knowledge_base_enabled")
MASKING_FIELDS: tuple[str, ...] = ("enabled", "level", "custom_patterns")
GUARDRAILS_FIELDS: tuple[str, ...] = ("mode", "ruleset", "disabled_rules")
APPROVALS_FIELDS: tuple[str, ...] = ("threshold", "autonomous_capabilities", "expiry_hours")
POLICIES_FIELDS: tuple[str, ...] = (
    "memory",
    "strategy",
    "knowledge",
    "masking",
    "guardrails",
    "approvals",
)

#: What an approval request stays answerable for. Long enough for an on-call
#: rotation to see it, short enough that nobody approves a plan for a cluster
#: that has since been replaced.
DEFAULT_APPROVAL_EXPIRY_HOURS = 4.0
MAX_APPROVAL_EXPIRY_HOURS = 168.0

#: A custom masking pattern is a name and a regular expression. The name is what
#: the token is built from, so ``NSRE_MASK_TICKET_1`` reads in a prompt where
#: ``NSRE_MASK_CUSTOM_1`` does not.
CUSTOM_PATTERN_FIELDS: tuple[str, ...] = ("name", "pattern")


@dataclass(frozen=True, slots=True)
class MemoryPolicySettings:
    """Whether this team's investigations read from and write to episodic memory."""

    read_enabled: bool = True
    write_enabled: bool = True

    @classmethod
    def of(cls, reader: Reader) -> MemoryPolicySettings:
        """Return the memory switches ``reader`` describes."""
        reader.close(MEMORY_FIELDS)
        return cls(
            read_enabled=reader.boolean("read_enabled", True),
            write_enabled=reader.boolean("write_enabled", True),
        )


@dataclass(frozen=True, slots=True)
class StrategyPolicySettings:
    """Whether synthesised playbooks are offered alongside episodes."""

    enabled: bool = True

    @classmethod
    def of(cls, reader: Reader) -> StrategyPolicySettings:
        """Return the strategy switch ``reader`` describes."""
        reader.close(STRATEGY_FIELDS)
        return cls(enabled=reader.boolean("enabled", True))


@dataclass(frozen=True, slots=True)
class KnowledgePolicySettings:
    """Whether the topology graph and the knowledge base are reachable."""

    topology_enabled: bool = True
    knowledge_base_enabled: bool = True

    @classmethod
    def of(cls, reader: Reader) -> KnowledgePolicySettings:
        """Return the knowledge switches ``reader`` describes."""
        reader.close(KNOWLEDGE_FIELDS)
        return cls(
            topology_enabled=reader.boolean("topology_enabled", True),
            knowledge_base_enabled=reader.boolean("knowledge_base_enabled", True),
        )


@dataclass(frozen=True, slots=True)
class CustomMaskingPattern:
    """One operator-supplied identifier shape."""

    name: str
    pattern: str

    @classmethod
    def of(cls, reader: Reader) -> CustomMaskingPattern:
        """Return the pattern ``reader`` describes."""
        reader.close(CUSTOM_PATTERN_FIELDS)
        name = reader.string("name")
        pattern = reader.string("pattern")
        if not name:
            reader.fail("name", "a custom pattern needs a name; it becomes part of the token")
        if not pattern:
            reader.fail("pattern", "a custom pattern needs an expression to match")
        return cls(name=name, pattern=pattern)


@dataclass(frozen=True, slots=True)
class MaskingPolicySettings:
    """How much of the operator's estate may reach a model they do not host."""

    enabled: bool = True
    level: str = DEFAULT_MASKING_POLICY
    custom_patterns: tuple[CustomMaskingPattern, ...] = ()

    @classmethod
    def of(cls, reader: Reader) -> MaskingPolicySettings:
        """Return the masking policy ``reader`` describes."""
        reader.close(MASKING_FIELDS)
        return cls(
            enabled=reader.boolean("enabled", True),
            level=reader.string("level", DEFAULT_MASKING_POLICY, allowed=MASKING_POLICY_LEVELS),
            custom_patterns=tuple(
                CustomMaskingPattern.of(each) for each in reader.sections("custom_patterns")
            ),
        )


@dataclass(frozen=True, slots=True)
class GuardrailPolicySettings:
    """Which secret shapes are looked for, and whether a match is acted on."""

    mode: str = GUARDRAIL_MODE_ENFORCING
    ruleset: str | None = None
    disabled_rules: tuple[str, ...] = ()

    @classmethod
    def of(cls, reader: Reader) -> GuardrailPolicySettings:
        """Return the guardrail policy ``reader`` describes."""
        reader.close(GUARDRAILS_FIELDS)
        return cls(
            mode=reader.string("mode", GUARDRAIL_MODE_ENFORCING, allowed=GUARDRAIL_MODES),
            ruleset=reader.optional_string("ruleset"),
            disabled_rules=reader.strings("disabled_rules"),
        )

    @property
    def enforcing(self) -> bool:
        """Return whether a match alters or blocks rather than only recording."""
        return self.mode == GUARDRAIL_MODE_ENFORCING


@dataclass(frozen=True, slots=True)
class ApprovalPolicySettings:
    """Where the line between "do it" and "ask first" sits for this team.

    ``threshold`` is the lowest side-effect level that needs a human. It cannot
    be raised past ``write_reversible``: Article III says anything above
    ``read_sensitive`` needs per-action approval, and a configuration field that
    could switch that off would make the article advisory.
    """

    threshold: str = SIDE_EFFECT_WRITE_REVERSIBLE
    autonomous_capabilities: tuple[str, ...] = ()
    expiry_hours: float = DEFAULT_APPROVAL_EXPIRY_HOURS

    @classmethod
    def of(cls, reader: Reader) -> ApprovalPolicySettings:
        """Return the approval policy ``reader`` describes."""
        reader.close(APPROVALS_FIELDS)
        threshold = reader.string(
            "threshold", SIDE_EFFECT_WRITE_REVERSIBLE, allowed=SIDE_EFFECT_LEVELS
        )
        if SIDE_EFFECT_LEVELS.index(threshold) > SIDE_EFFECT_LEVELS.index(
            SIDE_EFFECT_WRITE_REVERSIBLE
        ):
            reader.fail(
                "threshold",
                f"cannot sit above {SIDE_EFFECT_WRITE_REVERSIBLE!r}: every write needs "
                f"per-action approval and a stored rollback plan",
            )
            threshold = SIDE_EFFECT_WRITE_REVERSIBLE
        return cls(
            threshold=threshold,
            autonomous_capabilities=reader.strings("autonomous_capabilities"),
            expiry_hours=reader.number(
                "expiry_hours",
                DEFAULT_APPROVAL_EXPIRY_HOURS,
                minimum=0.25,
                maximum=MAX_APPROVAL_EXPIRY_HOURS,
            ),
        )

    def requires_approval(self, side_effect_level: str, capability: str = "") -> bool:
        """Return whether an action at ``side_effect_level`` needs a human first."""
        if capability and capability in self.autonomous_capabilities:
            return False
        if side_effect_level not in SIDE_EFFECT_LEVELS:
            return True
        return SIDE_EFFECT_LEVELS.index(side_effect_level) >= SIDE_EFFECT_LEVELS.index(
            self.threshold
        )


@dataclass(frozen=True, slots=True)
class PoliciesConfig:
    """Every policy switch, in one section."""

    memory: MemoryPolicySettings = field(default_factory=MemoryPolicySettings)
    strategy: StrategyPolicySettings = field(default_factory=StrategyPolicySettings)
    knowledge: KnowledgePolicySettings = field(default_factory=KnowledgePolicySettings)
    masking: MaskingPolicySettings = field(default_factory=MaskingPolicySettings)
    guardrails: GuardrailPolicySettings = field(default_factory=GuardrailPolicySettings)
    approvals: ApprovalPolicySettings = field(default_factory=ApprovalPolicySettings)

    @classmethod
    def of(cls, reader: Reader) -> PoliciesConfig:
        """Return the policies ``reader`` describes."""
        reader.close(POLICIES_FIELDS)
        return cls(
            memory=MemoryPolicySettings.of(reader.section("memory")),
            strategy=StrategyPolicySettings.of(reader.section("strategy")),
            knowledge=KnowledgePolicySettings.of(reader.section("knowledge")),
            masking=MaskingPolicySettings.of(reader.section("masking")),
            guardrails=GuardrailPolicySettings.of(reader.section("guardrails")),
            approvals=ApprovalPolicySettings.of(reader.section("approvals")),
        )

    def ablation_summary(self) -> Mapping[str, object]:
        """Return what a run trace records about how learning was configured.

        The configuration, not what happened. "Recall was off" and "recall found
        nothing" are different facts, and an ablation table that could not tell
        them apart would be unreadable.
        """
        return {
            "memory_read_enabled": self.memory.read_enabled,
            "memory_write_enabled": self.memory.write_enabled,
            "strategy_enabled": self.strategy.enabled,
            "topology_enabled": self.knowledge.topology_enabled,
            "knowledge_base_enabled": self.knowledge.knowledge_base_enabled,
            "masking_enabled": self.masking.enabled,
            "guardrail_mode": self.guardrails.mode,
        }


__all__ = [
    "APPROVALS_FIELDS",
    "ApprovalPolicySettings",
    "CUSTOM_PATTERN_FIELDS",
    "CustomMaskingPattern",
    "GUARDRAILS_FIELDS",
    "GUARDRAIL_MODES",
    "GUARDRAIL_MODE_ENFORCING",
    "GUARDRAIL_MODE_OBSERVING",
    "GuardrailPolicySettings",
    "KNOWLEDGE_FIELDS",
    "KnowledgePolicySettings",
    "MASKING_FIELDS",
    "MEMORY_FIELDS",
    "MaskingPolicySettings",
    "MemoryPolicySettings",
    "POLICIES_FIELDS",
    "PoliciesConfig",
    "STRATEGY_FIELDS",
    "StrategyPolicySettings",
]
