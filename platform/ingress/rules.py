"""Ordered rules, evaluated in one place, deciding what happens to a verified delivery.

Verification answers *who is this*; these rules answer *what do we do about it*.
Splitting the two is what this module is for: today a verifier decides the team
and the team decides everything, so an operator who wants critical alerts from
one zone to go somewhere else has nowhere to say so.

Three properties, and each of them is a bug this shape prevents.

**Ordered, first match wins.** A set where two rules could both apply and the
winner depended on iteration order is a set whose behaviour nobody can predict
from reading it. So the order is the operator's, it is preserved, and the first
rule whose matchers all agree is the one that decides.

**The last rule is a catch-all, and validation refuses a set without one.** The
fate of a delivery nothing matched is an explicit choice or the set does not
save. A set that ended in a specific rule would leave "what happens to
everything else" as an implicit default, and an implicit default for *discard*
is how an alert disappears with nobody knowing it disappeared.

**Discard carries a reason.** Always, checked at construction. The row in the
ledger says why, so "it never arrived" and "it arrived and we chose not to act"
are different sentences on the screen instead of the same silence.

Matchers are vocabulary rather than free text. A zone or a criticality is a
value the estate and the normalised alert already produce, and
``check_vocabulary`` is what refuses a rule matching on a zone the estate has
never heard of — a rule that can never fire is worse than a missing one,
because the operator believes it is in force.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from config.constants.transit import (
    DEFAULT_CATCH_ALL_RULE_ID,
    MAX_ROUTING_RULES,
    RULE_ACTION_DISCARD,
    RULE_ACTION_INVESTIGATE,
    RULE_ACTIONS,
)


class RuleSetInvalid(ValueError):
    """A rule set that would behave in a way nobody could predict from reading it.

    Named rather than a bare ``ValueError`` so the configuration section, the
    editor and the simulate endpoint can all report the same failure as the same
    kind of thing.
    """


@dataclass(frozen=True, slots=True)
class Signals:
    """One delivery, reduced to the dimensions a rule may speak about.

    Built by the caller from what it already resolved — the source path, the
    normalised alert's severity, and the estate resource the labels resolved to
    — so the matcher is a pure function of a value and never reaches for a
    repository. That is what lets the live path and the simulation run the same
    code with the same result.
    """

    source: str = ""
    zone: str = ""
    criticality: str = ""
    resource_id: str = ""
    #: The team the verifier established. A rule may redirect, and a rule that
    #: names no team leaves this one in place.
    team_node_id: str = ""


@dataclass(frozen=True, slots=True)
class RoutingRule:
    """One row: what it matches, where it sends, and what it does.

    Empty matcher tuples mean "no filter on this dimension" rather than "match
    nothing", for the reason ``EstateQuery`` gives — it is the only reading that
    composes when an editor builds a rule out of optional inputs, and it is what
    makes a rule with no matchers at all the catch-all.
    """

    rule_id: str
    sources: tuple[str, ...] = ()
    zones: tuple[str, ...] = ()
    criticalities: tuple[str, ...] = ()
    resource_ids: tuple[str, ...] = ()
    #: Where matched deliveries go. Empty keeps the team the verifier established,
    #: which is what the default set does and therefore what today's behaviour is.
    team_node_id: str = ""
    action: str = RULE_ACTION_INVESTIGATE
    #: Why, for a discard. Shown on the ledger row and on the screen.
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise RuleSetInvalid(
                "A routing rule needs an identifier; a rule nobody can name "
                "cannot be reported as the one that caught a delivery."
            )
        if self.action not in RULE_ACTIONS:
            raise RuleSetInvalid(
                f"rule {self.rule_id!r} declares action {self.action!r}; expected one of "
                f"{', '.join(RULE_ACTIONS)}"
            )
        if self.action == RULE_ACTION_DISCARD and not self.reason:
            raise RuleSetInvalid(
                f"rule {self.rule_id!r} discards without a reason. A silent discard is how "
                f"an alert disappears without anybody knowing it disappeared."
            )

    @property
    def is_catch_all(self) -> bool:
        """Return whether this rule matches every delivery.

        A rule with no matchers, which is the only shape that cannot be made not
        to fire. Validation requires the last rule to be one of these.
        """
        return not (self.sources or self.zones or self.criticalities or self.resource_ids)

    def matches(self, signals: Signals) -> bool:
        """Return whether every matcher this rule declares agrees with ``signals``."""
        if self.sources and signals.source not in self.sources:
            return False
        if self.zones and signals.zone not in self.zones:
            return False
        if self.criticalities and signals.criticality not in self.criticalities:
            return False
        return not (self.resource_ids and signals.resource_id not in self.resource_ids)


@dataclass(frozen=True, slots=True)
class RuleSet:
    """Every rule, in the operator's order, with the catch-all last."""

    rules: tuple[RoutingRule, ...] = field(default=())

    @classmethod
    def of(cls, rules: Iterable[RoutingRule]) -> RuleSet:
        """Return a validated set, or raise ``RuleSetInvalid``.

        Validation is here rather than beside the editor because the live path
        loads a set too, and a set that was only checked on the way in is a set
        that is unchecked after a hand-edited import.
        """
        collected = tuple(rules)
        if not collected:
            raise RuleSetInvalid(
                "A rule set with no rules decides nothing. The fate of an unmatched "
                "delivery is an explicit choice, so a set holds at least a catch-all."
            )
        if len(collected) > MAX_ROUTING_RULES:
            raise RuleSetInvalid(
                f"{len(collected)} rules exceeds the {MAX_ROUTING_RULES}-rule bound; "
                f"evaluation is a linear scan on the ingress path."
            )

        seen: set[str] = set()
        for rule in collected:
            if rule.rule_id in seen:
                raise RuleSetInvalid(
                    f"rule {rule.rule_id!r} appears twice. Two rows with one name makes "
                    f"'which rule caught this' a question with two answers."
                )
            seen.add(rule.rule_id)

        for rule in collected[:-1]:
            if rule.is_catch_all:
                raise RuleSetInvalid(
                    f"rule {rule.rule_id!r} matches everything but is not last, so no rule "
                    f"after it can ever fire."
                )
        if not collected[-1].is_catch_all:
            raise RuleSetInvalid(
                f"the last rule {collected[-1].rule_id!r} declares matchers, so a delivery "
                f"matching none of these rules has no declared fate. End the set with a "
                f"catch-all whose action is explicit."
            )
        return cls(rules=collected)

    @property
    def catch_all(self) -> RoutingRule:
        """Return the rule that decides everything nothing else matched.

        Always present — ``of`` refuses a set without one — so this is a
        property rather than an optional lookup, and the editor can render it
        without asking whether there is one to render.
        """
        return self.rules[-1]

    def check_vocabulary(
        self,
        *,
        sources: Sequence[str],
        zones: Sequence[str],
        criticalities: Sequence[str],
    ) -> None:
        """Raise when a rule matches on a value nothing can ever produce.

        Zones and criticalities come from the estate and the normalised alert,
        never from text somebody typed. A rule naming a zone this deployment has
        no resources in can never fire, and an operator who believes it is in
        force is worse off than one who was told it is not.

        An empty vocabulary checks nothing on that dimension: a deployment whose
        estate has not been swept yet has no zones to check against, and
        refusing every zone matcher until the first sweep would be refusing to
        configure the deployment before it has been configured.
        """
        for rule in self.rules:
            _check_dimension(rule.rule_id, "source", rule.sources, sources)
            _check_dimension(rule.rule_id, "zone", rule.zones, zones)
            _check_dimension(rule.rule_id, "criticality", rule.criticalities, criticalities)


def _check_dimension(
    rule_id: str, dimension: str, declared: Sequence[str], known: Sequence[str]
) -> None:
    """Raise when ``declared`` names something outside a non-empty ``known``."""
    if not known:
        return
    unknown = [value for value in declared if value not in known]
    if unknown:
        raise RuleSetInvalid(
            f"rule {rule_id!r} matches on {dimension} {', '.join(repr(v) for v in unknown)}, "
            f"which this deployment cannot produce. A rule that can never fire is worse "
            f"than a missing one, because the operator believes it is in force."
        )


@dataclass(frozen=True, slots=True)
class RuleMatch:
    """Which rule caught a delivery, where it goes, and what happens to it."""

    rule: RoutingRule
    team_node_id: str

    @property
    def action(self) -> str:
        """Return what the matched rule does with this delivery."""
        return self.rule.action

    @property
    def reason(self) -> str:
        """Return why, for a discard, and the empty string otherwise."""
        return self.rule.reason


def evaluate(rule_set: RuleSet, signals: Signals) -> RuleMatch:
    """Return the first rule that matches ``signals``, and the team it sends to.

    Total, because the set's last rule is a catch-all and ``RuleSet.of`` refuses
    a set where it is not — so there is no "nothing matched" branch here for a
    caller to get wrong, and no implicit default hiding in one.

    This is the *only* implementation. The live ingress path and the simulate
    endpoint both call it, which is what makes a simulation a statement about
    what will happen rather than about what a second copy of the logic thinks
    will happen.
    """
    for rule in rule_set.rules:
        if rule.matches(signals):
            return RuleMatch(rule=rule, team_node_id=rule.team_node_id or signals.team_node_id)
    # Unreachable while ``RuleSet.of`` is the only constructor: the last rule
    # matches everything. Stated rather than assumed, because the day somebody
    # builds a ``RuleSet`` directly this is a named failure instead of an
    # IndexError three frames away.
    raise RuleSetInvalid(
        "no rule matched and the set has no catch-all; it was not built through RuleSet.of"
    )


def default_rule_set() -> RuleSet:
    """Return the set that reproduces today's behaviour exactly.

    One catch-all, investigating, keeping the team the verifier established.
    That is what every verified delivery does today, and shipping it as a *rule*
    rather than as an absence of rules is what makes the seam movable: the
    characterisation test passes before the rules exist and after they do,
    against the same assertions.
    """
    return RuleSet.of(
        (RoutingRule(rule_id=DEFAULT_CATCH_ALL_RULE_ID, action=RULE_ACTION_INVESTIGATE),)
    )


__all__ = [
    "RoutingRule",
    "RuleMatch",
    "RuleSet",
    "RuleSetInvalid",
    "Signals",
    "default_rule_set",
    "evaluate",
]
