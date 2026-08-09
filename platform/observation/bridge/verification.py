"""Asking a metrics system a real question, and reporting what is publishing into it.

Configuring a metrics source is two facts and an operator only supplies one of
them. They say where Prometheus is; they do not say what is scraping into it,
and that is the fact this feature's value depends on. A shipped mapping for the
Proxmox exporter is worth nothing against a Prometheus that only has a node
exporter, and the way that failure presents is silence — the mapping produces no
series, no detector fires, and the deployment looks like it is watching.

So verification makes a query and reports **per exporter**. Present, absent, and
what would publish the absent ones. An operator reading it learns which half of
their stack this deployment can actually use.

**Unreachable reports nothing absent.** A source that could not be asked has not
established that anything is missing, and a verification that listed every
exporter as absent after a connection refusal would send somebody to install
software they already have.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from config.constants.observability_bridge import (
    EXPORTER_NODE,
    EXPORTER_PROXMOX,
    EXPORTER_TEXTFILE,
)
from platform.observability.logging import get_logger
from platform.observation.bridge.errors import MetricsSourceUnreachable
from platform.observation.bridge.ports import MetricSeries, MetricsSource

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ExporterExpectation:
    """One exporter this deployment knows how to use, and how to tell it is there.

    ``matcher`` is a selector rather than a metric name because presence is a
    question about series, not about the schema: a Prometheus that scraped the
    Proxmox exporter once last week still has the metric name and is not
    publishing it now.
    """

    exporter: str
    matcher: str
    #: What it publishes, in the operator's terms rather than in metric names.
    describes: str
    #: What to do about it being absent. Every expectation carries one, because
    #: "absent" with no next step is a dead end and all three of these have a
    #: short fix.
    install_hint: str


@dataclass(frozen=True, slots=True)
class ExporterPresence:
    """Whether one expected exporter is publishing, and what it would give us."""

    exporter: str
    present: bool
    series_seen: int
    describes: str
    install_hint: str


#: The exporters a Proxmox homelab actually runs, and the one that carries the
#: readings nothing else publishes. Shipped rather than configured: their label
#: schemes are stable, and an operator who has to declare them has to learn a
#: mapping language before the deployment works at all.
SHIPPED_EXPORTERS: Final[tuple[ExporterExpectation, ...]] = (
    ExporterExpectation(
        exporter=EXPORTER_PROXMOX,
        matcher="pve_up",
        describes="the cluster's own view of its nodes, guests and datastores",
        install_hint=(
            "run prometheus-pve-exporter against the cluster and scrape it; it needs a "
            "read-only Proxmox token and publishes every guest and datastore"
        ),
    ),
    ExporterExpectation(
        exporter=EXPORTER_NODE,
        matcher="node_uname_info",
        describes="each machine's own view of its cpu, memory, filesystems and network",
        install_hint=(
            "install node_exporter on each node and scrape it; the hypervisor's view of a "
            "node does not include its filesystems or its interfaces"
        ),
    ),
    ExporterExpectation(
        exporter=EXPORTER_TEXTFILE,
        matcher="node_textfile_mtime_seconds",
        describes=(
            "the readings no exporter publishes: failed systemd units, bridge state, "
            "and thin-pool metadata usage"
        ),
        install_hint=(
            "point node_exporter at a textfile directory and write those three readings "
            "into it from a timer; they are the ones that explain a hypervisor outage "
            "and the REST API cannot answer any of them"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class MetricsVerification:
    """What one real query established about a metrics source.

    ``reachable`` gates everything else. When it is false the exporter lists are
    empty rather than all-absent, so no reader can mistake "we could not look"
    for "we looked and it is not there".
    """

    source: str
    reachable: bool
    checked_at: datetime
    exporters: tuple[ExporterPresence, ...] = ()
    failure: str = ""

    @property
    def present(self) -> tuple[ExporterPresence, ...]:
        """Return the exporters that answered with series."""
        return tuple(entry for entry in self.exporters if entry.present)

    @property
    def absent(self) -> tuple[ExporterPresence, ...]:
        """Return the exporters that were looked for and are not publishing."""
        return tuple(entry for entry in self.exporters if not entry.present)

    @property
    def summary(self) -> str:
        """Return the one line an operator reads about this source."""
        if not self.reachable:
            return f"{self.source} did not answer: {self.failure}"
        if not self.present:
            return (
                f"{self.source} answered and nothing this deployment recognises is "
                f"publishing into it; mapping will find no series to associate"
            )
        found = ", ".join(entry.exporter for entry in self.present)
        missing = ", ".join(entry.exporter for entry in self.absent)
        if not missing:
            return f"{self.source}: {found} publishing"
        return f"{self.source}: {found} publishing; {missing} absent"


async def verify_metrics_source(
    source: MetricsSource,
    *,
    expected: tuple[ExporterExpectation, ...] = SHIPPED_EXPORTERS,
    at: datetime,
    name: str = "metrics source",
) -> MetricsVerification:
    """Return what one real query established about ``source``.

    One query for every expectation at once rather than one per exporter: the
    cost of verification should not grow with the number of things this
    deployment knows how to use, and an operator runs this from a setup wizard
    where three round trips are three seconds.
    """
    try:
        found = await source.series(
            matchers=tuple(expectation.matcher for expectation in expected), at=at
        )
    except MetricsSourceUnreachable as unreachable:
        logger.warning("bridge.metrics_unreachable", source=name, reason=unreachable.reason)
        return MetricsVerification(
            source=name, reachable=False, checked_at=at, failure=unreachable.reason
        )
    except Exception as broken:  # noqa: BLE001 - a transport failure is still a verdict
        # Deliberately broad. Whatever the transport managed to raise, the one
        # outcome that must not follow is a verification that reports a clean
        # result because it never got an answer.
        logger.warning("bridge.metrics_unreachable", source=name, reason=str(broken))
        return MetricsVerification(
            source=name,
            reachable=False,
            checked_at=at,
            failure=f"{type(broken).__name__}: {broken}",
        )

    counts = _counts(found, expected)
    return MetricsVerification(
        source=name,
        reachable=True,
        checked_at=at,
        exporters=tuple(
            ExporterPresence(
                exporter=expectation.exporter,
                present=counts[expectation.exporter] > 0,
                series_seen=counts[expectation.exporter],
                describes=expectation.describes,
                install_hint=expectation.install_hint,
            )
            for expectation in expected
        ),
    )


def _counts(
    found: tuple[MetricSeries, ...],
    expected: tuple[ExporterExpectation, ...],
) -> dict[str, int]:
    """Return how many series each expectation accounted for, by metric name.

    A source answers with series and does not say which selector produced each
    one, so attribution is by the metric name the expectation names. That is why
    every shipped matcher is a bare metric name and not a filtered selector: a
    matcher this function could not attribute would be an exporter that verifies
    as absent while publishing, which is the worst of the four possible answers.
    """
    counts = {expectation.exporter: 0 for expectation in expected}
    by_metric: dict[str, list[str]] = {}
    for expectation in expected:
        by_metric.setdefault(expectation.matcher, []).append(expectation.exporter)
    for series in found:
        for exporter in by_metric.get(series.metric, ()):
            counts[exporter] += 1
    return counts


__all__ = [
    "SHIPPED_EXPORTERS",
    "ExporterExpectation",
    "ExporterPresence",
    "MetricsVerification",
    "verify_metrics_source",
]
