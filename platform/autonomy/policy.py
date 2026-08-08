"""What an operator configures, and the document it is reviewable as.

A policy set is rules, freeze windows, budgets and overrides — nothing else, and
in particular no expressions. It is built from the hierarchical configuration
service, so merge, locked fields, required fields, approval gating and
provenance are inherited rather than rebuilt; a second configuration mechanism
for the most safety-critical setting in the system would be the wrong place to
save effort.

**Malformed fails at save time, with a name and a path.** ``of_document`` is what
a write goes through, and every refusal it raises names the field. The
alternative is a policy that validates when it is written and raises when it is
read, which is to say during an incident, about an action that has nothing to do
with the mistake.

**Export and import are the same shape.** ``to_document`` produces exactly what
``of_document`` accepts, so a deployment's posture is a file somebody can read
in a review, and the round trip is a test rather than a hope.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from typing import Any

from config.constants.autonomy import (
    AUTONOMY_BUDGET_SCOPE_RESOURCE,
    DEFAULT_AUTONOMY_BUDGET,
    DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS,
    DEFAULT_AUTONOMY_OVERRIDE_SECONDS,
    DEFAULT_FREEZE_TIMEZONE,
    DEFAULT_RISK_BOUND,
    MAX_AUTONOMY_OVERRIDE_SECONDS,
    MAX_AUTONOMY_RULES,
)
from platform.autonomy.bounds import BudgetRule, FreezeWindow
from platform.autonomy.errors import MalformedPolicy
from platform.autonomy.levels import AutonomyLevel, level_of
from platform.autonomy.risk import RiskClass, risk_class_of
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.autonomy.subjects import ProposedAction, Subject


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """One statement: in this scope, this much autonomy, up to this much risk.

    ``risk_bound`` is read only at ``act_on_low_risk``. It is carried at every
    level anyway rather than being a second optional type, because a rule that
    changes shape with its level is a rule an operator edits into a different
    shape by changing one word.
    """

    scope: PolicyScope
    level: AutonomyLevel
    risk_bound: RiskClass = RiskClass(DEFAULT_RISK_BOUND)
    dry_run: bool = False
    #: Which configuration node this arrived from, for the explanation. Not part
    #: of the identity: the same scope set at two nodes is the same rule seen
    #: twice, and the merge has already decided which one survived.
    source: str = ""

    @property
    def rule_id(self) -> str:
        """Return the stable name this rule is referred to by."""
        return self.scope.identity

    @property
    def specificity(self) -> int:
        """Return how specific this rule's scope is."""
        return self.scope.specificity

    def applies_to(self, action: ProposedAction, subject: Subject) -> bool:
        """Return whether this rule covers ``subject`` under ``action``."""
        return self.scope.matches(action, subject)

    def describe(self) -> str:
        """Return the sentence an explanation reads with."""
        bound = (
            f" up to {self.risk_bound.value} risk"
            if self.level is AutonomyLevel.ACT_ON_LOW_RISK
            else ""
        )
        simulated = ", simulated only" if self.dry_run else ""
        return f"{self.scope.describe()}: {self.level.value}{bound}{simulated}"

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, which is also the exported document's form."""
        record: dict[str, Any] = {
            "scope": self.scope.to_record(),
            "level": self.level.value,
            "risk_bound": self.risk_bound.value,
        }
        if self.dry_run:
            record["dry_run"] = True
        return record


@dataclass(frozen=True, slots=True)
class TimedOverride:
    """A raise in autonomy that ends by itself.

    Expiry is a comparison against the resolution's own clock rather than a
    scheduled job, so an override cannot outlive its window because a worker was
    down. What the job is for is *announcing* the expiry; what stops the
    override taking effect is that it is simply no longer applicable.
    """

    name: str
    scope: PolicyScope
    level: AutonomyLevel
    expires_at: datetime
    risk_bound: RiskClass = RiskClass(DEFAULT_RISK_BOUND)
    granted_by: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("An override needs a name; its expiry has to name what expired.")
        if self.expires_at.tzinfo is None:
            raise ValueError(
                f"{self.name}: an override expires at an instant, not a wall-clock time; "
                f"give expires_at a timezone"
            )

    def active_at(self, at: datetime) -> bool:
        """Return whether this override still applies at ``at``."""
        return at < self.expires_at

    def as_rule(self) -> PolicyRule:
        """Return the rule this override behaves as while it is active.

        An override is an ordinary rule with an end date, deliberately. Giving
        it a resolution path of its own would mean the most permissive thing an
        operator can do is also the one path the decision matrix does not cover.
        """
        return replace(
            PolicyRule(scope=self.scope, level=self.level, risk_bound=self.risk_bound),
            source=f"override {self.name}",
        )

    def describe(self) -> str:
        """Return the sentence an operator reads about this override."""
        why = f" — {self.reason}" if self.reason else ""
        return (
            f"the override {self.name!r} raises {self.scope.describe()} to "
            f"{self.level.value} until {self.expires_at.isoformat()}{why}"
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, which is also the exported document's form."""
        return {
            "name": self.name,
            "scope": self.scope.to_record(),
            "level": self.level.value,
            "risk_bound": self.risk_bound.value,
            "expires_at": self.expires_at.isoformat(),
            "granted_by": self.granted_by,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PolicySet:
    """Everything one resolution reads, as one value.

    Frozen and complete. Resolution is a pure function of an action, one of
    these, and a clock — which is what makes the decision matrix exhaustive
    rather than sampled, and what makes a policy change previewable against
    history without a deployment to run it in.
    """

    rules: tuple[PolicyRule, ...] = ()
    freezes: tuple[FreezeWindow, ...] = ()
    budgets: tuple[BudgetRule, ...] = ()
    overrides: tuple[TimedOverride, ...] = ()
    #: Simulate everything, whatever any rule says. The deployment-wide half of
    #: the dry-run mode; the per-scope half is ``PolicyRule.dry_run``.
    dry_run: bool = False

    def __post_init__(self) -> None:
        if len(self.rules) > MAX_AUTONOMY_RULES:
            raise MalformedPolicy(
                "rules",
                f"a deployment may configure {MAX_AUTONOMY_RULES} rules; found "
                f"{len(self.rules)}. Resolution runs on every action, and a policy set "
                f"nobody can read is not one anybody reviewed.",
            )

    def active_rules(self, at: datetime) -> tuple[PolicyRule, ...]:
        """Return the configured rules plus every override still in force."""
        live = tuple(override.as_rule() for override in self.overrides if override.active_at(at))
        return self.rules + live

    def expired(self, at: datetime) -> tuple[TimedOverride, ...]:
        """Return the overrides that have run out by ``at``, for the record."""
        return tuple(override for override in self.overrides if not override.active_at(at))

    def with_rules(self, rules: Iterable[PolicyRule]) -> PolicySet:
        """Return this set with ``rules`` in place of its own. What a preview varies."""
        return replace(self, rules=tuple(rules))

    def to_document(self) -> dict[str, Any]:
        """Return the reviewable document this posture is, ready to write out."""
        return {
            "dry_run": self.dry_run,
            "rules": [rule.to_record() for rule in self.rules],
            "freezes": [window.to_record() for window in self.freezes],
            "budgets": [budget.to_record() for budget in self.budgets],
            "overrides": [override.to_record() for override in self.overrides],
        }

    @classmethod
    def of_document(cls, document: Mapping[str, Any]) -> PolicySet:
        """Return the policy set ``document`` describes, or raise naming the field.

        Raises:
            MalformedPolicy: any field the engine cannot act on, named by path.
        """
        return cls(
            dry_run=_bool(document.get("dry_run", False), "dry_run"),
            rules=tuple(
                _rule(entry, f"rules[{index}]")
                for index, entry in enumerate(_sequence(document.get("rules"), "rules"))
            ),
            freezes=tuple(
                _freeze(entry, f"freezes[{index}]")
                for index, entry in enumerate(_sequence(document.get("freezes"), "freezes"))
            ),
            budgets=tuple(
                _budget(entry, f"budgets[{index}]")
                for index, entry in enumerate(_sequence(document.get("budgets"), "budgets"))
            ),
            overrides=tuple(
                _override(entry, f"overrides[{index}]")
                for index, entry in enumerate(_sequence(document.get("overrides"), "overrides"))
            ),
        )


def policy_set_of_document(document: Mapping[str, Any]) -> PolicySet:
    """Return the policy set ``document`` describes. The function form."""
    return PolicySet.of_document(document)


def override_expiring(
    *,
    name: str,
    scope: PolicyScope,
    level: AutonomyLevel,
    granted_at: datetime,
    seconds: float = DEFAULT_AUTONOMY_OVERRIDE_SECONDS,
    granted_by: str = "",
    reason: str = "",
    risk_bound: RiskClass = RiskClass(DEFAULT_RISK_BOUND),
) -> TimedOverride:
    """Return an override lasting ``seconds``, bounded by the configured ceiling.

    Raises:
        MalformedPolicy: ``seconds`` is past the ceiling, or is not positive.
    """
    if seconds <= 0:
        raise MalformedPolicy(f"overrides.{name}", "an override lasting no time is not one")
    if seconds > MAX_AUTONOMY_OVERRIDE_SECONDS:
        raise MalformedPolicy(
            f"overrides.{name}",
            f"an override may last {MAX_AUTONOMY_OVERRIDE_SECONDS / 3600:g} hours at most; "
            f"a longer raise is a policy change and goes through a review",
        )
    return TimedOverride(
        name=name,
        scope=scope,
        level=level,
        expires_at=granted_at + timedelta(seconds=seconds),
        risk_bound=risk_bound,
        granted_by=granted_by,
        reason=reason,
    )


# --- document parsing --------------------------------------------------------
#
# One helper per shape, each raising ``MalformedPolicy`` with the path it was
# reading. Written out rather than driven by a schema library because the whole
# of the requirement is that the error names the field, and a generic validator
# reports a type mismatch three levels into a structure an operator did not
# write in that shape.


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise MalformedPolicy(path, f"must be a list; found {type(value).__name__}")
    return value


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MalformedPolicy(path, f"must be an object; found {type(value).__name__}")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise MalformedPolicy(path, f"must be true or false; found {value!r}")
    return value


def _text(value: Any, path: str, *, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise MalformedPolicy(path, f"must be text; found {type(value).__name__}")
    if required and not value.strip():
        raise MalformedPolicy(path, "must not be empty")
    return value.strip()


def _integer(value: Any, path: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedPolicy(path, f"must be a whole number; found {value!r}")
    return value


def _number(value: Any, path: str, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MalformedPolicy(path, f"must be a number of seconds; found {value!r}")
    return float(value)


def _scope(value: Any, path: str) -> PolicyScope:
    record = _mapping(value, path)
    kind = _text(record.get("kind"), f"{path}.kind")
    try:
        scope_kind = ScopeKind(kind)
    except ValueError as unknown:
        raise MalformedPolicy(
            f"{path}.kind",
            f"{kind!r} is not a scope kind; expected one of "
            f"{', '.join(member.value for member in ScopeKind)}",
        ) from unknown

    labels_value = record.get("labels") or {}
    labels = _mapping(labels_value, f"{path}.labels")
    for name, label in labels.items():
        if not isinstance(label, str):
            raise MalformedPolicy(f"{path}.labels.{name}", "must be text")

    try:
        return PolicyScope(
            kind=scope_kind,
            team_node_id=_text(record.get("team_node_id"), f"{path}.team_node_id", required=False),
            resource_kind=_text(
                record.get("resource_kind"), f"{path}.resource_kind", required=False
            ),
            resource_id=_text(record.get("resource_id"), f"{path}.resource_id", required=False),
            capability=_text(record.get("capability"), f"{path}.capability", required=False),
            labels={name: str(label) for name, label in labels.items()},
        )
    except MalformedPolicy:
        # Already named the exact field. Re-wrapping it here would replace
        # ``freezes[0].start`` with ``freezes[0]``, which is the whole of what
        # the operator needed.
        raise
    except ValueError as rejected:
        raise MalformedPolicy(path, str(rejected)) from rejected


def _level(value: Any, path: str) -> AutonomyLevel:
    try:
        return level_of(_text(value, path))
    except MalformedPolicy:
        # Already named the exact field. Re-wrapping it here would replace
        # ``freezes[0].start`` with ``freezes[0]``, which is the whole of what
        # the operator needed.
        raise
    except ValueError as rejected:
        raise MalformedPolicy(path, str(rejected)) from rejected


def _risk(value: Any, path: str) -> RiskClass:
    if value is None or (isinstance(value, str) and not value.strip()):
        return RiskClass(DEFAULT_RISK_BOUND)
    try:
        return risk_class_of(_text(value, path))
    except MalformedPolicy:
        # Already named the exact field. Re-wrapping it here would replace
        # ``freezes[0].start`` with ``freezes[0]``, which is the whole of what
        # the operator needed.
        raise
    except ValueError as rejected:
        raise MalformedPolicy(path, str(rejected)) from rejected


def _rule(value: Any, path: str) -> PolicyRule:
    record = _mapping(value, path)
    return PolicyRule(
        scope=_scope(record.get("scope"), f"{path}.scope"),
        level=_level(record.get("level"), f"{path}.level"),
        risk_bound=_risk(record.get("risk_bound"), f"{path}.risk_bound"),
        dry_run=_bool(record.get("dry_run", False), f"{path}.dry_run"),
    )


def _time(value: Any, path: str) -> time:
    text = _text(value, path)
    try:
        return time.fromisoformat(text)
    except ValueError as rejected:
        raise MalformedPolicy(path, f"{text!r} is not a time of day like '01:00'") from rejected


def _freeze(value: Any, path: str) -> FreezeWindow:
    record = _mapping(value, path)
    try:
        return FreezeWindow(
            name=_text(record.get("name"), f"{path}.name"),
            scope=_scope(record.get("scope"), f"{path}.scope"),
            start=_time(record.get("start"), f"{path}.start"),
            end=_time(record.get("end"), f"{path}.end"),
            timezone=_text(record.get("timezone"), f"{path}.timezone", required=False)
            or DEFAULT_FREEZE_TIMEZONE,
            reason=_text(record.get("reason"), f"{path}.reason", required=False),
        )
    except MalformedPolicy:
        # Already named the exact field. Re-wrapping it here would replace
        # ``freezes[0].start`` with ``freezes[0]``, which is the whole of what
        # the operator needed.
        raise
    except ValueError as rejected:
        raise MalformedPolicy(path, str(rejected)) from rejected


def _budget(value: Any, path: str) -> BudgetRule:
    record = _mapping(value, path)
    scope = record.get("scope")
    try:
        return BudgetRule(
            name=_text(record.get("name"), f"{path}.name"),
            counted_by=_text(record.get("counted_by"), f"{path}.counted_by", required=False)
            or AUTONOMY_BUDGET_SCOPE_RESOURCE,
            limit=_integer(record.get("limit"), f"{path}.limit", DEFAULT_AUTONOMY_BUDGET),
            interval_seconds=_number(
                record.get("interval_seconds"),
                f"{path}.interval_seconds",
                DEFAULT_AUTONOMY_BUDGET_INTERVAL_SECONDS,
            ),
            scope=_scope(scope, f"{path}.scope") if scope is not None else None,
        )
    except MalformedPolicy:
        # Already named the exact field. Re-wrapping it here would replace
        # ``freezes[0].start`` with ``freezes[0]``, which is the whole of what
        # the operator needed.
        raise
    except ValueError as rejected:
        raise MalformedPolicy(path, str(rejected)) from rejected


def _instant(value: Any, path: str) -> datetime:
    text = _text(value, path)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as rejected:
        raise MalformedPolicy(path, f"{text!r} is not an instant in ISO 8601") from rejected
    if parsed.tzinfo is None:
        raise MalformedPolicy(path, f"{text!r} names no timezone, so it names no instant")
    return parsed


def _override(value: Any, path: str) -> TimedOverride:
    record = _mapping(value, path)
    try:
        return TimedOverride(
            name=_text(record.get("name"), f"{path}.name"),
            scope=_scope(record.get("scope"), f"{path}.scope"),
            level=_level(record.get("level"), f"{path}.level"),
            expires_at=_instant(record.get("expires_at"), f"{path}.expires_at"),
            risk_bound=_risk(record.get("risk_bound"), f"{path}.risk_bound"),
            granted_by=_text(record.get("granted_by"), f"{path}.granted_by", required=False),
            reason=_text(record.get("reason"), f"{path}.reason", required=False),
        )
    except MalformedPolicy:
        # Already named the exact field. Re-wrapping it here would replace
        # ``freezes[0].start`` with ``freezes[0]``, which is the whole of what
        # the operator needed.
        raise
    except ValueError as rejected:
        raise MalformedPolicy(path, str(rejected)) from rejected


#: An empty posture. Resolves to ``propose_only`` for everything, which is the
#: point: a deployment that has configured nothing acts on nothing.
NOTHING_CONFIGURED: PolicySet = PolicySet()


__all__ = [
    "NOTHING_CONFIGURED",
    "PolicyRule",
    "PolicyScope",
    "PolicySet",
    "ScopeKind",
    "TimedOverride",
    "override_expiring",
    "policy_set_of_document",
]
