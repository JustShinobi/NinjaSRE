"""The seventh configuration section: ordered rules, and where results are delivered.

Two things this file is for. The rule half is validated at the *document*, not
only in the editor, because the live ingress path loads the same document — a
set checked on the way in is unchecked after a hand-edited import. The
destination half exists to make the silent misconfigurations loud: a destination
subscribed to nothing, and one subscribed to an event nothing publishes.
"""

from __future__ import annotations

import pytest

from config.constants.transit import (
    DELIVERY_DETAIL_FULL_REPORT,
    DELIVERY_DETAIL_SUMMARY_WITH_LINK,
    DELIVERY_EVENT_INVESTIGATION_CONCLUDED,
    DELIVERY_EVENT_SOURCE_DEGRADED,
)
from platform.config_service.errors import ConfigInvalid
from platform.config_service.schema import RootConfig
from platform.config_service.schema.root import ROOT_SECTIONS

pytestmark = pytest.mark.unit


def config(**transit: object) -> RootConfig:
    """Return a root configuration whose transit section is ``transit``."""
    return RootConfig.of({"transit": transit})


# --- The section ------------------------------------------------------------------


def test_transit_is_a_section_of_its_own() -> None:
    """Not a corner of ``policies``: the other six answer what value applies here."""
    assert "transit" in ROOT_SECTIONS


def test_a_deployment_that_configures_nothing_still_investigates_everything() -> None:
    """The default set is today's behaviour, stated as a rule rather than an absence."""
    rules = RootConfig().transit.rule_set()

    assert len(rules.rules) == 1
    assert rules.catch_all.action == "investigate"
    assert rules.catch_all.team_node_id == ""


# --- Rules ----------------------------------------------------------------------


def test_ordered_rules_survive_the_document_in_the_operator_s_order() -> None:
    resolved = config(
        rules=[
            {"rule_id": "noisy", "sources": ["sentry"], "action": "discard", "reason": "chatter"},
            {"rule_id": "rest", "action": "investigate"},
        ]
    )

    assert [rule.rule_id for rule in resolved.transit.rule_set().rules] == ["noisy", "rest"]


def test_a_rule_set_with_no_explicit_last_word_never_reaches_storage() -> None:
    """Acceptance 4, enforced at the document rather than only at the editor."""
    with pytest.raises(ConfigInvalid):
        config(rules=[{"rule_id": "only-sentry", "sources": ["sentry"]}])


def test_a_discarding_rule_with_no_reason_never_reaches_storage() -> None:
    with pytest.raises(ConfigInvalid):
        config(
            rules=[
                {"rule_id": "quiet", "sources": ["sentry"], "action": "discard"},
                {"rule_id": "rest"},
            ]
        )


def test_an_action_nothing_implements_never_reaches_storage() -> None:
    with pytest.raises(ConfigInvalid):
        config(rules=[{"rule_id": "rest", "action": "escalate"}])


# --- Destinations -----------------------------------------------------------------


def test_a_destination_declares_events_a_channel_and_a_detail_level() -> None:
    """Acceptance 5, at the document."""
    resolved = config(
        destinations=[
            {
                "destination_id": "ops-channel",
                "channel": "slack",
                "events": [DELIVERY_EVENT_INVESTIGATION_CONCLUDED],
                "detail": DELIVERY_DETAIL_FULL_REPORT,
            }
        ]
    )

    destination = resolved.transit.destinations[0]
    assert destination.channel == "slack"
    assert list(destination.events) == [DELIVERY_EVENT_INVESTIGATION_CONCLUDED]
    assert destination.detail == DELIVERY_DETAIL_FULL_REPORT


def test_the_safe_detail_level_is_the_one_a_destination_gets_by_default() -> None:
    """A summary behind an authenticated link, not the whole report in a chat body."""
    resolved = config(
        destinations=[
            {
                "destination_id": "ops-channel",
                "channel": "slack",
                "events": [DELIVERY_EVENT_SOURCE_DEGRADED],
            }
        ]
    )

    assert resolved.transit.destinations[0].detail == DELIVERY_DETAIL_SUMMARY_WITH_LINK


def test_a_destination_subscribed_to_nothing_never_reaches_storage() -> None:
    """It looks configured on the screen and is never told anything."""
    with pytest.raises(ConfigInvalid):
        config(destinations=[{"destination_id": "ops", "channel": "slack", "events": []}])


def test_a_destination_subscribed_to_a_typo_never_reaches_storage() -> None:
    with pytest.raises(ConfigInvalid):
        config(
            destinations=[
                {"destination_id": "ops", "channel": "slack", "events": ["investigation_done"]}
            ]
        )


def test_two_destinations_with_one_name_never_reach_storage() -> None:
    with pytest.raises(ConfigInvalid):
        config(
            destinations=[
                {
                    "destination_id": "ops",
                    "channel": "slack",
                    "events": [DELIVERY_EVENT_SOURCE_DEGRADED],
                },
                {
                    "destination_id": "ops",
                    "channel": "teams",
                    "events": [DELIVERY_EVENT_SOURCE_DEGRADED],
                },
            ]
        )


def test_only_the_enabled_destinations_subscribed_to_an_event_are_returned() -> None:
    resolved = config(
        destinations=[
            {
                "destination_id": "chat",
                "channel": "slack",
                "events": [DELIVERY_EVENT_INVESTIGATION_CONCLUDED],
            },
            {
                "destination_id": "paused",
                "channel": "teams",
                "events": [DELIVERY_EVENT_INVESTIGATION_CONCLUDED],
                "enabled": False,
            },
            {
                "destination_id": "degradation",
                "channel": "slack",
                "events": [DELIVERY_EVENT_SOURCE_DEGRADED],
            },
        ]
    )

    told = resolved.transit.destinations_for(DELIVERY_EVENT_INVESTIGATION_CONCLUDED)

    assert [destination.destination_id for destination in told] == ["chat"]
