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

from typing import Literal

from pydantic import field_validator

from config.constants.surfaces import CHAT_PLATFORMS, SURFACE_IDENTIFIERS
from platform.config_service.schema.types import (
    ConfigSection,
    ConfiguredStr,
    ConfiguredStrList,
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

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        """Refuse a destination kind no adapter delivers to."""
        if value not in DESTINATION_KINDS:
            raise ValueError(f"must be one of {', '.join(DESTINATION_KINDS)}; found {value!r}")
        return value


class SurfacesConfig(ConfigSection):
    """Which surfaces this team uses, and where their output goes."""

    enabled: ConfiguredStrList = ()
    channels: tuple[ChannelSettings, ...] = ()
    report_destinations: tuple[DestinationSettings, ...] = ()
    notification_sinks: tuple[DestinationSettings, ...] = ()

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


SURFACES_FIELDS: tuple[str, ...] = tuple(SurfacesConfig.model_fields)
CHANNEL_FIELDS: tuple[str, ...] = tuple(ChannelSettings.model_fields)
DESTINATION_FIELDS: tuple[str, ...] = tuple(DestinationSettings.model_fields)


__all__ = [
    "CHANNEL_FIELDS",
    "DESTINATION_FIELDS",
    "DESTINATION_KINDS",
    "SEVERITIES",
    "SURFACES_FIELDS",
    "ChannelSettings",
    "DestinationSettings",
    "SurfacesConfig",
]
