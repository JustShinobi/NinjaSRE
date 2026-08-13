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
from config.constants.observability_bridge import (
    BRIDGE_VIEW_HYPERVISOR,
    BRIDGE_VIEWS,
    DEFAULT_HISTORY_LOOKBACK_SECONDS,
    DEFAULT_LOG_WINDOW_SECONDS,
    DEFAULT_MAPPING_INTERVAL_SECONDS,
    MAX_HISTORY_LOOKBACK_SECONDS,
    MAX_LOG_LINES,
    MAX_LOG_WINDOW_SECONDS,
    MIN_MAPPING_INTERVAL_SECONDS,
    PRECEDENCE_SOURCES,
)
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
    OIDC_DEFAULT_SCOPES,
    OIDC_EMAIL_CLAIM,
    OIDC_GROUPS_CLAIM,
    OIDC_NAME_CLAIM,
    OIDC_SUBJECT_CLAIM,
    SIDE_EFFECT_LEVELS,
    SIDE_EFFECT_WRITE_REVERSIBLE,
)
from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredFloat,
    ConfiguredInt,
    ConfiguredStr,
    ConfiguredStrList,
    field_help,
    section_help,
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

    model_config = section_help(
        "Whether investigations may look up what happened last time, and whether they "
        "add what happened this time. The two switch separately so you can keep the "
        "record while measuring what consulting it is worth."
    )

    read_enabled: Annotated[
        bool,
        field_help("Let an investigation recall similar past incidents while it works."),
    ] = True
    write_enabled: Annotated[
        bool,
        field_help("Record this team's finished investigations so later ones can recall them."),
    ] = True


class StrategyPolicySettings(ConfigSection):
    """Whether synthesised playbooks are offered alongside episodes."""

    model_config = section_help(
        "Whether the platform may offer the playbooks it has distilled from repeated "
        "incidents, as well as the incidents themselves."
    )

    enabled: Annotated[
        bool,
        field_help("Offer distilled playbooks to an investigation alongside past incidents."),
    ] = True


class KnowledgePolicySettings(ConfigSection):
    """Whether the topology graph and the knowledge base are reachable."""

    model_config = section_help(
        "Whether an investigation may consult what this deployment knows about the "
        "estate: how things are connected, and the documents you have given it."
    )

    topology_enabled: Annotated[
        bool,
        field_help("Let an investigation follow how resources depend on one another."),
    ] = True
    knowledge_base_enabled: Annotated[
        bool,
        field_help("Let an investigation search your runbooks, postmortems and notes."),
    ] = True


class CustomMaskingPattern(ConfigSection):
    """One operator-supplied identifier shape.

    The name becomes part of the token, so ``NSRE_MASK_TICKET_1`` reads in a
    prompt where ``NSRE_MASK_CUSTOM_1`` does not — which is why it is required
    rather than generated.
    """

    model_config = section_help(
        "One identifier shape of your own to hide before anything leaves for a model — "
        "a ticket number, an internal hostname scheme."
    )

    #: Both required. A pattern with no name produces an unreadable token and
    #: one with no expression matches nothing; defaults would hide either.
    name: Annotated[
        ConfiguredStr,
        field_help(
            "A short name for this shape. It appears in the placeholder that replaces "
            "the value, so make it recognisable."
        ),
    ]
    pattern: Annotated[
        ConfiguredStr,
        field_help("A regular expression matching the values to hide."),
    ]


class MaskingPolicySettings(ConfigSection):
    """How much of the operator's estate may reach a model they do not host."""

    model_config = section_help(
        "How much about your estate is allowed to reach a model you do not host. "
        "Identifiers are replaced with placeholders on the way out and restored on the "
        "way back, so a report still reads normally."
    )

    enabled: Annotated[
        bool,
        field_help("Hide identifying values before they are sent to a model."),
    ] = True
    level: Annotated[
        ConfiguredStr,
        field_help(
            "How much is hidden. A stricter level covers more kinds of value and gives "
            "the model less to work with."
        ),
    ] = DEFAULT_MASKING_POLICY
    custom_patterns: Annotated[
        tuple[CustomMaskingPattern, ...],
        field_help("Extra value shapes of your own to hide, beyond the ones shipped."),
    ] = ()

    @field_validator("level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        """Refuse a level the masking layer does not implement."""
        if value not in MASKING_POLICY_LEVELS:
            raise ValueError(f"must be one of {', '.join(MASKING_POLICY_LEVELS)}; found {value!r}")
        return value


class GuardrailPolicySettings(ConfigSection):
    """Which secret shapes are looked for, and whether a match is acted on."""

    model_config = section_help(
        "What the platform does when it spots something that looks like a secret. It "
        "always looks; this decides whether a match is blocked or only recorded."
    )

    mode: Annotated[
        GuardrailMode,
        field_help(
            "Enforcing blocks or redacts a match. Observing records it and changes "
            "nothing, which is how you find out what enforcing would have done."
        ),
    ] = GUARDRAIL_MODE_ENFORCING
    ruleset: Annotated[
        ConfiguredStr | None,
        field_help("Which named set of rules to use. Empty means the shipped set."),
    ] = None
    disabled_rules: Annotated[
        ConfiguredStrList,
        field_help(
            "Rules to switch off by name, for the ones that keep matching something "
            "harmless in your estate."
        ),
    ] = ()

    @property
    def enforcing(self) -> bool:
        """Return whether a match alters or blocks rather than only recording."""
        return self.mode == GUARDRAIL_MODE_ENFORCING


class ApprovalPolicySettings(ConfigSection):
    """Where the line between "do it" and "ask first" sits for this team.

    ``threshold`` is the lowest side-effect level that needs a human. It cannot
    be raised past ``write_reversible``: every write needs per-action approval
    and a stored rollback plan, and a configuration field that could switch that
    off would make the guarantee a preference.
    """

    model_config = section_help(
        "Where the line sits between what the platform does on its own and what it asks "
        "about first. Anything that writes always needs a person."
    )

    threshold: Annotated[
        ConfiguredStr,
        field_help(
            "The lowest kind of action that needs a person to say yes. It cannot be set "
            "so high that a write goes through unapproved."
        ),
    ] = SIDE_EFFECT_WRITE_REVERSIBLE
    autonomous_capabilities: Annotated[
        ConfiguredStrList,
        field_help(
            "Named capabilities this team has decided need no approval, whatever the "
            "threshold says."
        ),
    ] = ()
    expiry_hours: Annotated[
        ConfiguredFloat,
        Field(ge=0.25, le=MAX_APPROVAL_EXPIRY_HOURS),
        field_help(
            "How long a request waits for an answer before it lapses. Long enough for "
            "the on-call to see it, short enough that nobody approves a plan for a "
            "system that has since changed."
        ),
    ] = DEFAULT_APPROVAL_EXPIRY_HOURS

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

    model_config = section_help(
        "One thing this team watches for, and the point at which it becomes an incident."
    )

    #: Both required. A detector with no identifier cannot be enabled, disabled
    #: or referred to in an incident, and one with no signal reads nothing.
    detector_id: Annotated[
        ConfiguredStr,
        field_help("A short identifier for this detector. Incidents it opens are named by it."),
    ]
    signal: Annotated[
        ConfiguredStr,
        field_help("Which measurement it watches."),
    ]
    name: Annotated[
        ConfiguredStr, field_help("A readable title, shown wherever this detector appears.")
    ] = ""
    description: Annotated[
        ConfiguredStr,
        field_help("What going wrong here means, for whoever reads the incident at 03:00."),
    ] = ""
    kind: Annotated[
        ConfiguredStr,
        field_help(
            "What sort of condition this is: a value crossing a threshold, a change of "
            "state, an absence of data."
        ),
    ] = DETECTOR_KIND_THRESHOLD
    comparison: Annotated[
        ConfiguredStr,
        field_help("Whether it fires when the measurement goes above the value or below it."),
    ] = DETECTOR_COMPARISON_ABOVE
    resource_kinds: Annotated[
        ConfiguredStrList,
        field_help("Which kinds of resource this applies to. Empty means all of them."),
    ] = ()
    fire_value: Annotated[ConfiguredFloat, field_help("The value at which this starts firing.")] = (
        0.0
    )
    clear_value: Annotated[
        ConfiguredFloat,
        field_help(
            "The value at which it stops. Set it back from the firing value so a "
            "measurement hovering on the line does not open and close repeatedly."
        ),
    ] = 0.0
    silent_after_seconds: Annotated[
        ConfiguredInt,
        Field(ge=0),
        field_help(
            "How long a measurement may go missing before that silence is itself the "
            "problem. Zero means never."
        ),
    ] = 0
    to_state: Annotated[
        ConfiguredStr, field_help("For a state change: the state being entered.")
    ] = ""
    from_state: Annotated[
        ConfiguredStr, field_help("For a state change: the state being left.")
    ] = ""
    for_seconds: Annotated[
        ConfiguredInt,
        Field(ge=1),
        field_help("How long the condition must hold before an incident is opened."),
    ] = DEFAULT_DETECTOR_DURATION_SECONDS
    recovery_seconds: Annotated[
        ConfiguredInt,
        Field(ge=1),
        field_help("How long it must be clear again before the incident is closed."),
    ] = DEFAULT_DETECTOR_DURATION_SECONDS
    severity: Annotated[ConfiguredStr, field_help("How serious an incident this opens.")] = (
        SEVERITY_HIGH
    )
    grouping_key: Annotated[
        ConfiguredStr,
        field_help(
            "What counts as the same incident: one per detector, or one per affected resource."
        ),
    ] = DETECTOR_GROUPING_DETECTOR
    enabled: Annotated[
        bool, field_help("Off keeps the detector configured and stops it watching.")
    ] = True
    capabilities: Annotated[
        ConfiguredStrList,
        field_help("Capabilities to reach for first when investigating what this detector finds."),
    ] = ()
    #: Where this detector came from, when it was not written by hand — the
    #: identifier of the document that proposed it. Empty for every shipped and
    #: operator-authored detector, which is what makes it the thing a listing
    #: sorts candidates by.
    origin: Annotated[
        ConfiguredStr,
        field_help(
            "Where this detector came from, when it was proposed rather than written by "
            "hand. Empty for the ones you and the platform wrote."
        ),
    ] = ""
    #: The sentence the proposing document's author wrote. An operator deciding
    #: whether a threshold is right needs the reason beside it, and for a
    #: proposed detector the reason is in somebody else's document.
    origin_excerpt: Annotated[
        ConfiguredStr,
        field_help("The reasoning the proposal gave, so the number can be judged on it."),
    ] = ""

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


class DetectorOverrideSettings(ConfigSection):
    """One shipped detector's threshold, changed without editing the shipped set.

    Two scopes and no third. An override with no ``resource_id`` applies to
    every resource this deployment watches with that detector; one with a
    ``resource_id`` applies to that resource alone and wins over the
    deployment-wide one. Anything more expressive would be a rule language, and
    the reason not to build one here is the same reason a detector has four
    condition kinds.

    Every field except the identifier is optional, because an operator changing
    a firing value should not have to restate the duration, the severity, and
    the clear value in order to keep them.
    """

    model_config = section_help(
        "A change to one of the shipped detectors, for this deployment. Fill in only "
        "what is different; everything left blank keeps the shipped value."
    )

    detector_id: Annotated[ConfiguredStr, field_help("Which shipped detector this changes.")]
    #: Empty means "every resource this detector applies to".
    resource_id: Annotated[
        ConfiguredStr,
        field_help(
            "Which resource the change applies to. Empty applies it everywhere the "
            "detector runs; naming one wins over the deployment-wide change."
        ),
    ] = ""
    fire_value: Annotated[
        ConfiguredFloat | None, field_help("A different value to start firing at.")
    ] = None
    clear_value: Annotated[
        ConfiguredFloat | None, field_help("A different value to stop firing at.")
    ] = None
    for_seconds: Annotated[
        Annotated[ConfiguredInt, Field(ge=1)] | None,
        field_help("A different length of time the condition must hold first."),
    ] = None
    recovery_seconds: Annotated[
        Annotated[ConfiguredInt, Field(ge=1)] | None,
        field_help("A different length of time it must be clear before closing."),
    ] = None
    severity: Annotated[
        ConfiguredStr, field_help("A different severity for the incidents this opens.")
    ] = ""
    enabled: Annotated[bool | None, field_help("Switch this shipped detector off, or back on.")] = (
        None
    )
    #: Why the shipped number is wrong for this deployment. Not required — an
    #: operator who has to justify themselves to their own tool will stop using
    #: it — but recorded when given, because the next person to read the
    #: override deserves the same courtesy the shipped rationale gave them.
    reason: Annotated[
        ConfiguredStr,
        field_help("Why the shipped number is wrong here. Optional, and worth writing."),
    ] = ""


class GuardianSettings(ConfigSection):
    """Whether the shipped detector set is watching, and what has been changed about it.

    Off by default: the set ships with the integration and is enabled by choice.
    Turning it on is a single flag because that is the whole interaction the
    feature promises — paste a token, enable the guardian, read what it would
    have done.

    ``heartbeat_destination`` has no default and cannot be switched off while
    the guardian is enabled. It is the only outbound thing here, and it is the
    answer to the failure this whole package is shaped around: a guardian that
    has stopped looks exactly like a cluster with no problems.
    """

    model_config = section_help(
        "The detector set that ships with the platform: whether it is watching, and what "
        "this deployment has changed about it."
    )

    enabled: Annotated[
        bool,
        field_help("Run the shipped detectors against this estate. Off by default."),
    ] = False
    #: Which topology the deployment detected, when it has. Stored so a listing
    #: can say *why* a two-node detector is or is not active without re-reading
    #: the cluster.
    cluster_shape: Annotated[
        ConfiguredStr,
        field_help(
            "The shape of cluster that was detected. It decides which shipped detectors "
            "make sense here — some only apply once there is more than one node."
        ),
    ] = ""
    overrides: Annotated[
        tuple[DetectorOverrideSettings, ...],
        field_help("Changes to individual shipped detectors, without editing the set."),
    ] = ()
    #: Where the outbound heartbeat is pushed. A URL the operator chooses — a
    #: dead-man's-switch service, a webhook, their own phone. Empty is a
    #: configuration the deployment warns about continuously rather than one it
    #: accepts silently.
    heartbeat_destination: Annotated[
        ConfiguredStr,
        field_help(
            "Where to send a regular sign of life. Required while the shipped detectors "
            "are running: a watcher that has stopped looks exactly like a healthy estate."
        ),
    ] = ""
    #: Where the operator's declarative control plane declares intent. Read as a
    #: second source of truth about what *should* be running; never written to.
    declared_intent_source: Annotated[
        ConfiguredStr,
        field_help(
            "Where you declare what is meant to be running, so the platform can tell a "
            "deliberate shutdown from a failure. Only ever read."
        ),
    ] = ""


class MetricsSourceSettings(ConfigSection):
    """A metrics system the operator already runs, and where to reach it.

    ``endpoint`` is here as well as in the integration's own connection settings
    because the bridge needs the *host* to answer one question the connection
    cannot: whether the metrics system is running inside the estate it observes.
    """

    model_config = section_help(
        "A metrics system you already run, joined to the estate so investigations can read from it."
    )

    enabled: Annotated[bool, field_help("Read metrics from this system.")] = False
    name: Annotated[ConfiguredStr, field_help("Which metrics system it is.")] = ""
    endpoint: Annotated[
        ConfiguredStr,
        field_help(
            "Its address. Also how the platform tells whether the metrics system runs "
            "inside the estate it is watching."
        ),
    ] = ""
    integration: Annotated[
        ConfiguredStr,
        field_help("Which connected integration carries the queries and holds the credential."),
    ] = ""


class LogSourceSettings(ConfigSection):
    """A log system the operator already runs, and where to reach it."""

    model_config = section_help(
        "A log system you already run, joined to the estate so investigations can read from it."
    )

    enabled: Annotated[bool, field_help("Read logs from this system.")] = False
    name: Annotated[ConfiguredStr, field_help("Which log system it is.")] = ""
    endpoint: Annotated[ConfiguredStr, field_help("Its address.")] = ""
    integration: Annotated[
        ConfiguredStr,
        field_help("Which connected integration carries the queries and holds the credential."),
    ] = ""


class LabelRuleSettings(ConfigSection):
    """One declared association between a family of series and a kind of resource.

    ``when_labels`` is a list of ``label=prefix`` strings rather than a mapping,
    matching the flat shape every other section uses — a nested free-form
    mapping would be the one place in this document where the console cannot
    render a form.
    """

    model_config = section_help(
        "One rule tying a family of measurements to the kind of resource they are about, "
        "so a series found in your monitoring can be matched to something in the estate."
    )

    rule_id: Annotated[ConfiguredStr, field_help("A short identifier for this rule.")]
    resource_kind: Annotated[
        ConfiguredStr, field_help("The kind of resource these measurements describe.")
    ]
    integration: Annotated[
        ConfiguredStr, field_help("Which connected integration these measurements come from.")
    ]
    native_template: Annotated[
        ConfiguredStr,
        field_help("How to build the resource identifier out of the measurement's labels."),
    ]
    metric_prefixes: Annotated[
        ConfiguredStrList,
        field_help("Measurement names starting with any of these are covered by this rule."),
    ] = ()
    when_labels: Annotated[
        ConfiguredStrList,
        field_help(
            "Extra conditions on the labels, written as label=prefix. All of them must "
            "hold for the rule to apply."
        ),
    ] = ()
    view: Annotated[
        ConfiguredStr,
        field_help("Which layer of the estate this rule describes."),
    ] = BRIDGE_VIEW_HYPERVISOR
    description: Annotated[
        ConfiguredStr, field_help("What this rule is for, for whoever reads it next.")
    ] = ""

    @field_validator("view")
    @classmethod
    def _known_view(cls, value: str) -> str:
        """Refuse a view the mapping does not model."""
        if value not in BRIDGE_VIEWS:
            raise ValueError(f"must be one of {', '.join(BRIDGE_VIEWS)}; found {value!r}")
        return value


class LogSelectorSettings(ConfigSection):
    """The stream selector that applies to one kind of resource."""

    model_config = section_help("How to find the logs belonging to one kind of resource.")

    rule_id: Annotated[ConfiguredStr, field_help("A short identifier for this selector.")]
    resource_kind: Annotated[
        ConfiguredStr, field_help("The kind of resource whose logs this finds.")
    ]
    template: Annotated[
        ConfiguredStr,
        field_help("The query to run, with the resource's own details filled in."),
    ]
    description: Annotated[
        ConfiguredStr, field_help("What this selector is for, for whoever reads it next.")
    ] = ""


class DashboardMappingSettings(ConfigSection):
    """One dashboard, and what it is the picture of."""

    model_config = section_help(
        "One of your existing dashboards, and what it is a picture of — so an incident "
        "can link straight to it."
    )

    dashboard_uid: Annotated[
        ConfiguredStr, field_help("The dashboard's identifier in your monitoring system.")
    ]
    base_url: Annotated[ConfiguredStr, field_help("The address the dashboard is served from.")]
    title: Annotated[ConfiguredStr, field_help("What to call it in the link.")] = ""
    resource_kinds: Annotated[
        ConfiguredStrList, field_help("Which kinds of resource this dashboard is about.")
    ] = ()
    detector_ids: Annotated[
        ConfiguredStrList,
        field_help("Which detectors this dashboard helps with. Incidents they open link here."),
    ] = ()
    panel_id: Annotated[
        ConfiguredStr, field_help("A single panel to link to, rather than the whole dashboard.")
    ] = ""
    description: Annotated[ConfiguredStr, field_help("What the dashboard shows.")] = ""


class SignalPrecedenceSettings(ConfigSection):
    """Which side produces a signal both the bridge and the deployment can gather."""

    model_config = section_help(
        "For a measurement both your monitoring and the platform's own polling can "
        'produce: which one is used. There is deliberately no "both".'
    )

    signal: Annotated[ConfiguredStr, field_help("The measurement in question.")]
    winner: Annotated[
        ConfiguredStr,
        field_help("Which side supplies it: your monitoring, or the platform's own polling."),
    ]
    reason: Annotated[ConfiguredStr, field_help("Why that side is the better source here.")]

    @field_validator("winner")
    @classmethod
    def _known_winner(cls, value: str) -> str:
        """Refuse a winner that is neither side. There is deliberately no 'both'."""
        if value not in PRECEDENCE_SOURCES:
            raise ValueError(f"must be one of {', '.join(PRECEDENCE_SOURCES)}; found {value!r}")
        return value


class ObservabilityBridgeSettings(ConfigSection):
    """The monitoring the operator already runs, and how it joins to the estate.

    Every field defaults to off or to the shipped set. A deployment with no
    observability stack leaves this section absent and works entirely from its
    own polling, which is what makes the whole feature additive rather than a
    dependency.
    """

    model_config = section_help(
        "The monitoring you already run, joined to what the platform knows about your "
        "estate. Leave it off and the platform watches entirely by its own polling."
    )

    enabled: Annotated[
        bool, field_help("Use your existing monitoring as a source alongside the platform's own.")
    ] = False
    metrics: MetricsSourceSettings = MetricsSourceSettings()
    logs: LogSourceSettings = LogSourceSettings()
    dashboard_base_url: Annotated[
        ConfiguredStr,
        field_help("Where your dashboards are served from, so incidents can link to them."),
    ] = ""
    #: Whether the shipped exporter mappings are used. On by default: the label
    #: schemes of the Proxmox and node exporters are stable, and an operator who
    #: had to declare them would have to learn a mapping language before the
    #: bridge did anything at all.
    use_shipped_rules: Annotated[
        bool,
        field_help(
            "Use the mappings that ship with the platform for the common exporters. On "
            "by default, so the bridge does something useful before you declare anything."
        ),
    ] = True
    label_rules: Annotated[
        tuple[LabelRuleSettings, ...],
        field_help("Your own mappings, for measurements the shipped ones do not cover."),
    ] = ()
    use_shipped_log_selectors: Annotated[
        bool, field_help("Use the shipped queries for finding a resource's logs.")
    ] = True
    log_selectors: Annotated[
        tuple[LogSelectorSettings, ...],
        field_help("Your own log queries, for resources the shipped ones do not cover."),
    ] = ()
    dashboards: Annotated[
        tuple[DashboardMappingSettings, ...],
        field_help("Your dashboards, and what each one is a picture of."),
    ] = ()
    precedence: Annotated[
        tuple[SignalPrecedenceSettings, ...],
        field_help(
            "For measurements both sides can produce, which one wins. Anything not "
            "listed keeps the platform's default choice."
        ),
    ] = ()
    mapping_interval_seconds: Annotated[
        ConfiguredInt,
        Field(ge=MIN_MAPPING_INTERVAL_SECONDS),
        field_help("How often to re-match your monitoring's series against the estate."),
    ] = DEFAULT_MAPPING_INTERVAL_SECONDS
    history_lookback_seconds: Annotated[
        ConfiguredInt,
        Field(ge=1, le=MAX_HISTORY_LOOKBACK_SECONDS),
        field_help("How far back to read history when an investigation asks what happened."),
    ] = DEFAULT_HISTORY_LOOKBACK_SECONDS
    log_window_seconds: Annotated[
        ConfiguredInt,
        Field(ge=1, le=MAX_LOG_WINDOW_SECONDS),
        field_help("How much time either side of an event to pull logs for."),
    ] = DEFAULT_LOG_WINDOW_SECONDS
    log_line_limit: Annotated[
        ConfiguredInt,
        Field(ge=1, le=MAX_LOG_LINES),
        field_help("The most log lines one read may return."),
    ] = MAX_LOG_LINES


class ObservationPolicySettings(ConfigSection):
    """What this team watches for, and whether it is watching at all.

    ``paused`` is the global stop. It suppresses every detector this node
    resolves without unconfiguring any of them, so an operator who needs the
    deployment to stop opening incidents during a migration does not have to
    delete the detectors and remember to put them back.
    """

    model_config = section_help("What this team watches for, and whether it is watching at all.")

    detectors: Annotated[
        tuple[DetectorSettings, ...],
        field_help("The detectors this team has written, on top of any shipped ones."),
    ] = ()
    paused: Annotated[
        bool,
        field_help(
            "Stop opening incidents for this team without unconfiguring anything — for a "
            "migration or a planned outage."
        ),
    ] = False
    pause_reason: Annotated[
        ConfiguredStr,
        field_help("Why watching is paused, so the next person knows whether to resume it."),
    ] = ""
    #: The operator's own monitoring, joined to the estate. Absent by default,
    #: and a deployment that leaves it absent watches entirely by its own
    #: polling — which is the arrangement most homelabs are in.
    bridge: ObservabilityBridgeSettings = ObservabilityBridgeSettings()
    #: The shipped detector set, and what this deployment has changed about it.
    #: Here rather than as a seventh top-level section for the reason the
    #: detectors themselves are here: whether this team runs the shipped set is
    #: a policy about what it watches, not a separate concern.
    guardian: GuardianSettings = GuardianSettings()


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

    model_config = section_help(
        "One label a scope selects on. Both halves are needed: a name with no value "
        "would select everything."
    )

    #: Both required. A label with no name selects nothing and one with no value
    #: selects everything, and a default would hide either.
    name: Annotated[ConfiguredStr, field_help("The label to look at.")]
    value: Annotated[ConfiguredStr, field_help("The value it has to have.")]


class AutonomyScopeSettings(ConfigSection):
    """Where a rule, a freeze, a budget or an override applies.

    Validated here as well as in the engine. This is the save-time half: an
    operator writing a scope whose kind and fields disagree finds out when they
    write it, rather than when something declines to act because of it.
    """

    model_config = section_help(
        "Where this applies. Pick how wide it reaches, then name the thing it reaches — "
        "everywhere, one team, one kind of resource, one resource, or one capability."
    )

    kind: Annotated[
        ConfiguredStr,
        field_help(
            "How wide this reaches. Each choice needs the matching field below filled in; "
            "the deployment-wide choice needs none."
        ),
    ] = AUTONOMY_SCOPE_DEPLOYMENT
    team_node_id: Annotated[
        ConfiguredStr, field_help("Which team, when the scope is one team.")
    ] = ""
    resource_kind: Annotated[
        ConfiguredStr, field_help("Which kind of resource, when the scope is one kind.")
    ] = ""
    resource_id: Annotated[
        ConfiguredStr, field_help("Which resource, when the scope is a single one.")
    ] = ""
    capability: Annotated[
        ConfiguredStr, field_help("Which capability, when the scope is one action.")
    ] = ""
    labels: Annotated[
        tuple[AutonomyLabelSettings, ...],
        field_help("Which labels a resource must carry, when the scope selects by label."),
    ] = ()

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

    model_config = section_help(
        "One statement of how much the platform may do by itself somewhere: here, this "
        "much freedom, up to this much risk."
    )

    scope: AutonomyScopeSettings = AutonomyScopeSettings()
    level: Annotated[
        ConfiguredStr,
        field_help("How much may happen without a person: nothing, ask first, or act."),
    ] = DEFAULT_AUTONOMY_LEVEL
    risk_bound: Annotated[
        ConfiguredStr,
        field_help("The riskiest class of action this rule allows, whatever the level says."),
    ] = DEFAULT_RISK_BOUND
    dry_run: Annotated[
        bool,
        field_help(
            "Go through the motions and change nothing, so you can read what would have happened."
        ),
    ] = False

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

    model_config = section_help(
        "A stretch of the day when nothing in scope may act — a change freeze, a nightly "
        "batch window."
    )

    #: Required. A refusal has to name what refused it, and "a freeze window"
    #: sends an operator to read every one they have.
    name: Annotated[
        ConfiguredStr,
        field_help("What this window is called. A refusal names it, so make it recognisable."),
    ]
    start: Annotated[ConfiguredStr, field_help("What time it begins, like 22:00.")]
    end: Annotated[ConfiguredStr, field_help("What time it ends. It may not equal the start.")]
    scope: AutonomyScopeSettings = AutonomyScopeSettings()
    timezone: Annotated[
        ConfiguredStr,
        field_help("The timezone the two times are read in."),
    ] = DEFAULT_FREEZE_TIMEZONE
    reason: Annotated[ConfiguredStr, field_help("Why this window exists, for whoever hits it.")] = (
        ""
    )

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

    model_config = section_help(
        "A cap on how much may happen by itself in a stretch of time, so a repeating "
        "fault cannot be repaired in a loop."
    )

    #: Required. An exhaustion has to name which budget is spent.
    name: Annotated[
        ConfiguredStr, field_help("What this budget is called. It is named when it runs out.")
    ]
    counted_by: Annotated[
        ConfiguredStr,
        field_help("What the count is kept against: per resource, per capability, or overall."),
    ] = AUTONOMY_BUDGET_SCOPE_RESOURCE
    limit: Annotated[
        ConfiguredInt,
        Field(ge=0),
        field_help("How many actions are allowed in one interval. Zero allows none."),
    ] = DEFAULT_AUTONOMY_BUDGET
    interval_seconds: Annotated[
        ConfiguredFloat,
        Field(gt=0),
        field_help("How long the interval is, in seconds."),
    ] = DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS
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

    model_config = section_help(
        "A temporary raise in what may happen without asking — for an incident, a "
        "migration — that ends on its own at a stated moment."
    )

    #: Both required. An expiry has to name what expired, and an override with
    #: no end is a policy change wearing an override's name.
    name: Annotated[
        ConfiguredStr, field_help("What this override is called. It is named when it expires.")
    ]
    expires_at: Annotated[
        ConfiguredStr,
        field_help(
            "When it ends, as a date and time including the timezone offset. An override "
            "with no end is a policy change, not an override."
        ),
    ]
    scope: AutonomyScopeSettings = AutonomyScopeSettings()
    level: Annotated[
        ConfiguredStr, field_help("How much may happen without a person while this is in force.")
    ] = DEFAULT_AUTONOMY_LEVEL
    risk_bound: Annotated[
        ConfiguredStr, field_help("The riskiest class of action allowed while this is in force.")
    ] = DEFAULT_RISK_BOUND
    granted_by: Annotated[ConfiguredStr, field_help("Who granted it.")] = ""
    reason: Annotated[ConfiguredStr, field_help("Why it was granted.")] = ""

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

    model_config = section_help(
        "How much this team may do without asking, and the limits on the answer: the "
        "rules, the times nothing may run, the caps, and any temporary raises."
    )

    rules: Annotated[
        tuple[AutonomyRuleSettings, ...],
        field_help("Statements of how much freedom applies where. The most specific one wins."),
    ] = ()
    freezes: Annotated[
        tuple[FreezeWindowSettings, ...],
        field_help("Stretches of the day when nothing in scope may act."),
    ] = ()
    budgets: Annotated[
        tuple[AutonomyBudgetSettings, ...],
        field_help("Caps on how much may happen by itself over an interval."),
    ] = ()
    overrides: Annotated[
        tuple[AutonomyOverrideSettings, ...],
        field_help("Temporary raises that end by themselves."),
    ] = ()
    #: Simulate everything this node resolves, whatever any rule says. The
    #: deployment-wide half of dry-run mode; the per-scope half is on the rule.
    dry_run: Annotated[
        bool,
        field_help(
            "Simulate every action for this team, whatever any rule says, and change "
            "nothing. The safest way to start."
        ),
    ] = False
    #: Whether an action whose effect no signal reports may run unattended.
    #: Defaults to ``False``, and the default is the decision: a capability
    #: nobody can verify is one the deployment would act on and never find out
    #: about, so it takes a human approval until an operator says otherwise.
    allow_unverifiable_actions: Annotated[
        bool,
        field_help(
            "Let an action run unattended even when nothing can confirm afterwards that "
            "it worked. Off by default: otherwise the platform acts and never finds out."
        ),
    ] = False
    #: How many times one capability may be applied to one resource inside the
    #: window before it stops being an incident and becomes a recurring problem.
    #: Zero means the deployment default.
    recurrence_threshold: Annotated[
        int,
        field_help(
            "How many times the same fix may be applied to the same resource in the "
            "window before it is treated as a recurring problem rather than an incident. "
            "Zero uses the deployment default; two is the smallest number that can be a "
            "pattern."
        ),
    ] = 0
    #: How long that window is, in seconds. Zero means the deployment default.
    recurrence_window_seconds: Annotated[
        int,
        field_help("How long that window is, in seconds. Zero uses the deployment default."),
    ] = 0

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


class GitHostSettings(ConfigSection):
    """One git host's commit listing, as a change source.

    ``vendor`` names which client reads it and ``repository`` names what to
    read. Both are needed: a vendor with no repository would compose a listing
    request for the empty string, which is a source that fails on every
    investigation rather than one that is absent.
    """

    model_config = section_help(
        "A git host to read recent commits from, so an investigation can see what "
        "changed before things broke."
    )

    vendor: Annotated[
        ConfiguredStr, field_help("Which git host it is. Needed together with the repository.")
    ] = ""
    repository: Annotated[
        ConfiguredStr, field_help("Which repository to read, as that host names it.")
    ] = ""


class ChangeSourceSettings(ConfigSection):
    """Where this deployment reads "what changed" from.

    Configuration rather than a build-time choice, because which of these a
    deployment has is a fact about the operator's estate. Both are optional and
    neither is a default: a deployment that configured none reports that nothing
    was consulted, which is a different finding from nothing having changed and
    leads somewhere different.
    """

    model_config = section_help(
        "Where this deployment finds out what changed recently. Configure neither and an "
        "investigation reports that nothing was consulted, which is different from "
        "nothing having changed."
    )

    #: The repository root whose ``.infra-state`` apply record is read. The
    #: repository root rather than the state directory, so it is the same path a
    #: deployment already configures its documentation corpus with.
    repository_path: Annotated[
        ConfiguredStr,
        field_help(
            "A checkout on this host whose recorded applies are read. Give the "
            "repository root, the same one your documentation is read from."
        ),
    ] = ""
    git_host: GitHostSettings = GitHostSettings()


class SsoClaimSettings(ConfigSection):
    """Which claim carries which fact.

    Overridable because "groups" is spelled at least four ways across the
    providers operators actually run, and a deployment that has to be patched to
    read its own directory is a deployment that forks.
    """

    model_config = section_help(
        "Which piece of the sign-in token carries which fact. Change these only if your "
        "provider spells them differently from the defaults."
    )

    subject: Annotated[
        ConfiguredStr, field_help("Which claim holds the user's stable identifier.")
    ] = OIDC_SUBJECT_CLAIM
    email: Annotated[ConfiguredStr, field_help("Which claim holds the user's email address.")] = (
        OIDC_EMAIL_CLAIM
    )
    display_name: Annotated[ConfiguredStr, field_help("Which claim holds the name to show.")] = (
        OIDC_NAME_CLAIM
    )
    groups: Annotated[
        ConfiguredStr,
        field_help("Which claim holds the user's groups. Providers spell this several ways."),
    ] = OIDC_GROUPS_CLAIM


class SsoSettings(ConfigSection):
    """The identity provider an operator points this deployment at.

    Configuration rather than a store of its own, which puts it under the same
    preview, provenance and audit as everything else somebody changes here — and
    keeps it out of the credential vault, where it does not belong: none of
    these fields is a secret.

    ``verified_digest`` is what binds a passing test to the settings that passed
    it. It holds the digest of the configuration a successful test was run
    against, so *editing anything invalidates the test by construction*: the
    digest is derived from the settings, and a changed setting produces a
    different one. That is the lockout prevention the whole flow exists for, and
    it is a property here rather than a rule somebody has to remember to apply.
    """

    model_config = section_help(
        "The identity provider people sign in through. Nothing here is a secret. Changes "
        "have to be tested again before they can be switched on, so a wrong value cannot "
        "lock everybody out."
    )

    provider: Annotated[ConfiguredStr, field_help("Which identity provider this is.")] = ""
    issuer: Annotated[
        ConfiguredStr,
        field_help("The provider's issuer address, as it appears in the tokens it signs."),
    ] = ""
    client_id: Annotated[
        ConfiguredStr, field_help("The client identifier this deployment was registered under.")
    ] = ""
    authorisation_endpoint: Annotated[
        ConfiguredStr, field_help("Where people are sent to sign in.")
    ] = ""
    token_endpoint: Annotated[
        ConfiguredStr, field_help("Where the sign-in is exchanged for a token.")
    ] = ""
    jwks_uri: Annotated[
        ConfiguredStr,
        field_help("Where the provider publishes the keys its tokens are signed with."),
    ] = ""
    redirect_uri: Annotated[
        ConfiguredStr,
        field_help(
            "Where the provider sends people back to. Must match what you registered with "
            "the provider exactly."
        ),
    ] = ""
    scopes: Annotated[
        ConfiguredStrList,
        field_help("What to ask the provider for. The defaults cover identity and groups."),
    ] = OIDC_DEFAULT_SCOPES
    claims: SsoClaimSettings = SsoClaimSettings()
    #: Provider group name to node id. A group naming no node is ignored, which
    #: is what lets a directory carry groups this deployment does not care about.
    group_to_node: Annotated[
        Mapping[str, str],
        field_help(
            "Which of your directory groups lands people on which team. A group naming "
            "no team is ignored."
        ),
    ] = {}
    #: Where a user with no mapped group lands. Without it there is no answer but
    #: refusal, and a directory change nobody made deliberately becomes an outage.
    default_node_id: Annotated[
        ConfiguredStr,
        field_help(
            "Where somebody lands when none of their groups is mapped. Without it, a "
            "directory change nobody meant becomes a lockout."
        ),
    ] = ""
    is_active: Annotated[
        bool,
        field_help(
            "Sign-in through this provider is live. It can only be switched on after a "
            "successful test."
        ),
    ] = False
    verified_digest: Annotated[
        ConfiguredStr,
        field_help(
            "Records which settings the last successful test was run against. Changing "
            "anything above clears it, so an untested change cannot go live."
        ),
    ] = ""


class PoliciesConfig(ConfigSection):
    """Every policy switch, in one section."""

    model_config = section_help(
        "What this deployment is allowed to do, and what it is allowed to learn from."
    )

    changes: ChangeSourceSettings = ChangeSourceSettings()
    sso: SsoSettings = SsoSettings()
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
