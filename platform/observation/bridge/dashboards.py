"""Linking a report to the panel that shows the window in question, or to nothing.

A report that says a datastore reached 96% has told an operator a number. A
report that links to the panel showing the last six hours of that datastore has
told them whether it is a step or a climb, which is the thing that decides what
they do next.

Three rules, and the last one is the one that matters.

**A dashboard is mapped to a resource kind or to a detector.** A detector's own
panel is the more useful mapping where it exists — it is the picture of the
exact condition — so a detector mapping wins over a kind mapping.

**A link carries the incident's own window**, padded either side. A panel that
starts exactly at the firing instant shows a cliff with nothing before it, and
the minutes before are what tell an operator whether it was a step or a climb.

**Where nothing is mapped, there is no link.** Never a default, never the
Grafana home page, never "the closest dashboard". A link to a default dashboard
is a dead end wearing the appearance of an answer, and the operator who follows
it loses the time they would have spent looking somewhere useful. The same
applies to a Grafana behind authentication this deployment does not hold: the
link is omitted and the reason is recorded, because a link that answers with a
login page is worse than none.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from config.constants.observability_bridge import DASHBOARD_LINK_PADDING_SECONDS
from platform.observability.logging import get_logger
from platform.observation.bridge.errors import DashboardsUnreachable
from platform.observation.bridge.ports import DashboardSource

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DashboardMapping:
    """One dashboard, and what it is the picture of."""

    dashboard_uid: str
    title: str
    #: The origin a reader would open it at. Held per mapping rather than
    #: globally because a deployment may reasonably link to two Grafanas, and a
    #: single origin would silently send half the links to the wrong one.
    base_url: str
    resource_kinds: tuple[str, ...] = ()
    detector_ids: tuple[str, ...] = ()
    #: The panel worth opening at, when the dashboard has an obvious one.
    panel_id: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not self.dashboard_uid or not self.base_url:
            raise ValueError(
                "A dashboard mapping needs a dashboard and an origin to open it at; "
                "a mapping that resolves to no URL would produce a link to nowhere."
            )
        if not self.resource_kinds and not self.detector_ids:
            raise ValueError(
                f"dashboard {self.dashboard_uid!r} is mapped to nothing, so it would "
                f"either never be linked or be linked to everything. Both are worse "
                f"than declaring what it is a picture of."
            )

    def matches_detector(self, detector_id: str) -> bool:
        """Return whether this dashboard is the picture of ``detector_id``'s condition."""
        return bool(detector_id) and detector_id in self.detector_ids

    def matches_kind(self, resource_kind: str) -> bool:
        """Return whether this dashboard is about resources of ``resource_kind``."""
        return bool(resource_kind) and resource_kind in self.resource_kinds


@dataclass(frozen=True, slots=True)
class DashboardLink:
    """One link, with the window it opens at."""

    url: str
    title: str
    dashboard_uid: str
    from_at: datetime
    to_at: datetime


@dataclass(frozen=True, slots=True)
class DashboardOutcome:
    """A link, or the reason there is not one.

    Never both empty. An omission with no reason is the thing this whole module
    is arranged against — a report that quietly has no link tells nobody whether
    that is because nothing was mapped or because Grafana refused us.
    """

    link: DashboardLink | None = None
    omitted_because: str = ""


def link_for(
    mappings: Sequence[DashboardMapping],
    *,
    resource_kind: str,
    detector_id: str,
    opened_at: datetime,
    closed_at: datetime,
) -> DashboardLink | None:
    """Return the link for this incident's window, or ``None`` when nothing is mapped.

    A detector mapping is preferred over a kind mapping: the detector's own
    panel is the picture of the exact condition, and the kind's is the picture
    of the neighbourhood.
    """
    chosen = next(
        (mapping for mapping in mappings if mapping.matches_detector(detector_id)),
        None,
    ) or next((mapping for mapping in mappings if mapping.matches_kind(resource_kind)), None)
    if chosen is None:
        return None

    padding = timedelta(seconds=DASHBOARD_LINK_PADDING_SECONDS)
    from_at = opened_at - padding
    to_at = closed_at + padding
    query = f"from={_millis(from_at)}&to={_millis(to_at)}"
    if chosen.panel_id:
        query = f"{query}&viewPanel={chosen.panel_id}"
    return DashboardLink(
        url=f"{chosen.base_url.rstrip('/')}/d/{chosen.dashboard_uid}?{query}",
        title=chosen.title,
        dashboard_uid=chosen.dashboard_uid,
        from_at=from_at,
        to_at=to_at,
    )


async def dashboard_link(
    source: DashboardSource,
    *,
    mappings: Sequence[DashboardMapping],
    resource_kind: str,
    detector_id: str,
    opened_at: datetime,
    closed_at: datetime,
) -> DashboardOutcome:
    """Return the link a report should carry, or the reason it carries none.

    The reachability check runs only when there is something to link to. Asking
    Grafana whether it is up in order to decide not to link to it is a round
    trip for nothing, and it happens on every report in a deployment that has
    mapped no dashboards — which is most of them.
    """
    link = link_for(
        mappings,
        resource_kind=resource_kind,
        detector_id=detector_id,
        opened_at=opened_at,
        closed_at=closed_at,
    )
    if link is None:
        return DashboardOutcome(
            omitted_because=(
                f"no dashboard is mapped to {detector_id or resource_kind or 'this incident'}; "
                f"the report omits the link rather than sending a responder to a default one"
            )
        )

    try:
        await source.check()
    except DashboardsUnreachable as unreachable:
        logger.info("bridge.dashboards_unreachable", reason=unreachable.reason)
        return DashboardOutcome(
            omitted_because=(
                f"the dashboard at {link.url} was not linked: {unreachable.reason}. A link "
                f"that answers with a login page is worse than no link"
            )
        )
    except Exception as broken:  # noqa: BLE001 - a degraded link is still a decision
        # Deliberately broad. Whatever went wrong reaching Grafana, the report
        # still has to be produced and still has to say why it has no link.
        logger.info("bridge.dashboards_unreachable", reason=str(broken))
        return DashboardOutcome(
            omitted_because=(
                f"the dashboard at {link.url} was not linked: {type(broken).__name__}: {broken}"
            )
        )

    return DashboardOutcome(link=link)


def _millis(moment: datetime) -> int:
    """Return ``moment`` as the millisecond epoch a dashboard URL uses."""
    return int(moment.timestamp() * 1_000)


__all__ = [
    "DashboardLink",
    "DashboardMapping",
    "DashboardOutcome",
    "dashboard_link",
    "link_for",
]
