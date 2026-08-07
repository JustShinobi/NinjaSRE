"""Which team a channel serves, and which alerts are allowed to land there."""

from __future__ import annotations

import pytest

from config.constants.surfaces import CHAT_PLATFORM_DISCORD, CHAT_PLATFORM_SLACK
from core.domain.alerts.normalisation import Severity
from gateway.chat.port import ChatTarget
from gateway.chat.routing import (
    ChannelRouting,
    RoutingTable,
    UnroutedChannel,
    at_or_above,
    routing_of,
)

pytestmark = pytest.mark.unit


def _target(
    channel: str, *, platform: str = CHAT_PLATFORM_SLACK, workspace: str = "W1"
) -> ChatTarget:
    return ChatTarget(platform=platform, channel_id=channel, workspace_id=workspace)


def _row(channel: str, team: str, **overrides: object) -> ChannelRouting:
    return ChannelRouting(
        platform=CHAT_PLATFORM_SLACK,
        channel_id=channel,
        team_id=team,
        workspace_id="W1",
        **overrides,  # type: ignore[arg-type]
    )


# --- One workspace, several teams ---------------------------------------------


def test_a_channel_resolves_to_the_team_it_serves() -> None:
    table = RoutingTable.of([_row("C-pay", "payments"), _row("C-plat", "platform")])

    assert table.team_of(_target("C-pay")) == "payments"
    assert table.team_of(_target("C-plat")) == "platform"


def test_an_unrouted_channel_is_refused_rather_than_defaulted() -> None:
    table = RoutingTable.of([_row("C-pay", "payments")])

    with pytest.raises(UnroutedChannel, match="not routed to a team"):
        table.team_of(_target("C-random"))
    assert table.is_served(_target("C-random")) is False


def test_the_same_channel_id_in_two_workspaces_is_two_channels() -> None:
    table = RoutingTable.of(
        [
            _row("C-pay", "payments"),
            ChannelRouting(
                platform=CHAT_PLATFORM_SLACK,
                channel_id="C-pay",
                team_id="other-payments",
                workspace_id="W2",
            ),
        ]
    )

    assert table.team_of(_target("C-pay", workspace="W1")) == "payments"
    assert table.team_of(_target("C-pay", workspace="W2")) == "other-payments"


def test_the_same_channel_id_on_two_platforms_is_two_channels() -> None:
    table = RoutingTable.of(
        [
            _row("C-pay", "payments"),
            ChannelRouting(
                platform=CHAT_PLATFORM_DISCORD,
                channel_id="C-pay",
                team_id="community",
                workspace_id="W1",
            ),
        ]
    )

    assert table.team_of(_target("C-pay")) == "payments"
    assert table.team_of(_target("C-pay", platform=CHAT_PLATFORM_DISCORD)) == "community"


def test_routing_one_channel_twice_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="routed twice"):
        RoutingTable.of([_row("C-pay", "payments"), _row("C-pay", "platform")])


# --- Per-channel alert settings -------------------------------------------------


def test_a_severity_floor_keeps_quieter_alerts_out() -> None:
    row = _row("C-pay", "payments", minimum_severity=Severity.HIGH)

    assert row.accepts(source="pagerduty", severity=Severity.CRITICAL) is True
    assert row.accepts(source="pagerduty", severity=Severity.HIGH) is True
    assert row.accepts(source="pagerduty", severity=Severity.MEDIUM) is False


def test_an_unclassified_alert_only_clears_the_widest_floor() -> None:
    """``unknown`` is not evidence that something is quiet."""
    strict = _row("C-pay", "payments", minimum_severity=Severity.INFO)
    widest = _row("C-all", "payments", minimum_severity=Severity.UNKNOWN)

    assert strict.accepts(source="generic", severity=Severity.UNKNOWN) is False
    assert widest.accepts(source="generic", severity=Severity.UNKNOWN) is True


def test_a_source_list_restricts_which_alerts_auto_post() -> None:
    row = _row(
        "C-pay",
        "payments",
        alert_sources=frozenset({"sentry"}),
        minimum_severity=Severity.INFO,
    )

    assert row.accepts(source="sentry", severity=Severity.LOW) is True
    assert row.accepts(source="pagerduty", severity=Severity.CRITICAL) is False


def test_an_empty_source_list_means_every_source() -> None:
    row = _row("C-pay", "payments", minimum_severity=Severity.INFO)

    assert row.accepts(source="anything", severity=Severity.LOW) is True


def test_a_channel_with_auto_post_off_is_still_routed_for_mentions() -> None:
    table = RoutingTable.of([_row("C-ask", "payments", auto_post=False)])

    assert table.team_of(_target("C-ask")) == "payments"
    assert table.channels_for_alert(source="pagerduty", severity=Severity.CRITICAL) == ()


def test_an_alert_fans_out_only_to_the_channels_that_take_it() -> None:
    table = RoutingTable.of(
        [
            _row("C-pay", "payments", minimum_severity=Severity.CRITICAL),
            _row("C-plat", "platform", minimum_severity=Severity.LOW),
        ]
    )

    critical = table.channels_for_alert(source="pagerduty", severity=Severity.CRITICAL)
    medium = table.channels_for_alert(source="pagerduty", severity=Severity.MEDIUM)

    assert {target.channel_id for target in critical} == {"C-pay", "C-plat"}
    assert {target.channel_id for target in medium} == {"C-plat"}


def test_fan_out_can_be_narrowed_to_one_team() -> None:
    table = RoutingTable.of(
        [
            _row("C-pay", "payments", minimum_severity=Severity.LOW),
            _row("C-plat", "platform", minimum_severity=Severity.LOW),
        ]
    )

    only = table.channels_for_alert(source="grafana", severity=Severity.HIGH, team_id="payments")

    assert [target.channel_id for target in only] == ["C-pay"]


def test_channels_of_a_team_are_listable() -> None:
    table = RoutingTable.of([_row("C-pay", "payments"), _row("C-pay2", "payments")])

    assert {target.channel_id for target in table.channels_of("payments")} == {"C-pay", "C-pay2"}


# --- Configuration --------------------------------------------------------------


def test_a_configured_table_reads_every_field() -> None:
    table = routing_of(
        [
            {
                "platform": CHAT_PLATFORM_SLACK,
                "channel_id": "C-pay",
                "team_id": "payments",
                "workspace_id": "W1",
                "alert_sources": ["sentry", "grafana"],
                "minimum_severity": "medium",
                "auto_post": False,
            }
        ]
    )

    row = table.find(_target("C-pay"))
    assert row is not None
    assert row.alert_sources == frozenset({"sentry", "grafana"})
    assert row.minimum_severity is Severity.MEDIUM
    assert row.auto_post is False


def test_a_configured_row_defaults_to_posting_high_and_above_from_anywhere() -> None:
    table = routing_of(
        [{"platform": CHAT_PLATFORM_SLACK, "channel_id": "C-pay", "team_id": "payments"}]
    )

    row = table.find(ChatTarget(platform=CHAT_PLATFORM_SLACK, channel_id="C-pay"))
    assert row is not None
    assert row.minimum_severity is Severity.HIGH
    assert row.alert_sources == frozenset()
    assert row.auto_post is True


def test_severity_ordering_is_total_and_correctly_directed() -> None:
    assert at_or_above(Severity.CRITICAL, Severity.LOW) is True
    assert at_or_above(Severity.LOW, Severity.CRITICAL) is False
    assert at_or_above(Severity.HIGH, Severity.HIGH) is True
