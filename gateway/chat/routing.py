"""Which team a channel serves, and which alerts are allowed to arrive in it.

One workspace commonly serves several teams, and a bot that treated every
channel as the same tenant would put one team's incident in another team's
window. So the routing table is the thing that answers "whose run is this", and
a channel with no row is not served at all — an unrouted channel is refused
rather than defaulted, for the same reason an unknown node denies in
``platform/identity/authorisation.py``.

**Per-channel alert settings are a filter, not a subscription.** A row names the
sources that may auto-post there and the severity floor. ``#incidents`` takes
critical pages from everywhere; ``#checkout-team`` takes everything from one
source. Both are the same row with different values, which is what keeps the
matching in one function.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from core.domain.alerts.normalisation import Severity
from gateway.chat.port import ChatTarget

#: Most severe first. What "at or above this floor" means, and the reason the
#: floor is comparable at all — ``Severity`` is a name, not a number.
SEVERITY_ORDER: Final[tuple[Severity, ...]] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
    Severity.UNKNOWN,
)


def at_or_above(severity: Severity, floor: Severity) -> bool:
    """Return whether ``severity`` is at least as severe as ``floor``.

    ``UNKNOWN`` is last, so a floor of ``UNKNOWN`` takes everything and a
    severity of ``UNKNOWN`` clears only that floor. An alert nobody classified
    is not evidence that it is quiet.
    """
    return SEVERITY_ORDER.index(severity) <= SEVERITY_ORDER.index(floor)


@dataclass(frozen=True, slots=True)
class ChannelRouting:
    """One channel, the team it serves, and what may be posted into it."""

    platform: str
    channel_id: str
    team_id: str
    workspace_id: str = ""
    #: Alert sources permitted to auto-post here. Empty means every source.
    alert_sources: frozenset[str] = field(default_factory=frozenset)
    #: The least severe alert that may auto-post here.
    minimum_severity: Severity = Severity.HIGH
    #: Whether alerts auto-post at all. A channel people only ask questions in
    #: is routed — so a mention works — without becoming an alert firehose.
    auto_post: bool = True

    def accepts(self, *, source: str, severity: Severity) -> bool:
        """Return whether an alert from ``source`` at ``severity`` may post here."""
        if not self.auto_post:
            return False
        if self.alert_sources and source not in self.alert_sources:
            return False
        return at_or_above(severity, self.minimum_severity)

    @property
    def key(self) -> str:
        """Return the identifier the table looks this row up by."""
        return f"{self.platform}:{self.workspace_id}:{self.channel_id}"

    def target(self) -> ChatTarget:
        """Return the channel itself, unbound to any thread."""
        return ChatTarget(
            platform=self.platform, channel_id=self.channel_id, workspace_id=self.workspace_id
        )


class UnroutedChannel(LookupError):
    """A channel nobody configured, which is therefore not served.

    Named rather than returning ``None`` at the call sites that must not
    continue: an investigation with no team is one whose permissions, its
    configuration, and its storage scope are all unanswered.
    """

    def __init__(self, target: ChatTarget) -> None:
        self.target = target
        super().__init__(
            f"{target.platform} channel {target.channel_id!r} is not routed to a team. "
            f"Add it to the chat routing configuration; an unrouted channel is not served."
        )


@dataclass(frozen=True, slots=True)
class RoutingTable:
    """Every routed channel, and the two questions asked of them."""

    routes: tuple[ChannelRouting, ...] = ()

    @classmethod
    def of(cls, routes: Iterable[ChannelRouting]) -> RoutingTable:
        """Return a table of ``routes``, refusing two rows for one channel.

        Two rows would make "which team" depend on iteration order, and the
        first person to notice would be whoever read an audit line naming the
        wrong team.
        """
        collected = tuple(routes)
        seen: set[str] = set()
        for route in collected:
            if route.key in seen:
                raise ValueError(
                    f"{route.platform} channel {route.channel_id!r} is routed twice. One "
                    f"channel serves one team, or 'which team' has no answer."
                )
            seen.add(route.key)
        return cls(routes=collected)

    def find(self, target: ChatTarget) -> ChannelRouting | None:
        """Return the row for ``target``'s channel, or ``None``."""
        wanted = f"{target.platform}:{target.workspace_id}:{target.channel_id}"
        for route in self.routes:
            if route.key == wanted:
                return route
        return None

    def team_of(self, target: ChatTarget) -> str:
        """Return the team ``target``'s channel serves.

        Raises:
            UnroutedChannel: nobody configured this channel.
        """
        route = self.find(target)
        if route is None:
            raise UnroutedChannel(target)
        return route.team_id

    def is_served(self, target: ChatTarget) -> bool:
        """Return whether this channel is configured at all."""
        return self.find(target) is not None

    def channels_for_alert(
        self, *, source: str, severity: Severity, team_id: str = ""
    ) -> tuple[ChatTarget, ...]:
        """Return the channels an alert from ``source`` may auto-post into."""
        return tuple(
            route.target()
            for route in self.routes
            if (not team_id or route.team_id == team_id)
            and route.accepts(source=source, severity=severity)
        )

    def channels_of(self, team_id: str) -> tuple[ChatTarget, ...]:
        """Return every channel serving ``team_id``."""
        return tuple(route.target() for route in self.routes if route.team_id == team_id)


def routing_of(rows: Sequence[Mapping[str, Any]]) -> RoutingTable:
    """Return the table a deployment's configured rows describe."""
    return RoutingTable.of(
        ChannelRouting(
            platform=str(row["platform"]),
            channel_id=str(row["channel_id"]),
            team_id=str(row["team_id"]),
            workspace_id=str(row.get("workspace_id", "")),
            alert_sources=frozenset(str(name) for name in row.get("alert_sources") or ()),
            minimum_severity=Severity(str(row.get("minimum_severity", Severity.HIGH.value))),
            auto_post=bool(row.get("auto_post", True)),
        )
        for row in rows
    )


__all__ = [
    "SEVERITY_ORDER",
    "ChannelRouting",
    "RoutingTable",
    "UnroutedChannel",
    "at_or_above",
    "routing_of",
]
