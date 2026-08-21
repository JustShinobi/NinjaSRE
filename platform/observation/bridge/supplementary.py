"""The three readings that explained an outage and that no REST API can answer.

A Proxmox node's failed ``systemd`` units, whether its configured bridges exist
and are up, and an LVM thin pool's *metadata* percentage. On the reference
cluster all three were plain at the node level and invisible at the API level
during the worst outage it has had, and ``integrations/proxmox/supplementary.py``
already has the shape that reads them — it has simply had nothing to read,
because filling it is this feature's job.

**They arrive as metrics, because the alternative is a shell.** All three are one
SSH command away, and a hypervisor integration that could run arbitrary commands
on both nodes would hold the single largest authority in this system — larger
than every remediation capability combined, because it would subsume them.
Article IV forbids the agent holding an SSH identity at all.

**The textfile collector is the publication path, and it is the operator's own.**
A node exporter already serves any ``.prom`` file in a directory, and the
reference cluster's own operators had already reached for exactly that mechanism
to close a different visibility gap. Building a second agent beside theirs would
give one node two things to keep running; writing three files into the directory
they already have gives it none.

**An absent reading produces no key.** Not an empty tuple, not a zero. The
integration turns a missing key into "unavailable, and here is what would publish
it", and turns a present-but-empty one into "nothing is failing" — which are
opposite claims, and only one of them can be made about a node nobody is
watching.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from config.constants.observability_bridge import EXPORTER_TEXTFILE
from platform.observation.bridge.mapping import MappedSeries, SeriesMapping, SeriesView
from platform.observation.bridge.ports import MetricSeries

#: The metric a node exporter publishes for every ``systemd`` unit's state. Part
#: of the standard collector, so a node with the systemd collector enabled needs
#: no textfile for this one.
METRIC_UNIT_STATE: Final = "node_systemd_unit_state"

#: The label carrying the unit's name, and the one carrying which state the
#: series is about — the exporter publishes one series per state per unit and
#: sets exactly one of them to 1.
UNIT_NAME_LABEL: Final = "name"
UNIT_STATE_LABEL: Final = "state"
UNIT_STATE_FAILED: Final = "failed"

#: What a textfile collector publishes for a bridge: 1 when the bridge exists and
#: is up, 0 when it is configured and is not. A bridge that is *absent* publishes
#: no series at all, which is why the estate's own view of what should exist is
#: what makes a missing series meaningful.
METRIC_BRIDGE_UP: Final = "node_bridge_up"
BRIDGE_LABEL: Final = "bridge"

#: What a textfile collector publishes for a thin pool's metadata usage. The
#: reading that stops writes while the data percentage still looks comfortable —
#: on the reference cluster, 31.98% metadata against 72.38% data.
METRIC_THIN_POOL_METADATA: Final = "node_lvm_thinpool_metadata_percent"
VOLUME_GROUP_LABEL: Final = "vg"
POOL_LABEL: Final = "pool"


@dataclass(frozen=True, slots=True)
class TextfileMetric:
    """One reading a node publishes about itself through the textfile collector."""

    metric: str
    #: What it says, in the operator's terms.
    publishes: str
    #: How to publish it, concretely enough to act on.
    how: str


#: What a node has to publish for the three readings to arrive. Declared rather
#: than documented in prose, so that the verification report, the setup guidance
#: and the code that parses them cannot come to disagree about the metric names.
TEXTFILE_METRICS: Final[tuple[TextfileMetric, ...]] = (
    TextfileMetric(
        metric=METRIC_UNIT_STATE,
        publishes="every systemd unit's state, so a failed one is visible",
        how=(
            "enable the node exporter's systemd collector (--collector.systemd); no "
            f"textfile is needed for this one, though a {EXPORTER_TEXTFILE} works too"
        ),
    ),
    TextfileMetric(
        metric=METRIC_BRIDGE_UP,
        publishes="whether each configured bridge exists and is up",
        how=(
            f"write it from a timer into the {EXPORTER_TEXTFILE} directory: one line per "
            "bridge in /etc/network/interfaces, 1 when `ip link show` finds it up"
        ),
    ),
    TextfileMetric(
        metric=METRIC_THIN_POOL_METADATA,
        publishes="each LVM thin pool's metadata usage, which stops writes on its own",
        how=(
            f"write it from a timer into the {EXPORTER_TEXTFILE} directory, from "
            "`lvs --noheadings -o vg_name,lv_name,metadata_percent`"
        ),
    ),
)


def published_readings(
    mapping: SeriesMapping,
    *,
    resource_id: str,
) -> dict[str, Any]:
    """Return what ``resource_id``'s node is publishing, in the shape the estate reads.

    Keys are present only for readings something is actually publishing. That is
    the whole contract with ``integrations/proxmox/supplementary.py``: a missing
    key becomes "unavailable, and here is what would publish it", and an empty
    value becomes "nothing is failing". Producing an empty value for a node
    nobody watches would be reporting the absence of a monitor as the absence of
    a problem.
    """
    mine = tuple(entry for entry in mapping.mapped if entry.resource_id == resource_id)
    published: dict[str, Any] = {}

    units = _failed_units(mine)
    if units is not None:
        published["failed_units"] = units

    bridges = _bridges(mine)
    if bridges is not None:
        published["bridges"] = bridges

    pools = _thin_pool_metadata(mine)
    if pools is not None:
        published["thin_pool_metadata"] = pools

    return published


def published_for_series(series: tuple[MetricSeries, ...]) -> dict[str, Any]:
    """Return what ``series`` publishes, for a caller that already knows the node.

    Same three-key contract as ``published_readings``, without the estate
    mapping pass — for an on-demand tool that named the node itself rather
    than a periodic sweep resolving an unlabelled corpus to a resource.
    """
    mapped = tuple(
        MappedSeries(
            series=entry, resource_id="", resource_kind="", rule_id="", view=SeriesView.NODE
        )
        for entry in series
    )
    return published_readings(SeriesMapping(mapped=mapped), resource_id="")


def _failed_units(series: tuple[MappedSeries, ...]) -> tuple[str, ...] | None:
    """Return the failed unit names, or ``None`` when nothing publishes unit states."""
    seen = [entry for entry in series if entry.metric == METRIC_UNIT_STATE]
    if not seen:
        return None
    failed = {
        entry.labels.get(UNIT_NAME_LABEL, "")
        for entry in seen
        if entry.labels.get(UNIT_STATE_LABEL) == UNIT_STATE_FAILED and _value(entry) == 1.0
    }
    return tuple(sorted(name for name in failed if name))


def _bridges(series: tuple[MappedSeries, ...]) -> Mapping[str, bool] | None:
    """Return each bridge and whether it is up, or ``None`` when nothing publishes them."""
    seen = [entry for entry in series if entry.metric == METRIC_BRIDGE_UP]
    if not seen:
        return None
    return {
        entry.labels[BRIDGE_LABEL]: _value(entry) == 1.0
        for entry in seen
        if entry.labels.get(BRIDGE_LABEL)
    }


def _thin_pool_metadata(series: tuple[MappedSeries, ...]) -> Mapping[str, float] | None:
    """Return each thin pool's metadata percentage, or ``None`` when none is published."""
    seen = [entry for entry in series if entry.metric == METRIC_THIN_POOL_METADATA]
    if not seen:
        return None
    found: dict[str, float] = {}
    for entry in seen:
        group = entry.labels.get(VOLUME_GROUP_LABEL, "")
        pool = entry.labels.get(POOL_LABEL, "")
        if not pool:
            continue
        value = _value(entry)
        if value is not None:
            found[f"{group}/{pool}" if group else pool] = value
    return found


def _value(entry: MappedSeries) -> float | None:
    """Return the newest value of one mapped series, or ``None`` when it has none."""
    newest = entry.series.newest
    return newest.value if newest is not None else None


__all__ = [
    "BRIDGE_LABEL",
    "METRIC_BRIDGE_UP",
    "METRIC_THIN_POOL_METADATA",
    "METRIC_UNIT_STATE",
    "POOL_LABEL",
    "TEXTFILE_METRICS",
    "UNIT_NAME_LABEL",
    "UNIT_STATE_FAILED",
    "UNIT_STATE_LABEL",
    "VOLUME_GROUP_LABEL",
    "TextfileMetric",
    "published_for_series",
    "published_readings",
]
