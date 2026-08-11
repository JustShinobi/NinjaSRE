"""What a destination is once the catalogue has had its say.

A destination is configuration — 062's ``transit.destinations`` section — but
whether it can actually be delivered to is not, because that depends on what
this deployment wired. So the record a screen renders is the declaration joined
to the catalogue, and a destination whose channel nothing carries says why
rather than rendering as a working row that silently never sends.

**The masking policy is named on the row.** Not looked up by the reader: what a
destination will withhold is part of what a destination *is*, and a row that
made an operator go somewhere else to find out would be the "five screens"
problem this feature exists to end.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.transit import NO_DELIVERY_CHANNEL_REASON
from platform.config_service.bindings import masking_policy
from platform.config_service.schema import RootConfig


@dataclass(frozen=True, slots=True)
class DeclaredDestination:
    """One destination, and whether this deployment can deliver to it."""

    destination_id: str
    channel: str
    events: tuple[str, ...]
    detail: str
    enabled: bool
    #: The level the outbound body passes through before it leaves. Named on the
    #: row because "what does this withhold" is part of what the destination is.
    masking_policy: str
    #: Empty when this destination can be delivered to; the reason when not.
    unconfigurable_reason: str = ""

    @property
    def deliverable(self) -> bool:
        """Return whether an event subscribed to here would actually go anywhere."""
        return self.enabled and not self.unconfigurable_reason


def delivery_channels(settings: RootConfig) -> tuple[str, ...]:
    """Return the channels this deployment has configured something to deliver over.

    The chat channels in the surfaces section, which is what a deployment
    actually wired rather than what the catalogue could theoretically carry.
    A destination bound to anything else is bound to a channel nobody
    configured, and saying so is more useful than delivering nowhere.
    """
    return tuple(
        dict.fromkeys(channel.platform for channel in settings.surfaces.channels if channel.enabled)
    )


def declared_destinations(
    settings: RootConfig,
    *,
    channels: tuple[str, ...] | None = None,
) -> tuple[DeclaredDestination, ...]:
    """Return every declared destination joined to what this deployment can carry.

    ``channels`` defaults to what the configuration itself declares. It is a
    parameter so a caller holding a different catalogue — a test, or a
    deployment whose channels come from somewhere else — can say so without
    this module having to know about that somewhere else.
    """
    available = delivery_channels(settings) if channels is None else channels
    policy = masking_policy(settings.policies).level.value
    return tuple(
        DeclaredDestination(
            destination_id=declared.destination_id,
            channel=declared.channel,
            events=tuple(declared.events),
            detail=declared.detail,
            enabled=declared.enabled,
            masking_policy=policy,
            unconfigurable_reason=(
                ""
                if declared.channel in available
                else NO_DELIVERY_CHANNEL_REASON
                if not available
                else (
                    f"No configured channel carries {declared.channel!r}. This deployment "
                    f"delivers over {', '.join(available)}."
                )
            ),
        )
        for declared in settings.transit.destinations
    )


def destinations_for(
    settings: RootConfig,
    event: str,
    *,
    channels: tuple[str, ...] | None = None,
) -> tuple[DeclaredDestination, ...]:
    """Return every destination that would actually be told about ``event``.

    Deliverable ones only. A destination the catalogue cannot carry is still on
    the screen — with its reason — and is deliberately not in this list, because
    a dispatcher that tried it would produce a failed delivery per event for a
    misconfiguration that is already visible.
    """
    return tuple(
        destination
        for destination in declared_destinations(settings, channels=channels)
        if destination.deliverable and event in destination.events
    )


__all__ = [
    "DeclaredDestination",
    "declared_destinations",
    "delivery_channels",
    "destinations_for",
]
