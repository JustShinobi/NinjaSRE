"""Turning one team's resolved configuration into the objects that deliver for it.

The config service owns the *document*; this owns the reading of it. Keeping the
two apart is what lets the schema stay a plain typed surface — no imports from
the reporting or notification layers, no behaviour — while the knowledge of what
a stored ``kind: chat`` resolves to lives beside the code that has to resolve it.

**A generic kind needs an operator's mapping.** ``chat`` is not a destination; it
is a class of them, and which of the four platforms a team means is a fact the
deployment holds. An unmapped generic kind is skipped and *named*, because
silently dropping a configured destination is how a team finds out their reports
went nowhere by not receiving any.

**A team's numbers narrow, never widen.** The schema already refuses a rate limit
above the platform ceiling; this takes the smaller of the two for the cooldown as
well, so a team cannot shorten its way out of a suppression window.
"""

from __future__ import annotations

from collections.abc import Mapping

from config.constants.notifications import NOTIFICATION_COOLDOWN_SECONDS
from platform.config_service.schema.surfaces import (
    DestinationSettings,
    NotificationPolicySettings,
    SurfacesConfig,
)
from platform.notifications.cooldown import Cooldown
from platform.notifications.limits import RateLimiter
from platform.notifications.models import NotificationSink, SinkKind
from platform.notifications.policy import NotificationPolicy, QuietHours
from platform.observability.logging import get_logger
from platform.reporting.models import Audience, Destination

logger = get_logger(__name__)

#: How long a window a team's ``notifications_per_hour`` is expressed over.
_RATE_LIMIT_WINDOW_SECONDS = 3_600.0


def destinations_of(
    surfaces: SurfacesConfig, *, resolve: Mapping[str, str] | None = None
) -> tuple[Destination, ...]:
    """Return the report destinations one team's configuration names.

    ``resolve`` maps a generic kind to the named destination this deployment
    wired for it — ``{"chat": "slack", "knowledge_base": "confluence"}``. A
    generic kind with no mapping is skipped and logged rather than guessed.
    """
    mapping = dict(resolve or {})
    built: list[Destination] = []
    for entry in surfaces.active_destinations():
        kind = mapping.get(entry.kind, entry.kind)
        try:
            built.append(_destination(entry, kind))
        except ValueError:
            logger.warning(
                "reporting.destination_not_resolved",
                kind=entry.kind,
                target=entry.target,
                resolved_to=kind,
            )
    return tuple(built)


def sinks_of(surfaces: SurfacesConfig) -> tuple[NotificationSink, ...]:
    """Return the notification sinks one team's configuration names."""
    return tuple(
        NotificationSink(
            kind=SinkKind(entry.kind),
            target=entry.target,
            audience=Audience(entry.audience),
            enabled=entry.enabled,
            verified=entry.verified,
            options=dict(entry.options),
        )
        for entry in surfaces.active_sinks()
    )


def policy_of(surfaces: SurfacesConfig) -> NotificationPolicy:
    """Return the notification policy one team's configuration describes."""
    settings = surfaces.notification_policy
    return NotificationPolicy(
        sinks=sinks_of(surfaces),
        quiet_hours=_quiet_hours(settings),
        cooldown=Cooldown(
            window_seconds=max(settings.cooldown_seconds, NOTIFICATION_COOLDOWN_SECONDS)
        ),
        limits=RateLimiter(
            window_seconds=_RATE_LIMIT_WINDOW_SECONDS,
            limit=settings.notifications_per_hour,
        ),
    )


def _destination(entry: DestinationSettings, kind: str) -> Destination:
    """Return the destination ``entry`` describes once its kind is resolved."""
    return Destination(
        kind=kind,
        target=entry.target,
        audience=Audience(entry.audience),
        verified=entry.verified,
        options={"format": entry.format},
    )


def _quiet_hours(settings: NotificationPolicySettings) -> QuietHours | None:
    """Return the team's quiet-hours window, or ``None`` when they have none."""
    if not settings.quiet_hours_enabled:
        return None
    return QuietHours(
        start_hour=settings.quiet_hours_start,
        end_hour=settings.quiet_hours_end,
        timezone=settings.timezone,
    )


__all__ = ["destinations_of", "policy_of", "sinks_of"]
