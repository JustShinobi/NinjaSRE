"""How much the deployment may do without asking, and the bounds on the answer.

Three ordered levels, five ordered risk classes, seven scope kinds, and the four
bounds no level overrides. Every one of them is a closed set written out here
rather than derived, for the reason the side-effect scale is written out in
``security``: a control whose coverage changes when somebody edits an enum is
not a control an operator agreed to.

The names are strings rather than an enum because this module is tier 4 and may
import nothing. ``platform.autonomy`` builds the enums over them, and a test
asserts the two agree — so a level added here and forgotten there fails the
build instead of resolving to nothing.
"""

from __future__ import annotations

from typing import Final

# --- Levels ------------------------------------------------------------------

#: The three defensible postures, least to most permissive, and the order is
#: load-bearing: it is what "least permissive" means when one action targets
#: several resources whose rules disagree.
#:
#: There is deliberately no fourth. A rule language for autonomy is a place to
#: write a bug that executes something at four in the morning, and anything
#: three levels plus a risk bound cannot express is a case for an approval.
AUTONOMY_LEVEL_PROPOSE_ONLY: Final = "propose_only"
AUTONOMY_LEVEL_ACT_ON_LOW_RISK: Final = "act_on_low_risk"
AUTONOMY_LEVEL_ACT_AND_REPORT: Final = "act_and_report"

AUTONOMY_LEVELS: Final[tuple[str, ...]] = (
    AUTONOMY_LEVEL_PROPOSE_ONLY,
    AUTONOMY_LEVEL_ACT_ON_LOW_RISK,
    AUTONOMY_LEVEL_ACT_AND_REPORT,
)

#: What the absence of every rule resolves to. Article III's default posture: a
#: deployment that configures nothing acts on nothing.
DEFAULT_AUTONOMY_LEVEL: Final = AUTONOMY_LEVEL_PROPOSE_ONLY

# --- Risk classes ------------------------------------------------------------

#: Five classes, least to most dangerous. Each one answers the same three
#: questions — can it be undone, how far does it reach, and can it lose data or
#: availability — and the class is the worst answer among them.
#:
#: ``trivial``  reversible, one resource, loses neither data nor availability.
#: ``low``      reversible, one resource, a brief loss of availability at most.
#: ``moderate`` reversible only by a further action, or reaching a few resources.
#: ``high``     not reversible without a restore, or reaching many resources.
#: ``critical`` can lose data that has no other copy, or take an estate down.
RISK_CLASS_TRIVIAL: Final = "trivial"
RISK_CLASS_LOW: Final = "low"
RISK_CLASS_MODERATE: Final = "moderate"
RISK_CLASS_HIGH: Final = "high"
RISK_CLASS_CRITICAL: Final = "critical"

RISK_CLASSES: Final[tuple[str, ...]] = (
    RISK_CLASS_TRIVIAL,
    RISK_CLASS_LOW,
    RISK_CLASS_MODERATE,
    RISK_CLASS_HIGH,
    RISK_CLASS_CRITICAL,
)

#: What an action carrying no declared class is treated as. The top of the
#: scale, never a middle value and never "unclassified": the difference is
#: between a new capability defaulting to "safe to run unattended" and
#: defaulting to "ask", and only one of those survives somebody forgetting a
#: field.
UNCLASSIFIED_RISK_CLASS: Final = RISK_CLASS_CRITICAL

#: Where ``act_on_low_risk`` draws its line when a rule names no bound of its
#: own. "Low" is the operator's definition; this is only the definition they get
#: before they have expressed one.
DEFAULT_RISK_BOUND: Final = RISK_CLASS_LOW

# --- Scopes ------------------------------------------------------------------

#: The seven places a level may be set, least to most specific. The order *is*
#: the precedence: resolution walks it, and the most specific applicable rule
#: wins.
#:
#: A label selector sits above a resource kind because it is a narrower
#: statement about the same population, and below an individual resource because
#: naming one machine is the narrowest thing an operator can say about it.
AUTONOMY_SCOPE_DEPLOYMENT: Final = "deployment"
AUTONOMY_SCOPE_TEAM: Final = "team"
AUTONOMY_SCOPE_RESOURCE_KIND: Final = "resource_kind"
AUTONOMY_SCOPE_LABELS: Final = "labels"
AUTONOMY_SCOPE_CAPABILITY: Final = "capability"
AUTONOMY_SCOPE_RESOURCE: Final = "resource"
AUTONOMY_SCOPE_CAPABILITY_RESOURCE: Final = "capability_resource"

AUTONOMY_SCOPE_KINDS: Final[tuple[str, ...]] = (
    AUTONOMY_SCOPE_DEPLOYMENT,
    AUTONOMY_SCOPE_TEAM,
    AUTONOMY_SCOPE_RESOURCE_KIND,
    AUTONOMY_SCOPE_LABELS,
    AUTONOMY_SCOPE_CAPABILITY,
    AUTONOMY_SCOPE_RESOURCE,
    AUTONOMY_SCOPE_CAPABILITY_RESOURCE,
)

#: How many rules one deployment may configure. Resolution is linear in the rule
#: count and is on the path of every action, so the ceiling is what stops a
#: generated policy set turning every decision into a scan of a table nobody
#: reads.
MAX_AUTONOMY_RULES: Final[int] = 1_000

#: What resolution is allowed to cost at that ceiling, on one action against one
#: subject. Measured rather than guessed: the benchmark asserts it, so a change
#: that makes resolution quadratic fails the gate rather than a deployment.
AUTONOMY_RESOLUTION_BUDGET_SECONDS: Final[float] = 0.010

# --- Bounds no level overrides -----------------------------------------------

#: The four gates evaluated after the level, in this order. Named, because a
#: refusal that did not say which one refused would send an operator to look at
#: the policy that permitted the action.
AUTONOMY_BOUND_KILL_SWITCH: Final = "kill_switch"
AUTONOMY_BOUND_FREEZE: Final = "freeze"
AUTONOMY_BOUND_BUDGET: Final = "budget"
AUTONOMY_BOUND_ROLLBACK: Final = "rollback"

AUTONOMY_BOUNDS: Final[tuple[str, ...]] = (
    AUTONOMY_BOUND_KILL_SWITCH,
    AUTONOMY_BOUND_FREEZE,
    AUTONOMY_BOUND_BUDGET,
    AUTONOMY_BOUND_ROLLBACK,
)

#: What a budget permits, and over how long, when a rule names neither. Small
#: and hourly for the reason the allow-list's rate limit is: this bounds how
#: many times a policy can be wrong before somebody notices.
DEFAULT_AUTONOMY_BUDGET: Final[int] = 5
DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS: Final[float] = 60 * 60.0

#: The three things a budget may be counted against. One action spends every
#: budget that covers it, so a team budget and a per-resource budget are both
#: ceilings rather than alternatives.
AUTONOMY_BUDGET_SCOPE_RESOURCE: Final = "resource"
AUTONOMY_BUDGET_SCOPE_CAPABILITY: Final = "capability"
AUTONOMY_BUDGET_SCOPE_TEAM: Final = "team"

AUTONOMY_BUDGET_SCOPES: Final[tuple[str, ...]] = (
    AUTONOMY_BUDGET_SCOPE_RESOURCE,
    AUTONOMY_BUDGET_SCOPE_CAPABILITY,
    AUTONOMY_BUDGET_SCOPE_TEAM,
)

#: How far back a budget count reads, in rows, before it stops counting. A
#: budget is spent long before this, so the bound only ever caps the cost of
#: asking; it never shortens an answer that mattered.
MAX_AUTONOMY_BUDGET_ROWS: Final[int] = 100

#: The timezone a freeze window is read in when it names none. UTC rather than
#: the host's zone: a window that meant something different on a laptop and in
#: the cluster would be the least debuggable control in the deployment.
DEFAULT_FREEZE_TIMEZONE: Final = "UTC"

# --- Modes -------------------------------------------------------------------

#: The longest a time-bounded override may raise autonomy for, and what it lasts
#: when nobody says. A maintenance session is hours; an override that outlived
#: the session would be a policy change nobody reviewed.
DEFAULT_AUTONOMY_OVERRIDE_SECONDS: Final[float] = 2 * 60 * 60.0
MAX_AUTONOMY_OVERRIDE_SECONDS: Final[float] = 24 * 60 * 60.0

#: How many past decisions a policy-change preview replays. A week of a busy
#: deployment, bounded because a preview nobody can read is one nobody reads.
MAX_AUTONOMY_PREVIEW_ACTIONS: Final[int] = 500

# --- The record --------------------------------------------------------------

#: What each autonomy decision is called in the audit trail. One action name for
#: permitting and refusing alike, because "show me everything the policy engine
#: decided" must not be two queries somebody can get half right.
AUTONOMY_AUDIT_ACTION_DECISION: Final = "autonomy.decision"
AUTONOMY_AUDIT_ACTION_SPEND: Final = "autonomy.budget_spend"
AUTONOMY_AUDIT_ACTION_OVERRIDE_EXPIRED: Final = "autonomy.override_expired"

#: What an autonomy decision names as the thing it acted on.
AUTONOMY_AUDIT_RESOURCE_KIND: Final = "autonomy_decision"
AUTONOMY_AUDIT_RESOURCE_KIND_BUDGET: Final = "autonomy_budget"
AUTONOMY_AUDIT_RESOURCE_KIND_OVERRIDE: Final = "autonomy_override"

#: The keys a decision's audit detail carries. Named, because the explanation is
#: the point of the record and a second spelling of "which rule won" is a query
#: that silently returns half the answer.
AUTONOMY_DETAIL_LEVEL: Final = "level"
AUTONOMY_DETAIL_RISK_CLASS: Final = "risk_class"
AUTONOMY_DETAIL_WINNER: Final = "winning_rule"
AUTONOMY_DETAIL_CONSIDERED: Final = "considered_rules"
AUTONOMY_DETAIL_BOUND: Final = "refused_by"
AUTONOMY_DETAIL_OUTCOME: Final = "decision"
AUTONOMY_DETAIL_DRY_RUN: Final = "dry_run"

#: The five things a decision can be. ``simulate`` is separate from ``execute``
#: because a dry run that recorded itself as an execution would make the record
#: say a change happened that did not — which is the one claim a dry run must
#: never make.
AUTONOMY_DECISION_EXECUTE: Final = "execute"
AUTONOMY_DECISION_SIMULATE: Final = "simulate"
AUTONOMY_DECISION_PROPOSE: Final = "propose"
AUTONOMY_DECISION_APPROVE: Final = "approve"
AUTONOMY_DECISION_REFUSE: Final = "refuse"

AUTONOMY_DECISIONS: Final[tuple[str, ...]] = (
    AUTONOMY_DECISION_EXECUTE,
    AUTONOMY_DECISION_SIMULATE,
    AUTONOMY_DECISION_PROPOSE,
    AUTONOMY_DECISION_APPROVE,
    AUTONOMY_DECISION_REFUSE,
)


__all__ = [
    "AUTONOMY_AUDIT_ACTION_DECISION",
    "AUTONOMY_AUDIT_ACTION_OVERRIDE_EXPIRED",
    "AUTONOMY_AUDIT_ACTION_SPEND",
    "AUTONOMY_AUDIT_RESOURCE_KIND",
    "AUTONOMY_AUDIT_RESOURCE_KIND_BUDGET",
    "AUTONOMY_AUDIT_RESOURCE_KIND_OVERRIDE",
    "AUTONOMY_BOUNDS",
    "AUTONOMY_BOUND_BUDGET",
    "AUTONOMY_BOUND_FREEZE",
    "AUTONOMY_BOUND_KILL_SWITCH",
    "AUTONOMY_BOUND_ROLLBACK",
    "AUTONOMY_BUDGET_SCOPES",
    "AUTONOMY_BUDGET_SCOPE_CAPABILITY",
    "AUTONOMY_BUDGET_SCOPE_RESOURCE",
    "AUTONOMY_BUDGET_SCOPE_TEAM",
    "AUTONOMY_DECISIONS",
    "AUTONOMY_DECISION_APPROVE",
    "AUTONOMY_DECISION_EXECUTE",
    "AUTONOMY_DECISION_PROPOSE",
    "AUTONOMY_DECISION_REFUSE",
    "AUTONOMY_DECISION_SIMULATE",
    "AUTONOMY_DETAIL_BOUND",
    "AUTONOMY_DETAIL_CONSIDERED",
    "AUTONOMY_DETAIL_DRY_RUN",
    "AUTONOMY_DETAIL_LEVEL",
    "AUTONOMY_DETAIL_OUTCOME",
    "AUTONOMY_DETAIL_RISK_CLASS",
    "AUTONOMY_DETAIL_WINNER",
    "AUTONOMY_LEVELS",
    "AUTONOMY_LEVEL_ACT_AND_REPORT",
    "AUTONOMY_LEVEL_ACT_ON_LOW_RISK",
    "AUTONOMY_LEVEL_PROPOSE_ONLY",
    "AUTONOMY_RESOLUTION_BUDGET_SECONDS",
    "AUTONOMY_SCOPE_CAPABILITY",
    "AUTONOMY_SCOPE_CAPABILITY_RESOURCE",
    "AUTONOMY_SCOPE_DEPLOYMENT",
    "AUTONOMY_SCOPE_KINDS",
    "AUTONOMY_SCOPE_LABELS",
    "AUTONOMY_SCOPE_RESOURCE",
    "AUTONOMY_SCOPE_RESOURCE_KIND",
    "AUTONOMY_SCOPE_TEAM",
    "DEFAULT_AUTONOMY_BUDGET",
    "DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS",
    "DEFAULT_AUTONOMY_LEVEL",
    "DEFAULT_AUTONOMY_OVERRIDE_SECONDS",
    "DEFAULT_FREEZE_TIMEZONE",
    "DEFAULT_RISK_BOUND",
    "MAX_AUTONOMY_BUDGET_ROWS",
    "MAX_AUTONOMY_OVERRIDE_SECONDS",
    "MAX_AUTONOMY_PREVIEW_ACTIONS",
    "MAX_AUTONOMY_RULES",
    "RISK_CLASSES",
    "RISK_CLASS_CRITICAL",
    "RISK_CLASS_HIGH",
    "RISK_CLASS_LOW",
    "RISK_CLASS_MODERATE",
    "RISK_CLASS_TRIVIAL",
    "UNCLASSIFIED_RISK_CLASS",
]
