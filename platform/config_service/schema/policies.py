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
cannot be removed from the boundary, and a configuration field that could remove
it would make the claim a preference.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Final, Literal

from pydantic import Field, field_validator

from config.constants.security import (
    DEFAULT_MASKING_POLICY,
    MASKING_POLICY_LEVELS,
    SIDE_EFFECT_LEVELS,
    SIDE_EFFECT_WRITE_REVERSIBLE,
)
from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredFloat,
    ConfiguredStr,
    ConfiguredStrList,
)

#: Guardrails run, or guardrails run and record without altering anything.
#: There is deliberately no third value — no configuration removes the engine
#: from the boundary, because the constitution's claim is that it cannot be.
GuardrailMode = Literal["enforcing", "observing"]

GUARDRAIL_MODE_ENFORCING: Final[GuardrailMode] = "enforcing"
GUARDRAIL_MODE_OBSERVING: Final[GuardrailMode] = "observing"
GUARDRAIL_MODES: tuple[GuardrailMode, ...] = (GUARDRAIL_MODE_ENFORCING, GUARDRAIL_MODE_OBSERVING)

#: What an approval request stays answerable for. Long enough for an on-call
#: rotation to see it, short enough that nobody approves a plan for a cluster
#: that has since been replaced.
DEFAULT_APPROVAL_EXPIRY_HOURS = 4.0
MAX_APPROVAL_EXPIRY_HOURS = 168.0


class MemoryPolicySettings(ConfigSection):
    """Whether this team's investigations read from and write to episodic memory."""

    read_enabled: bool = True
    write_enabled: bool = True


class StrategyPolicySettings(ConfigSection):
    """Whether synthesised playbooks are offered alongside episodes."""

    enabled: bool = True


class KnowledgePolicySettings(ConfigSection):
    """Whether the topology graph and the knowledge base are reachable."""

    topology_enabled: bool = True
    knowledge_base_enabled: bool = True


class CustomMaskingPattern(ConfigSection):
    """One operator-supplied identifier shape.

    The name becomes part of the token, so ``NSRE_MASK_TICKET_1`` reads in a
    prompt where ``NSRE_MASK_CUSTOM_1`` does not — which is why it is required
    rather than generated.
    """

    #: Both required. A pattern with no name produces an unreadable token and
    #: one with no expression matches nothing; defaults would hide either.
    name: ConfiguredStr
    pattern: ConfiguredStr


class MaskingPolicySettings(ConfigSection):
    """How much of the operator's estate may reach a model they do not host."""

    enabled: bool = True
    level: ConfiguredStr = DEFAULT_MASKING_POLICY
    custom_patterns: tuple[CustomMaskingPattern, ...] = ()

    @field_validator("level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        """Refuse a level the masking layer does not implement."""
        if value not in MASKING_POLICY_LEVELS:
            raise ValueError(f"must be one of {', '.join(MASKING_POLICY_LEVELS)}; found {value!r}")
        return value


class GuardrailPolicySettings(ConfigSection):
    """Which secret shapes are looked for, and whether a match is acted on."""

    mode: GuardrailMode = GUARDRAIL_MODE_ENFORCING
    ruleset: ConfiguredStr | None = None
    disabled_rules: ConfiguredStrList = ()

    @property
    def enforcing(self) -> bool:
        """Return whether a match alters or blocks rather than only recording."""
        return self.mode == GUARDRAIL_MODE_ENFORCING


class ApprovalPolicySettings(ConfigSection):
    """Where the line between "do it" and "ask first" sits for this team.

    ``threshold`` is the lowest side-effect level that needs a human. It cannot
    be raised past ``write_reversible``: Article III says anything above
    ``read_sensitive`` needs per-action approval, and a configuration field that
    could switch that off would make the article advisory.
    """

    threshold: ConfiguredStr = SIDE_EFFECT_WRITE_REVERSIBLE
    autonomous_capabilities: ConfiguredStrList = ()
    expiry_hours: Annotated[ConfiguredFloat, Field(ge=0.25, le=MAX_APPROVAL_EXPIRY_HOURS)] = (
        DEFAULT_APPROVAL_EXPIRY_HOURS
    )

    @field_validator("threshold")
    @classmethod
    def _within_the_article(cls, value: str) -> str:
        """Refuse a threshold that would leave a write unapproved."""
        if value not in SIDE_EFFECT_LEVELS:
            raise ValueError(f"must be one of {', '.join(SIDE_EFFECT_LEVELS)}; found {value!r}")
        if SIDE_EFFECT_LEVELS.index(value) > SIDE_EFFECT_LEVELS.index(SIDE_EFFECT_WRITE_REVERSIBLE):
            raise ValueError(
                f"cannot sit above {SIDE_EFFECT_WRITE_REVERSIBLE!r}: every write needs "
                f"per-action approval and a stored rollback plan"
            )
        return value

    def requires_approval(self, side_effect_level: str, capability: str = "") -> bool:
        """Return whether an action at ``side_effect_level`` needs a human first."""
        if capability and capability in self.autonomous_capabilities:
            return False
        if side_effect_level not in SIDE_EFFECT_LEVELS:
            return True
        return SIDE_EFFECT_LEVELS.index(side_effect_level) >= SIDE_EFFECT_LEVELS.index(
            self.threshold
        )


class PoliciesConfig(ConfigSection):
    """Every policy switch, in one section."""

    memory: MemoryPolicySettings = MemoryPolicySettings()
    strategy: StrategyPolicySettings = StrategyPolicySettings()
    knowledge: KnowledgePolicySettings = KnowledgePolicySettings()
    masking: MaskingPolicySettings = MaskingPolicySettings()
    guardrails: GuardrailPolicySettings = GuardrailPolicySettings()
    approvals: ApprovalPolicySettings = ApprovalPolicySettings()

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


POLICIES_FIELDS: tuple[str, ...] = tuple(PoliciesConfig.model_fields)
MEMORY_FIELDS: tuple[str, ...] = tuple(MemoryPolicySettings.model_fields)
STRATEGY_FIELDS: tuple[str, ...] = tuple(StrategyPolicySettings.model_fields)
KNOWLEDGE_FIELDS: tuple[str, ...] = tuple(KnowledgePolicySettings.model_fields)
MASKING_FIELDS: tuple[str, ...] = tuple(MaskingPolicySettings.model_fields)
GUARDRAILS_FIELDS: tuple[str, ...] = tuple(GuardrailPolicySettings.model_fields)
APPROVALS_FIELDS: tuple[str, ...] = tuple(ApprovalPolicySettings.model_fields)
CUSTOM_PATTERN_FIELDS: tuple[str, ...] = tuple(CustomMaskingPattern.model_fields)


__all__ = [
    "APPROVALS_FIELDS",
    "CUSTOM_PATTERN_FIELDS",
    "GUARDRAILS_FIELDS",
    "GUARDRAIL_MODES",
    "GUARDRAIL_MODE_ENFORCING",
    "GUARDRAIL_MODE_OBSERVING",
    "GuardrailMode",
    "KNOWLEDGE_FIELDS",
    "MASKING_FIELDS",
    "MEMORY_FIELDS",
    "POLICIES_FIELDS",
    "STRATEGY_FIELDS",
    "ApprovalPolicySettings",
    "CustomMaskingPattern",
    "GuardrailPolicySettings",
    "KnowledgePolicySettings",
    "MaskingPolicySettings",
    "MemoryPolicySettings",
    "PoliciesConfig",
    "StrategyPolicySettings",
]
