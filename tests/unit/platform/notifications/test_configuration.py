"""Reading one team's destinations, sinks, and notification policy out of configuration."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from config.constants.notifications import (
    MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW,
    NOTIFICATION_COOLDOWN_SECONDS,
)
from platform.config_service.schema.surfaces import SurfacesConfig
from platform.notifications.configuration import destinations_of, policy_of, sinks_of
from platform.notifications.models import SinkKind
from platform.reporting.models import Audience, DestinationClass

NIGHT = datetime(2026, 3, 1, 3, 14, tzinfo=UTC)


def surfaces(**overrides: object) -> SurfacesConfig:
    """Return a team's surfaces section."""
    document: dict[str, object] = {
        "report_destinations": [
            {"kind": "slack", "target": "#incidents", "verified": True},
            {"kind": "jira", "target": "OPS", "audience": "team", "verified": True},
            {"kind": "chat", "target": "#status", "audience": "public", "verified": True},
        ],
        "notification_sinks": [
            {"kind": "pushover", "target": "user-key", "verified": True},
            {
                "kind": "chat",
                "target": "#incidents",
                "verified": True,
                "options": {"sound": "siren"},
            },
        ],
    }
    document.update(overrides)
    return SurfacesConfig(**document)  # type: ignore[arg-type]


# -- T038/FR-021: per-team destinations ----------------------------------------


def test_named_destinations_resolve_directly() -> None:
    built = destinations_of(surfaces())

    by_name = {item.name: item for item in built}
    assert by_name["slack:#incidents"].destination_class is DestinationClass.CHAT
    assert by_name["jira:OPS"].audience is Audience.TEAM
    assert by_name["jira:OPS"].verified


def test_a_generic_kind_resolves_through_the_deployments_mapping() -> None:
    built = destinations_of(surfaces(), resolve={"chat": "discord"})

    assert "discord:#status" in {item.name for item in built}


def test_a_generic_kind_with_no_mapping_is_skipped_rather_than_guessed() -> None:
    built = destinations_of(surfaces())

    assert all(item.kind != "chat" for item in built)
    assert len(built) == 2


def test_a_disabled_destination_is_not_returned() -> None:
    built = destinations_of(
        surfaces(
            report_destinations=[
                {"kind": "slack", "target": "#incidents", "verified": True, "enabled": False}
            ]
        )
    )

    assert built == ()


def test_a_destination_kind_nothing_renders_is_refused_at_the_write() -> None:
    with pytest.raises(ValidationError, match="must be one of"):
        SurfacesConfig(report_destinations=[{"kind": "carrier-pigeon", "target": "loft"}])


# -- Sinks ---------------------------------------------------------------------


def test_the_sinks_a_team_configured_are_returned_with_their_options() -> None:
    built = sinks_of(surfaces())

    by_name = {item.name: item for item in built}
    assert by_name["pushover:user-key"].kind is SinkKind.PUSHOVER
    assert by_name["chat:#incidents"].options["sound"] == "siren"
    assert all(item.verified for item in built)


def test_a_sink_kind_nothing_delivers_to_is_refused_at_the_write() -> None:
    with pytest.raises(ValidationError, match="must be one of"):
        SurfacesConfig(notification_sinks=[{"kind": "carrier-pigeon", "target": "loft"}])


def test_an_unverified_sink_is_carried_through_as_unverified() -> None:
    built = sinks_of(surfaces(notification_sinks=[{"kind": "pushover", "target": "user-key"}]))

    assert not built[0].verified


# -- The policy ----------------------------------------------------------------


def test_a_team_with_no_policy_gets_the_platform_defaults() -> None:
    policy = policy_of(surfaces())

    assert policy.quiet_hours is None
    assert policy.cooldown.window_seconds == NOTIFICATION_COOLDOWN_SECONDS
    assert policy.limits.limit == MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW


def test_quiet_hours_are_read_from_the_team_configuration() -> None:
    policy = policy_of(
        surfaces(
            notification_policy={
                "quiet_hours_enabled": True,
                "quiet_hours_start": 22,
                "quiet_hours_end": 7,
                "timezone": "Europe/Lisbon",
            }
        )
    )

    assert policy.quiet_hours is not None
    assert policy.quiet_hours.timezone == "Europe/Lisbon"
    assert policy.quiet_hours.covers(NIGHT)


def test_a_team_may_narrow_its_own_notification_volume() -> None:
    policy = policy_of(surfaces(notification_policy={"notifications_per_hour": 3}))

    assert policy.limits.limit == 3


def test_a_team_may_not_widen_past_the_platform_ceiling() -> None:
    with pytest.raises(ValidationError, match="must be between"):
        SurfacesConfig(
            notification_policy={
                "notifications_per_hour": MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW + 1
            }
        )


def test_a_team_may_not_shorten_its_way_out_of_the_cooldown() -> None:
    policy = policy_of(surfaces(notification_policy={"cooldown_seconds": 1.0}))

    assert policy.cooldown.window_seconds == NOTIFICATION_COOLDOWN_SECONDS


def test_a_team_may_lengthen_its_cooldown() -> None:
    policy = policy_of(
        surfaces(notification_policy={"cooldown_seconds": NOTIFICATION_COOLDOWN_SECONDS * 2})
    )

    assert policy.cooldown.window_seconds == NOTIFICATION_COOLDOWN_SECONDS * 2


def test_an_impossible_quiet_hours_boundary_is_refused_at_the_write() -> None:
    with pytest.raises(ValidationError, match="hour of the day"):
        SurfacesConfig(notification_policy={"quiet_hours_start": 25})


def test_the_policy_carries_the_teams_own_sinks() -> None:
    policy = policy_of(surfaces())

    assert {item.kind for item in policy.sinks} == {SinkKind.PUSHOVER, SinkKind.CHAT}
