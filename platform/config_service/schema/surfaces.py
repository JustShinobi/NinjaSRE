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

from dataclasses import dataclass

from config.constants.surfaces import CHAT_PLATFORMS, SURFACE_IDENTIFIERS
from platform.config_service.schema.reader import Reader

CHANNEL_FIELDS: tuple[str, ...] = ("platform", "channel", "min_severity", "enabled")
DESTINATION_FIELDS: tuple[str, ...] = ("kind", "target", "format", "enabled")
SURFACES_FIELDS: tuple[str, ...] = (
    "enabled",
    "channels",
    "report_destinations",
    "notification_sinks",
)

#: Where a finished investigation can be delivered. Closed, because each one is
#: an adapter that has to exist.
DESTINATION_KINDS: tuple[str, ...] = (
    "chat",
    "webhook",
    "email",
    "pull_request_comment",
    "knowledge_base",
)

#: The severity floor a channel accepts. Ordered, so "at least warning" is a
#: comparison rather than a list nobody remembers to extend.
SEVERITIES: tuple[str, ...] = ("info", "warning", "error", "critical")


@dataclass(frozen=True, slots=True)
class ChannelSettings:
    """One chat destination, and what it is willing to be told about."""

    platform: str
    channel: str
    min_severity: str = "info"
    enabled: bool = True

    @classmethod
    def of(cls, reader: Reader) -> ChannelSettings:
        """Return the channel ``reader`` describes."""
        reader.close(CHANNEL_FIELDS)
        platform = reader.string("platform", allowed=CHAT_PLATFORMS)
        channel = reader.string("channel")
        if not platform:
            reader.fail("platform", f"must be one of {', '.join(CHAT_PLATFORMS)}")
        if not channel:
            reader.fail("channel", "a channel entry needs the channel to post in")
        return cls(
            platform=platform,
            channel=channel,
            min_severity=reader.string("min_severity", "info", allowed=SEVERITIES),
            enabled=reader.boolean("enabled", True),
        )

    def accepts(self, severity: str) -> bool:
        """Return whether an alert of ``severity`` reaches this channel."""
        if not self.enabled or severity not in SEVERITIES:
            return False
        return SEVERITIES.index(severity) >= SEVERITIES.index(self.min_severity)


@dataclass(frozen=True, slots=True)
class DestinationSettings:
    """One place a finished investigation is delivered."""

    kind: str
    target: str
    format: str = "markdown"
    enabled: bool = True

    @classmethod
    def of(cls, reader: Reader) -> DestinationSettings:
        """Return the destination ``reader`` describes."""
        reader.close(DESTINATION_FIELDS)
        kind = reader.string("kind", allowed=DESTINATION_KINDS)
        target = reader.string("target")
        if not kind:
            reader.fail("kind", f"must be one of {', '.join(DESTINATION_KINDS)}")
        if not target:
            reader.fail("target", "a destination needs somewhere to deliver to")
        return cls(
            kind=kind,
            target=target,
            format=reader.string("format", "markdown", allowed=("markdown", "html", "json")),
            enabled=reader.boolean("enabled", True),
        )


@dataclass(frozen=True, slots=True)
class SurfacesConfig:
    """Which surfaces this team uses, and where their output goes."""

    enabled: tuple[str, ...] = ()
    channels: tuple[ChannelSettings, ...] = ()
    report_destinations: tuple[DestinationSettings, ...] = ()
    notification_sinks: tuple[DestinationSettings, ...] = ()

    @classmethod
    def of(cls, reader: Reader) -> SurfacesConfig:
        """Return the surface configuration ``reader`` describes."""
        reader.close(SURFACES_FIELDS)
        return cls(
            enabled=reader.strings("enabled", allowed=SURFACE_IDENTIFIERS),
            channels=tuple(ChannelSettings.of(each) for each in reader.sections("channels")),
            report_destinations=tuple(
                DestinationSettings.of(each) for each in reader.sections("report_destinations")
            ),
            notification_sinks=tuple(
                DestinationSettings.of(each) for each in reader.sections("notification_sinks")
            ),
        )

    def channels_for(self, severity: str) -> tuple[ChannelSettings, ...]:
        """Return the channels an alert of ``severity`` reaches, in declared order."""
        return tuple(channel for channel in self.channels if channel.accepts(severity))

    def active_destinations(self) -> tuple[DestinationSettings, ...]:
        """Return every enabled report destination, in declared order."""
        return tuple(entry for entry in self.report_destinations if entry.enabled)


__all__ = [
    "CHANNEL_FIELDS",
    "ChannelSettings",
    "DESTINATION_FIELDS",
    "DESTINATION_KINDS",
    "DestinationSettings",
    "SEVERITIES",
    "SURFACES_FIELDS",
    "SurfacesConfig",
]
