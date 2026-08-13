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
from typing import Annotated, Literal

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
    field_help,
    section_help,
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

    model_config = section_help(
        "One chat channel and the severity floor it accepts. No token is entered here: "
        "the chat integration holds it."
    )

    #: Both required: a channel entry naming neither a platform nor a channel
    #: is configuration that delivers nowhere.
    platform: Annotated[ConfiguredStr, field_help("Which chat platform this channel is on.")]
    channel: Annotated[
        ConfiguredStr, field_help("The channel to post in, as that platform names it.")
    ]
    min_severity: Annotated[
        Literal["info", "warning", "error", "critical"],
        field_help(
            "The lowest severity this channel is told about. Anything below it is not posted here."
        ),
    ] = "info"
    enabled: Annotated[
        bool, field_help("Off keeps the channel configured and stops posting to it.")
    ] = True

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

    model_config = section_help(
        "One place a finished report is delivered, and who is expected to read it there."
    )

    #: Both required, for the same reason a channel needs both of its.
    kind: Annotated[
        ConfiguredStr,
        field_help(
            "What sort of destination this is — a chat, a webhook, an "
            "email, a page in your knowledge base."
        ),
    ]
    target: Annotated[
        ConfiguredStr,
        field_help("Where exactly the report goes: the channel, the address, the page."),
    ]
    format: Annotated[
        Literal["markdown", "html", "json"],
        field_help("How the report is written for this destination."),
    ] = "markdown"
    enabled: Annotated[
        bool, field_help("Off keeps the destination and stops delivering to it.")
    ] = True
    #: Who reads what lands here. Decides whether masked identifiers are put
    #: back and whether evidence bodies may appear at all, so the safe value is
    #: the default and widening it is a deliberate edit.
    audience: Annotated[
        Literal["private", "team", "public"],
        field_help(
            "Who can read what lands here. It decides whether hostnames and identifiers "
            "are restored and whether raw evidence may appear at all, so widen it only "
            "on purpose."
        ),
    ] = AUDIENCE_PRIVATE
    #: Set once somebody has proved this destination works. Delivery refuses an
    #: unverified destination: an unverified one fails at 03:00, which is the
    #: worst possible moment to discover a wrong API token.
    verified: Annotated[
        bool,
        field_help(
            "Set by a successful test delivery. Nothing is sent to an unverified "
            "destination, so that a wrong address is found now rather than at 03:00."
        ),
    ] = False

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        """Refuse a destination kind no adapter delivers to."""
        if value not in DESTINATION_KINDS:
            raise ValueError(f"must be one of {', '.join(DESTINATION_KINDS)}; found {value!r}")
        return value


class SinkSettings(ConfigSection):
    """One notification target, and what its readership may be told."""

    model_config = section_help(
        "One place short notifications are sent — a push service, an email address, a "
        "webhook — and who is expected to read them there."
    )

    kind: Annotated[ConfiguredStr, field_help("What sort of notification target this is.")]
    target: Annotated[
        ConfiguredStr, field_help("Where the notification goes: the address, key or channel.")
    ]
    enabled: Annotated[bool, field_help("Off keeps the target and stops notifying it.")] = True
    audience: Annotated[
        Literal["private", "team", "public"],
        field_help(
            "Who can read what is sent here. It decides how much of an incident may "
            "appear in the text."
        ),
    ] = AUDIENCE_PRIVATE
    verified: Annotated[
        bool,
        field_help(
            "Set by a successful test notification. Nothing is sent to an unverified target."
        ),
    ] = False
    #: Per-sink extras a vendor understands and this schema does not interpret:
    #: a Pushover device name, a sound, an email sender. Strings only, because a
    #: nested structure here would be a second configuration language.
    options: Annotated[
        Mapping[str, ConfiguredStr],
        field_help(
            "Extras this particular target understands — a device name, a sound, a "
            "sender address. Text values only."
        ),
    ] = Field(default_factory=dict)

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
    ceiling not to be a ceiling, which the platform does not allow.
    """

    model_config = section_help(
        "How much of this team's attention a notification may take: when it is quiet, "
        "how soon the same thing may be repeated, and how many arrive in an hour. Every "
        "value here can only make the platform ceiling stricter."
    )

    quiet_hours_enabled: Annotated[
        bool,
        field_help("Hold non-urgent notifications during the hours set below."),
    ] = False
    quiet_hours_start: Annotated[
        ConfiguredInt, field_help("The hour of the day quiet hours begin, 0 to 23.")
    ] = QUIET_HOURS_START_HOUR
    quiet_hours_end: Annotated[
        ConfiguredInt, field_help("The hour of the day quiet hours end, 0 to 23.")
    ] = QUIET_HOURS_END_HOUR
    #: The team's own timezone. "22:00 to 07:00" means the team's night, and a
    #: window evaluated in UTC wakes a team in Auckland at lunchtime.
    timezone: Annotated[
        ConfiguredStr,
        field_help(
            "The team's own timezone, so quiet hours mean this team's night rather than "
            "somebody else's."
        ),
    ] = "UTC"
    cooldown_seconds: Annotated[
        ConfiguredFloat,
        field_help("How long to wait before notifying about the same thing again."),
    ] = NOTIFICATION_COOLDOWN_SECONDS
    notifications_per_hour: Annotated[
        ConfiguredInt,
        field_help(
            "The most notifications this team receives in an hour. Cannot be raised "
            "above the platform ceiling."
        ),
    ] = MAX_NOTIFICATIONS_PER_TEAM_PER_WINDOW

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


class ConsoleSurfaceSettings(ConfigSection):
    """What the web console remembers about a team, on the deployment's side.

    One field, and the reason it is here rather than in the browser is the whole
    of it: a dismissal kept in browser storage is a dismissal that has not
    happened on the second machine, or in the second browser, or for the second
    person on the same team. The guided tutorial is about *this deployment*, so
    what records that somebody has seen it belongs where the deployment's other
    per-team decisions live.

    Nothing here is a secret, and nothing here may become one. What the console
    keeps on this side is what a colleague could read over your shoulder without
    it mattering.
    """

    model_config = section_help(
        "What the console remembers about this team on the deployment's side, so it is "
        "the same in every browser."
    )

    #: Whether the guided tutorial has been dismissed for this team. The overlay
    #: is only ever shown while the setup checklist has something outstanding,
    #: so a stale ``False`` cannot trap a configured deployment behind it.
    tutorial_dismissed: Annotated[
        bool,
        field_help("Whether this team has dismissed the guided tour of the console."),
    ] = False


class SurfacesConfig(ConfigSection):
    """Which surfaces this team uses, and where their output goes."""

    model_config = section_help(
        "How this team reaches the platform and how the platform reaches it back: which "
        "surfaces are on, and where alerts, reports and notifications are sent."
    )

    enabled: Annotated[
        ConfiguredStrList,
        field_help("Which ways in this team uses — the console, the chat bot, the command line."),
    ] = ()
    console: ConsoleSurfaceSettings = ConsoleSurfaceSettings()
    channels: Annotated[
        tuple[ChannelSettings, ...],
        field_help("Chat channels this team is alerted in."),
    ] = ()
    report_destinations: Annotated[
        tuple[DestinationSettings, ...],
        field_help("Where a finished investigation report is delivered."),
    ] = ()
    notification_sinks: Annotated[
        tuple[SinkSettings, ...],
        field_help("Where short notifications are sent, as opposed to full reports."),
    ] = ()
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
CONSOLE_SURFACE_FIELDS: tuple[str, ...] = tuple(ConsoleSurfaceSettings.model_fields)
CHANNEL_FIELDS: tuple[str, ...] = tuple(ChannelSettings.model_fields)
DESTINATION_FIELDS: tuple[str, ...] = tuple(DestinationSettings.model_fields)
SINK_FIELDS: tuple[str, ...] = tuple(SinkSettings.model_fields)
NOTIFICATION_POLICY_FIELDS: tuple[str, ...] = tuple(NotificationPolicySettings.model_fields)


__all__ = [
    "CHANNEL_FIELDS",
    "CONSOLE_SURFACE_FIELDS",
    "ConsoleSurfaceSettings",
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
