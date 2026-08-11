"""What happens to what arrives, and who is told about what leaves.

The seventh section, and it is its own rather than a corner of ``policies`` for
the reason 062 exists at all: the other six answer *what value applies here*,
and this one answers *where did this come from and where did it go*. Mixing a
routing rule in with a threshold is how an operator ends up opening five screens
to find out why an alert never became an investigation.

Two lists, and the asymmetry between them is deliberate.

**Rules are ordered and the order is the operator's.** First match wins, and the
last rule is a catch-all whose action is explicit — validated here, not just in
the editor, because the live path loads this document too and a set that was
only checked on the way in is unchecked after a hand-edited import.

**Destinations are a set, and every one of them is told.** There is no order to
get wrong: an event goes to every destination subscribed to it. What a
destination chooses is *how much* — and the safe level is the default, so a
destination somebody added without thinking about it sends a summary and a link
rather than the whole report into a channel.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from config.constants.transit import (
    DEFAULT_CATCH_ALL_RULE_ID,
    DELIVERY_DETAIL_LEVELS,
    DELIVERY_DETAIL_SUMMARY_WITH_LINK,
    DELIVERY_EVENTS,
    MAX_DESTINATIONS,
    MAX_ROUTING_RULES,
    RULE_ACTION_DISCARD,
    RULE_ACTION_INVESTIGATE,
    RULE_ACTIONS,
)
from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredStr,
    ConfiguredStrList,
)
from platform.ingress.rules import RoutingRule, RuleSet, RuleSetInvalid, default_rule_set


class RoutingRuleSettings(ConfigSection):
    """One ordered rule: what it matches, where it sends, and what it does."""

    rule_id: ConfiguredStr
    #: Empty means "no filter on this dimension" rather than "match nothing",
    #: which is what makes a rule with no matchers the catch-all.
    sources: ConfiguredStrList = ()
    zones: ConfiguredStrList = ()
    criticalities: ConfiguredStrList = ()
    resources: ConfiguredStrList = ()
    #: Where matched deliveries go. Empty keeps the team the verifier
    #: established, which is what today's behaviour is.
    team: ConfiguredStr = ""
    action: Literal["investigate", "record_only", "discard"] = RULE_ACTION_INVESTIGATE
    #: Required for a discard, refused as noise on anything else — a reason
    #: attached to an action that has none is a sentence nobody will ever read.
    reason: ConfiguredStr = ""

    @field_validator("action")
    @classmethod
    def _known_action(cls, value: str) -> str:
        """Refuse an action no evaluator implements."""
        if value not in RULE_ACTIONS:
            raise ValueError(f"must be one of {', '.join(RULE_ACTIONS)}; found {value!r}")
        return value

    @model_validator(mode="after")
    def _discard_says_why(self) -> RoutingRuleSettings:
        """Refuse a discard with no reason.

        A silent discard is how an alert disappears without anybody knowing it
        disappeared, which is the failure this whole section exists to end.
        """
        if self.action == RULE_ACTION_DISCARD and not self.reason.strip():
            raise ValueError(
                "a discarding rule needs a reason; a silent discard is how an alert "
                "disappears without anybody knowing it disappeared"
            )
        return self

    def as_rule(self) -> RoutingRule:
        """Return the evaluator's own record for this row.

        The schema and the evaluator are two shapes of one fact, and this is the
        single place they meet — so a rule the console saved and a rule the
        ingress path runs cannot be built from different readings of the same
        document.
        """
        return RoutingRule(
            rule_id=self.rule_id,
            sources=tuple(self.sources),
            zones=tuple(self.zones),
            criticalities=tuple(self.criticalities),
            resource_ids=tuple(self.resources),
            team_node_id=self.team,
            action=self.action,
            reason=self.reason,
        )


class DeliveryDestinationSettings(ConfigSection):
    """One place results go: which events, over which channel, in how much detail."""

    destination_id: ConfiguredStr
    #: The catalogue integration that carries the message. Named rather than a
    #: URL, because a URL here would be a second place a credential could appear.
    channel: ConfiguredStr
    #: A closed set. A destination subscribed to a typo is one that is silently
    #: never notified, which is the same failure as a source that never delivers.
    events: ConfiguredStrList = ()
    detail: Literal["summary_with_link", "full_report"] = DELIVERY_DETAIL_SUMMARY_WITH_LINK
    enabled: bool = True

    @field_validator("events")
    @classmethod
    def _known_events(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Refuse an event nothing ever publishes."""
        unknown = [event for event in value if event not in DELIVERY_EVENTS]
        if unknown:
            raise ValueError(
                f"must each be one of {', '.join(DELIVERY_EVENTS)}; found "
                f"{', '.join(repr(event) for event in unknown)}"
            )
        return value

    @field_validator("detail")
    @classmethod
    def _known_detail(cls, value: str) -> str:
        """Refuse a detail level no formatter produces."""
        if value not in DELIVERY_DETAIL_LEVELS:
            raise ValueError(f"must be one of {', '.join(DELIVERY_DETAIL_LEVELS)}; found {value!r}")
        return value

    @model_validator(mode="after")
    def _subscribes_to_something(self) -> DeliveryDestinationSettings:
        """Refuse a destination that would never be told anything.

        An enabled destination with no events looks configured on the screen and
        delivers nothing, which is the most expensive shape of misconfiguration
        this feature knows about — it is silent.
        """
        if self.enabled and not self.events:
            raise ValueError(
                "an enabled destination subscribes to at least one event; one with none "
                "looks configured and is never told anything"
            )
        return self


class TransitConfig(ConfigSection):
    """The ordered rules, and the destinations results are delivered to."""

    rules: list[RoutingRuleSettings] = Field(default_factory=list)
    destinations: list[DeliveryDestinationSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def _bounded_and_terminated(self) -> TransitConfig:
        """Refuse a set that is unbounded, ambiguous, or has no declared fallback.

        The catch-all check is here rather than only in the editor because the
        resolution path reads this document too. An empty list is allowed and
        means "no rules configured", which resolves to the default set — today's
        behaviour, stated as a rule rather than as an absence of them.
        """
        if len(self.rules) > MAX_ROUTING_RULES:
            raise ValueError(
                f"at most {MAX_ROUTING_RULES} rules; evaluation is a linear scan on the "
                f"ingress path"
            )
        if len(self.destinations) > MAX_DESTINATIONS:
            raise ValueError(
                f"at most {MAX_DESTINATIONS} destinations; every one is told about every "
                f"event it subscribes to"
            )
        seen: set[str] = set()
        for destination in self.destinations:
            if destination.destination_id in seen:
                raise ValueError(
                    f"destination {destination.destination_id!r} appears twice; two rows "
                    f"with one name makes 'where did this go' a question with two answers"
                )
            seen.add(destination.destination_id)

        if self.rules:
            try:
                RuleSet.of(rule.as_rule() for rule in self.rules)
            except RuleSetInvalid as invalid:
                raise ValueError(str(invalid)) from invalid
        return self

    def rule_set(self) -> RuleSet:
        """Return the evaluator's rule set, or the default when none is configured.

        The default is one catch-all that investigates, keeping the verifier's
        team — which reproduces this build's behaviour before rules existed. A
        deployment that configures nothing therefore behaves exactly as it did,
        and the characterisation test that proves so runs against this path.
        """
        if not self.rules:
            return default_rule_set()
        return RuleSet.of(rule.as_rule() for rule in self.rules)

    def destinations_for(self, event: str) -> tuple[DeliveryDestinationSettings, ...]:
        """Return every enabled destination subscribed to ``event``."""
        return tuple(
            destination
            for destination in self.destinations
            if destination.enabled and event in destination.events
        )


#: The identifier the catch-all carries when nothing is configured. Re-exported
#: so the console can label the row it always renders without importing the
#: evaluator.
CATCH_ALL_RULE_ID = DEFAULT_CATCH_ALL_RULE_ID


__all__ = [
    "CATCH_ALL_RULE_ID",
    "DeliveryDestinationSettings",
    "RoutingRuleSettings",
    "TransitConfig",
]
