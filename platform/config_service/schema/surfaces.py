"""Where investigations arrive from, and where their results go.

A surface entry is a destination and the conditions under which something is
sent there. The conditions are here rather than in the surface's own code
because "page the on-call channel for anything above warning, and file
everything else in the weekly digest" is a team's decision that changes without
a deployment.

No credential appears in this section. A chat integration's token lives in the
vault and is named by the integration entry; what is here is the channel, which
is not a secret and is the thing an operator actually edits.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import Field, field_validator

from config.constants.notifications import (
    AUDIENCE_PRIVATE,
    MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW,
    NOTIFICATION_COOLDOWN_SECONDS,
    NOTIFICATION_SINKS,
    QUIET_HOURS_END_HOUR,
    QUIET_HOURS_START_HOUR,
    REPORT_DESTINATIONS,
)
from config.constants.surfaces import CHAT_PLATFORMS, SURFACE_IDENTIFIERS
from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredFloat,
    ConfiguredInt,
    ConfiguredStr,
    ConfiguredStrList,
)

#: The generic destination kinds this section has always accepted. Kept
#: alongside the concrete ones below rather than replaced: a team's stored
#: ``kind: chat`` predates the named destinations and must keep resolving.
GENERIC_DESTINATION_KINDS: tuple[str, ...] = (
    "chat",
    "webhook",
    "email",
    "pull_request_comment",
    "knowledge_base",
)

#: Where a finished investigation can be delivered. Closed, because each one is
#: an adapter that has to exist. The named destinations are the thirteen the
#: reporting layer renders; the generic ones are resolved to a named destination
#: by whatever the deployment wired for that team.
DESTINATION_KINDS: tuple[str, ...] = GENERIC_DESTINATION_KINDS + tuple(
    kind for kind in REPORT_DESTINATIONS if kind not in GENERIC_DESTINATION_KINDS
)

#: The notification targets a team may configure.
SINK_KINDS: tuple[str, ...] = NOTIFICATION_SINKS

#: The severity floor a channel accepts. Ordered, so "at least warning" is a
#: comparison rather than a list nobody remembers to extend.
SEVERITIES: tuple[str, ...] = ("info", "warning", "error", "critical")


class ChannelSettings(ConfigSection):
    """One chat destination, and what it is willing to be told about."""

    #: Both required: a channel entry naming neither a platform nor a channel
    #: is configuration that delivers nowhere.
    platform: ConfiguredStr
    channel: ConfiguredStr
    min_severity: Literal["info", "warning", "error", "critical"] = "info"
    enabled: bool = True

    @field_validator("platform")
    @classmethod
    def _known_platform(cls, value: str) -> str:
        """Refuse a chat platform nothing adapts."""
        if value not in CHAT_PLATFORMS:
            raise ValueError(f"must be one of {', '.join(CHAT_PLATFORMS)}; found {value!r}")
        return value

    def accepts(self, severity: str) -> bool:
        """Return whether an alert of ``severity`` reaches this channel."""
        if not self.enabled or severity not in SEVERITIES:
            return False
        return SEVERITIES.index(severity) >= SEVERITIES.index(self.min_severity)


class DestinationSettings(ConfigSection):
    """One place a finished investigation is delivered."""

    #: Both required, for the same reason a channel needs both of its.
    kind: ConfiguredStr
    target: ConfiguredStr
    format: Literal["markdown", "html", "json"] = "markdown"
    enabled: bool = True
    #: Who reads what lands here. Decides whether masked identifiers are put
    #: back and whether evidence bodies may appear at all, so the safe value is
    #: the default and widening it is a deliberate edit.
    audience: Literal["private", "team", "public"] = AUDIENCE_PRIVATE
    #: Set once somebody has proved this destination works. Delivery refuses an
    #: unverified destination: an unverified one fails at 03:00, which is the
    #: worst possible moment to discover a wrong API token.
    verified: bool = False

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        """Refuse a destination kind no adapter delivers to."""
        if value not in DESTINATION_KINDS:
            raise ValueError(f"must be one of {', '.join(DESTINATION_KINDS)}; found {value!r}")
        return value


class SinkSettings(ConfigSection):
    """One notification target, and what its readership may be told."""

    kind: ConfiguredStr
    target: ConfiguredStr
    enabled: bool = True
    audience: Literal["private", "team", "public"] = AUDIENCE_PRIVATE
    verified: bool = False
    #: Per-sink extras a vendor understands and this schema does not interpret:
    #: a Pushover device name, a sound, an email sender. Strings only, because a
    #: nested structure here would be a second configuration language.
    options: Mapping[str, ConfiguredStr] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        """Refuse a sink kind nothing delivers to."""
        if value not in SINK_KINDS:
            raise ValueError(f"must be one of {', '.join(SINK_KINDS)}; found {value!r}")
        return value


class NotificationPolicySettings(ConfigSection):
    """How much of this team's attention a notification may take.

    Every value is a *narrowing* of the platform default. A team that wants to
    be interrupted more often than the shipped ceilings allow is asking for the
    ceiling not to be a ceiling, which is the thing Article II rules out.
    """

    quiet_hours_enabled: bool = False
    quiet_hours_start: ConfiguredInt = QUIET_HOURS_START_HOUR
    quiet_hours_end: ConfiguredInt = QUIET_HOURS_END_HOUR
    #: The team's own timezone. "22:00 to 07:00" means the team's night, and a
    #: window evaluated in UTC wakes a team in Auckland at lunchtime.
    timezone: ConfiguredStr = "UTC"
    cooldown_seconds: ConfiguredFloat = NOTIFICATION_COOLDOWN_SECONDS
    notifications_per_hour: ConfiguredInt = MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def _hour_of_the_day(cls, value: int) -> int:
        """Refuse a quiet-hours boundary that is not an hour."""
        if not 0 <= value <= 23:
            raise ValueError(f"must be an hour of the day, 0 to 23; found {value}")
        return value

    @field_validator("cooldown_seconds")
    @classmethod
    def _not_negative(cls, value: float) -> float:
        """Refuse a negative window."""
        if value < 0:
            raise ValueError(f"must not be negative; found {value}")
        return value

    @field_validator("notifications_per_hour")
    @classmethod
    def _within_the_platform_ceiling(cls, value: int) -> int:
        """Refuse a limit above the shipped ceiling."""
        if not 0 <= value <= MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW:
            raise ValueError(
                f"must be between 0 and {MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW}; found {value}"
            )
        return value


class SurfacesConfig(ConfigSection):
    """Which surfaces this team uses, and where their output goes."""

    enabled: ConfiguredStrList = ()
    channels: tuple[ChannelSettings, ...] = ()
    report_destinations: tuple[DestinationSettings, ...] = ()
    notification_sinks: tuple[SinkSettings, ...] = ()
    notification_policy: NotificationPolicySettings = NotificationPolicySettings()

    @field_validator("enabled")
    @classmethod
    def _known_surfaces(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Refuse a surface this deployment does not have."""
        unknown = [name for name in value if name not in SURFACE_IDENTIFIERS]
        if unknown:
            raise ValueError(
                f"names {', '.join(unknown)}; must be from {', '.join(SURFACE_IDENTIFIERS)}"
            )
        return value

    def channels_for(self, severity: str) -> tuple[ChannelSettings, ...]:
        """Return the channels an alert of ``severity`` reaches, in declared order."""
        return tuple(channel for channel in self.channels if channel.accepts(severity))

    def active_destinations(self) -> tuple[DestinationSettings, ...]:
        """Return every enabled report destination, in declared order."""
        return tuple(entry for entry in self.report_destinations if entry.enabled)

    def active_sinks(self) -> tuple[SinkSettings, ...]:
        """Return every enabled notification sink, in declared order."""
        return tuple(entry for entry in self.notification_sinks if entry.enabled)


SURFACES_FIELDS: tuple[str, ...] = tuple(SurfacesConfig.model_fields)
CHANNEL_FIELDS: tuple[str, ...] = tuple(ChannelSettings.model_fields)
DESTINATION_FIELDS: tuple[str, ...] = tuple(DestinationSettings.model_fields)
SINK_FIELDS: tuple[str, ...] = tuple(SinkSettings.model_fields)
NOTIFICATION_POLICY_FIELDS: tuple[str, ...] = tuple(NotificationPolicySettings.model_fields)


__all__ = [
    "CHANNEL_FIELDS",
    "DESTINATION_FIELDS",
    "DESTINATION_KINDS",
    "GENERIC_DESTINATION_KINDS",
    "NOTIFICATION_POLICY_FIELDS",
    "SEVERITIES",
    "SINK_FIELDS",
    "SINK_KINDS",
    "SURFACES_FIELDS",
    "ChannelSettings",
    "DestinationSettings",
    "NotificationPolicySettings",
    "SinkSettings",
    "SurfacesConfig",
]
