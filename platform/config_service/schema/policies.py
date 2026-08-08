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
from datetime import datetime, time
from typing import Annotated, Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from config.constants.autonomy import (
    AUTONOMY_BUDGET_SCOPE_RESOURCE,
    AUTONOMY_BUDGET_SCOPES,
    AUTONOMY_LEVELS,
    AUTONOMY_SCOPE_CAPABILITY,
    AUTONOMY_SCOPE_CAPABILITY_RESOURCE,
    AUTONOMY_SCOPE_DEPLOYMENT,
    AUTONOMY_SCOPE_KINDS,
    AUTONOMY_SCOPE_LABELS,
    AUTONOMY_SCOPE_RESOURCE,
    AUTONOMY_SCOPE_RESOURCE_KIND,
    AUTONOMY_SCOPE_TEAM,
    DEFAULT_AUTONOMY_BUDGET,
    DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS,
    DEFAULT_AUTONOMY_LEVEL,
    DEFAULT_FREEZE_TIMEZONE,
    DEFAULT_RISK_BOUND,
    MAX_AUTONOMY_RULES,
    RISK_CLASSES,
)
from config.constants.closed_loop import MAX_RECURRENCE_WINDOW_SECONDS
from config.constants.notifications import SEVERITY_HIGH
from config.constants.observation import (
    DEFAULT_DETECTOR_DURATION_SECONDS,
    DETECTOR_COMPARISON_ABOVE,
    DETECTOR_COMPARISONS,
    DETECTOR_CONDITION_KINDS,
    DETECTOR_GROUPING_DETECTOR,
    DETECTOR_GROUPINGS,
    DETECTOR_KIND_THRESHOLD,
)
from config.constants.security import (
    DEFAULT_MASKING_POLICY,
    MASKING_POLICY_LEVELS,
    SIDE_EFFECT_LEVELS,
    SIDE_EFFECT_WRITE_REVERSIBLE,
)
from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredFloat,
    ConfiguredInt,
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


class DetectorSettings(ConfigSection):
    """One detector, as a team declares it.

    Deliberately flat and deliberately small. A detector is configuration so
    that a team can add one without new code; making it *expressive* would make
    it a second programming language, which is the risk the observation plan
    names and this shape is the mitigation. Four condition kinds, two numbers,
    two durations, and no expression field.

    Validated twice: here for shape, and again when it is turned into a
    declaration, which is where the cross-field rules live — a clear value on
    the wrong side of the firing value cannot be caught one field at a time.
    """

    #: Both required. A detector with no identifier cannot be enabled, disabled
    #: or referred to in an incident, and one with no signal reads nothing.
    detector_id: ConfiguredStr
    signal: ConfiguredStr
    name: ConfiguredStr = ""
    description: ConfiguredStr = ""
    kind: ConfiguredStr = DETECTOR_KIND_THRESHOLD
    comparison: ConfiguredStr = DETECTOR_COMPARISON_ABOVE
    resource_kinds: ConfiguredStrList = ()
    fire_value: ConfiguredFloat = 0.0
    clear_value: ConfiguredFloat = 0.0
    silent_after_seconds: Annotated[ConfiguredInt, Field(ge=0)] = 0
    to_state: ConfiguredStr = ""
    from_state: ConfiguredStr = ""
    for_seconds: Annotated[ConfiguredInt, Field(ge=1)] = DEFAULT_DETECTOR_DURATION_SECONDS
    recovery_seconds: Annotated[ConfiguredInt, Field(ge=1)] = DEFAULT_DETECTOR_DURATION_SECONDS
    severity: ConfiguredStr = SEVERITY_HIGH
    grouping_key: ConfiguredStr = DETECTOR_GROUPING_DETECTOR
    enabled: bool = True
    capabilities: ConfiguredStrList = ()

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        """Refuse a condition kind the evaluator does not implement."""
        if value not in DETECTOR_CONDITION_KINDS:
            raise ValueError(
                f"must be one of {', '.join(DETECTOR_CONDITION_KINDS)}; found {value!r}"
            )
        return value

    @field_validator("comparison")
    @classmethod
    def _known_comparison(cls, value: str) -> str:
        """Refuse a comparison that is neither side of the threshold."""
        if value not in DETECTOR_COMPARISONS:
            raise ValueError(f"must be one of {', '.join(DETECTOR_COMPARISONS)}; found {value!r}")
        return value

    @field_validator("grouping_key")
    @classmethod
    def _known_grouping(cls, value: str) -> str:
        """Refuse a grouping the correlation engine cannot apply."""
        if value not in DETECTOR_GROUPINGS:
            raise ValueError(f"must be one of {', '.join(DETECTOR_GROUPINGS)}; found {value!r}")
        return value


class ObservationPolicySettings(ConfigSection):
    """What this team watches for, and whether it is watching at all.

    ``paused`` is the global stop. It suppresses every detector this node
    resolves without unconfiguring any of them, so an operator who needs the
    deployment to stop opening incidents during a migration does not have to
    delete the detectors and remember to put them back.
    """

    detectors: tuple[DetectorSettings, ...] = ()
    paused: bool = False
    pause_reason: ConfiguredStr = ""


#: What each scope kind cannot be without. ``deployment`` needs nothing — it is
#: the statement "everywhere", which is a decision rather than an omission.
_SCOPE_REQUIREMENTS: Final[Mapping[str, tuple[str, ...]]] = {
    AUTONOMY_SCOPE_DEPLOYMENT: (),
    AUTONOMY_SCOPE_TEAM: ("team_node_id",),
    AUTONOMY_SCOPE_RESOURCE_KIND: ("resource_kind",),
    AUTONOMY_SCOPE_LABELS: ("labels",),
    AUTONOMY_SCOPE_CAPABILITY: ("capability",),
    AUTONOMY_SCOPE_RESOURCE: ("resource_id",),
    AUTONOMY_SCOPE_CAPABILITY_RESOURCE: ("capability", "resource_id"),
}


class AutonomyLabelSettings(ConfigSection):
    """One label a scope selects on.

    A pair rather than a mapping, for the reason a custom masking pattern is
    one: a section with operator-chosen keys is not a closed schema, and the
    console cannot render a form for a shape nobody declared.
    """

    #: Both required. A label with no name selects nothing and one with no value
    #: selects everything, and a default would hide either.
    name: ConfiguredStr
    value: ConfiguredStr


class AutonomyScopeSettings(ConfigSection):
    """Where a rule, a freeze, a budget or an override applies.

    Validated here as well as in the engine. This is the save-time half: an
    operator writing a scope whose kind and fields disagree finds out when they
    write it, rather than when something declines to act because of it.
    """

    kind: ConfiguredStr = AUTONOMY_SCOPE_DEPLOYMENT
    team_node_id: ConfiguredStr = ""
    resource_kind: ConfiguredStr = ""
    resource_id: ConfiguredStr = ""
    capability: ConfiguredStr = ""
    labels: tuple[AutonomyLabelSettings, ...] = ()

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        """Refuse a scope kind the resolver has no precedence for."""
        if value not in AUTONOMY_SCOPE_KINDS:
            raise ValueError(f"must be one of {', '.join(AUTONOMY_SCOPE_KINDS)}; found {value!r}")
        return value

    @model_validator(mode="after")
    def _named_something(self) -> AutonomyScopeSettings:
        """Refuse a scope whose kind needs a field it does not have."""
        required = _SCOPE_REQUIREMENTS[self.kind]
        missing = [
            name
            for name in required
            if not (self.labels if name == "labels" else getattr(self, name))
        ]
        if missing:
            raise ValueError(
                f"a {self.kind} scope needs {', '.join(missing)}; without it the rule "
                f"applies to everything, which is not what naming a scope means"
            )
        return self


class AutonomyRuleSettings(ConfigSection):
    """One statement: in this scope, this much autonomy, up to this much risk."""

    scope: AutonomyScopeSettings = AutonomyScopeSettings()
    level: ConfiguredStr = DEFAULT_AUTONOMY_LEVEL
    risk_bound: ConfiguredStr = DEFAULT_RISK_BOUND
    dry_run: bool = False

    @field_validator("level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        """Refuse a level outside the closed set of three."""
        if value not in AUTONOMY_LEVELS:
            raise ValueError(f"must be one of {', '.join(AUTONOMY_LEVELS)}; found {value!r}")
        return value

    @field_validator("risk_bound")
    @classmethod
    def _known_risk(cls, value: str) -> str:
        """Refuse a risk bound outside the closed scale."""
        if value not in RISK_CLASSES:
            raise ValueError(f"must be one of {', '.join(RISK_CLASSES)}; found {value!r}")
        return value


class FreezeWindowSettings(ConfigSection):
    """A span of the day nothing in scope may run, in a named timezone."""

    #: Required. A refusal has to name what refused it, and "a freeze window"
    #: sends an operator to read every one they have.
    name: ConfiguredStr
    start: ConfiguredStr
    end: ConfiguredStr
    scope: AutonomyScopeSettings = AutonomyScopeSettings()
    timezone: ConfiguredStr = DEFAULT_FREEZE_TIMEZONE
    reason: ConfiguredStr = ""

    @field_validator("start", "end")
    @classmethod
    def _a_time_of_day(cls, value: str) -> str:
        """Refuse anything that is not a wall-clock time."""
        try:
            time.fromisoformat(value)
        except ValueError as rejected:
            raise ValueError(f"must be a time of day like '01:00'; found {value!r}") from rejected
        return value

    @field_validator("timezone")
    @classmethod
    def _a_known_zone(cls, value: str) -> str:
        """Refuse a zone this host cannot resolve, at save time rather than at 01:00."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as unknown:
            raise ValueError(f"is not a timezone this host knows; found {value!r}") from unknown
        return value

    @model_validator(mode="after")
    def _spans_something(self) -> FreezeWindowSettings:
        """Refuse a window that freezes either nothing or everything."""
        if self.start == self.end:
            raise ValueError(
                "a window starting and ending at the same time freezes either nothing or "
                "everything depending on how it is read; say which you meant"
            )
        return self


class AutonomyBudgetSettings(ConfigSection):
    """How many actions may run in scope over an interval, and against what."""

    #: Required. An exhaustion has to name which budget is spent.
    name: ConfiguredStr
    counted_by: ConfiguredStr = AUTONOMY_BUDGET_SCOPE_RESOURCE
    limit: Annotated[ConfiguredInt, Field(ge=0)] = DEFAULT_AUTONOMY_BUDGET
    interval_seconds: Annotated[ConfiguredFloat, Field(gt=0)] = (
        DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS
    )
    scope: AutonomyScopeSettings | None = None

    @field_validator("counted_by")
    @classmethod
    def _known_counter(cls, value: str) -> str:
        """Refuse something a budget cannot be counted against."""
        if value not in AUTONOMY_BUDGET_SCOPES:
            raise ValueError(f"must be one of {', '.join(AUTONOMY_BUDGET_SCOPES)}; found {value!r}")
        return value


class AutonomyOverrideSettings(ConfigSection):
    """A raise in autonomy that ends by itself, at a stated instant."""

    #: Both required. An expiry has to name what expired, and an override with
    #: no end is a policy change wearing an override's name.
    name: ConfiguredStr
    expires_at: ConfiguredStr
    scope: AutonomyScopeSettings = AutonomyScopeSettings()
    level: ConfiguredStr = DEFAULT_AUTONOMY_LEVEL
    risk_bound: ConfiguredStr = DEFAULT_RISK_BOUND
    granted_by: ConfiguredStr = ""
    reason: ConfiguredStr = ""

    @field_validator("level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        """Refuse a level outside the closed set of three."""
        if value not in AUTONOMY_LEVELS:
            raise ValueError(f"must be one of {', '.join(AUTONOMY_LEVELS)}; found {value!r}")
        return value

    @field_validator("risk_bound")
    @classmethod
    def _known_risk(cls, value: str) -> str:
        """Refuse a risk bound outside the closed scale."""
        if value not in RISK_CLASSES:
            raise ValueError(f"must be one of {', '.join(RISK_CLASSES)}; found {value!r}")
        return value

    @field_validator("expires_at")
    @classmethod
    def _an_instant(cls, value: str) -> str:
        """Refuse a wall-clock time where an instant belongs.

        An override that expired "at 14:00" would expire at a different moment
        on every host that read it, which is the one property an expiry cannot
        have.
        """
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as rejected:
            raise ValueError(f"must be an instant in ISO 8601; found {value!r}") from rejected
        if parsed.tzinfo is None:
            raise ValueError(f"names no timezone, so it names no instant; found {value!r}")
        return value


class AutonomyPolicySettings(ConfigSection):
    """How much this team may do without asking, and the bounds on the answer.

    Under ``policies`` rather than in a section of its own, for the reason the
    detectors are: whether this team may act unattended is the same kind of
    decision as whether its runs may write to memory, and the closed set of
    top-level sections is what lets the console render a form at all.
    """

    rules: tuple[AutonomyRuleSettings, ...] = ()
    freezes: tuple[FreezeWindowSettings, ...] = ()
    budgets: tuple[AutonomyBudgetSettings, ...] = ()
    overrides: tuple[AutonomyOverrideSettings, ...] = ()
    #: Simulate everything this node resolves, whatever any rule says. The
    #: deployment-wide half of dry-run mode; the per-scope half is on the rule.
    dry_run: bool = False
    #: Whether an action whose effect no signal reports may run unattended.
    #: Defaults to ``False``, and the default is the decision: a capability
    #: nobody can verify is one the deployment would act on and never find out
    #: about, so it takes a human approval until an operator says otherwise.
    allow_unverifiable_actions: bool = False
    #: How many times one capability may be applied to one resource inside the
    #: window before it stops being an incident and becomes a recurring problem.
    #: Zero means the deployment default.
    recurrence_threshold: int = 0
    #: How long that window is, in seconds. Zero means the deployment default.
    recurrence_window_seconds: int = 0

    @field_validator("recurrence_window_seconds")
    @classmethod
    def _inside_the_recurrence_ceiling(cls, value: int) -> int:
        """Refuse a window beyond the point where the count stops describing now."""
        if value and not 0 < value <= MAX_RECURRENCE_WINDOW_SECONDS:
            raise ValueError(
                f"a recurrence window of {value}s is outside "
                f"(0, {MAX_RECURRENCE_WINDOW_SECONDS}]. Beyond a year the count stops "
                f"describing the system that exists now."
            )
        return value

    @field_validator("recurrence_threshold")
    @classmethod
    def _a_threshold_that_can_be_a_pattern(cls, value: int) -> int:
        """Refuse a threshold below two, which is not a recurrence."""
        if value and value < 2:
            raise ValueError(
                f"a recurrence threshold of {value} is not a recurrence; two is the "
                f"smallest number of occurrences that can be a pattern"
            )
        return value

    @field_validator("rules")
    @classmethod
    def _within_the_ceiling(
        cls, value: tuple[AutonomyRuleSettings, ...]
    ) -> tuple[AutonomyRuleSettings, ...]:
        """Refuse more rules than resolution is budgeted to walk."""
        if len(value) > MAX_AUTONOMY_RULES:
            raise ValueError(
                f"a node may configure {MAX_AUTONOMY_RULES} rules; found {len(value)}. "
                f"Resolution runs on every action, and a policy set nobody can read is "
                f"not one anybody reviewed."
            )
        return value


class PoliciesConfig(ConfigSection):
    """Every policy switch, in one section."""

    memory: MemoryPolicySettings = MemoryPolicySettings()
    strategy: StrategyPolicySettings = StrategyPolicySettings()
    knowledge: KnowledgePolicySettings = KnowledgePolicySettings()
    masking: MaskingPolicySettings = MaskingPolicySettings()
    guardrails: GuardrailPolicySettings = GuardrailPolicySettings()
    approvals: ApprovalPolicySettings = ApprovalPolicySettings()
    observation: ObservationPolicySettings = ObservationPolicySettings()
    autonomy: AutonomyPolicySettings = AutonomyPolicySettings()

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
AUTONOMY_FIELDS: tuple[str, ...] = tuple(AutonomyPolicySettings.model_fields)
AUTONOMY_RULE_FIELDS: tuple[str, ...] = tuple(AutonomyRuleSettings.model_fields)
AUTONOMY_SCOPE_FIELDS: tuple[str, ...] = tuple(AutonomyScopeSettings.model_fields)
FREEZE_WINDOW_FIELDS: tuple[str, ...] = tuple(FreezeWindowSettings.model_fields)
AUTONOMY_BUDGET_FIELDS: tuple[str, ...] = tuple(AutonomyBudgetSettings.model_fields)
AUTONOMY_OVERRIDE_FIELDS: tuple[str, ...] = tuple(AutonomyOverrideSettings.model_fields)
MEMORY_FIELDS: tuple[str, ...] = tuple(MemoryPolicySettings.model_fields)
STRATEGY_FIELDS: tuple[str, ...] = tuple(StrategyPolicySettings.model_fields)
KNOWLEDGE_FIELDS: tuple[str, ...] = tuple(KnowledgePolicySettings.model_fields)
MASKING_FIELDS: tuple[str, ...] = tuple(MaskingPolicySettings.model_fields)
GUARDRAILS_FIELDS: tuple[str, ...] = tuple(GuardrailPolicySettings.model_fields)
APPROVALS_FIELDS: tuple[str, ...] = tuple(ApprovalPolicySettings.model_fields)
OBSERVATION_FIELDS: tuple[str, ...] = tuple(ObservationPolicySettings.model_fields)
DETECTOR_FIELDS: tuple[str, ...] = tuple(DetectorSettings.model_fields)
CUSTOM_PATTERN_FIELDS: tuple[str, ...] = tuple(CustomMaskingPattern.model_fields)


__all__ = [
    "APPROVALS_FIELDS",
    "AUTONOMY_BUDGET_FIELDS",
    "AUTONOMY_FIELDS",
    "AUTONOMY_OVERRIDE_FIELDS",
    "AUTONOMY_RULE_FIELDS",
    "AUTONOMY_SCOPE_FIELDS",
    "CUSTOM_PATTERN_FIELDS",
    "DETECTOR_FIELDS",
    "GUARDRAILS_FIELDS",
    "GUARDRAIL_MODES",
    "GUARDRAIL_MODE_ENFORCING",
    "GUARDRAIL_MODE_OBSERVING",
    "GuardrailMode",
    "KNOWLEDGE_FIELDS",
    "MASKING_FIELDS",
    "MEMORY_FIELDS",
    "OBSERVATION_FIELDS",
    "POLICIES_FIELDS",
    "STRATEGY_FIELDS",
    "ApprovalPolicySettings",
    "AutonomyBudgetSettings",
    "AutonomyLabelSettings",
    "AutonomyOverrideSettings",
    "AutonomyPolicySettings",
    "AutonomyRuleSettings",
    "AutonomyScopeSettings",
    "CustomMaskingPattern",
    "DetectorSettings",
    "FREEZE_WINDOW_FIELDS",
    "FreezeWindowSettings",
    "GuardrailPolicySettings",
    "KnowledgePolicySettings",
    "MaskingPolicySettings",
    "MemoryPolicySettings",
    "ObservationPolicySettings",
    "PoliciesConfig",
    "StrategyPolicySettings",
]
