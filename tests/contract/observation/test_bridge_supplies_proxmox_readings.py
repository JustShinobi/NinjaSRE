"""Contract: the readings the hypervisor API cannot answer arrive through the bridge.

Feature 044 shipped the shape and nothing to fill it, deliberately — an estate
that answered "no failed units" for a node nobody is watching is the exact
failure that requirement was written to prevent, and it would have been
invisible until this feature landed. This is the test that it has.

It crosses a tier boundary on purpose: the bridge produces a plain mapping and
the integration reads one, and the only place the two can be shown to agree is a
test that may import both.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.observability_bridge import PROXMOX_ESTATE_SOURCE
from integrations.proxmox.supplementary import (
    SUPPLEMENTARY_PUBLISHER,
    supplementary_readings,
)
from platform.estate.kinds import KIND_NODE
from platform.observation.bridge.exporters import SHIPPED_RULES
from platform.observation.bridge.mapping import EstateIndex, map_series
from platform.observation.bridge.ports import MetricPoint, MetricSeries
from platform.observation.bridge.supplementary import TEXTFILE_METRICS, published_readings
from platform.persistence.ports import ResourceHealth
from platform.persistence.ports.estate_repository import Resource

pytestmark = pytest.mark.contract

EPOCH = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)
CLUSTER = "HAL9000"

PVE01 = Resource(
    resource_id="res-pve01",
    kind=KIND_NODE,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"node/{CLUSTER}/pve01",
    display_name="pve01",
)
ESTATE = EstateIndex.of((PVE01,))


def series(metric: str, value: float, /, **labels: str) -> MetricSeries:
    """Return one series carrying a single sample."""
    return MetricSeries(
        metric=metric,
        labels=labels,
        samples=(MetricPoint(observed_at=EPOCH, value=value),),
    )


def published(*answers: MetricSeries) -> dict[str, object]:
    """Return what the bridge publishes for pve01 given ``answers``."""
    return published_readings(
        map_series(answers, rules=SHIPPED_RULES, estate=ESTATE),
        resource_id=PVE01.resource_id,
    )


def test_the_bridge_fills_the_shape_the_hypervisor_integration_has_been_holding() -> None:
    """The reference cluster's own state: a failed qdevice, a bridge down, metadata at 32%."""
    readings = supplementary_readings(
        node="pve01",
        published=published(
            series(
                "node_systemd_unit_state",
                1.0,
                instance="pve01:9100",
                name="corosync-qdevice.service",
                state="failed",
            ),
            series("node_bridge_up", 0.0, instance="pve01:9100", bridge="vmbr0"),
            series(
                "node_lvm_thinpool_metadata_percent",
                31.98,
                instance="pve01:9100",
                vg="data-pool",
                pool="data-pool",
            ),
        ),
    )

    assert readings.any_available
    assert readings.failed_units.require() == ("corosync-qdevice.service",)
    assert readings.bridges.require() == {"vmbr0": False}
    assert readings.health_verdict() is ResourceHealth.DEGRADED
    assert "corosync-qdevice" in readings.signals()["failed_units"]


def test_a_node_publishing_nothing_still_reports_unavailable_rather_than_healthy() -> None:
    """The property feature 044 shipped the module for, now that something can fill it."""
    readings = supplementary_readings(node="pve01", published=published())

    assert not readings.any_available
    assert readings.health_verdict() is ResourceHealth.UNKNOWN
    assert SUPPLEMENTARY_PUBLISHER in readings.summary()
    assert readings.signals()["failed_units"] == "unavailable"


def test_a_node_publishing_only_some_of_them_is_honest_about_the_rest() -> None:
    """Partial publication is the ordinary case while an operator is setting this up."""
    readings = supplementary_readings(
        node="pve01",
        published=published(
            series(
                "node_systemd_unit_state",
                0.0,
                instance="pve01:9100",
                name="pveproxy.service",
                state="failed",
            )
        ),
    )

    assert readings.any_available
    assert readings.failed_units.require() == ()
    assert not readings.bridges.available
    assert readings.signals()["thin_pool_metadata_watched"] == "no"


def test_the_publication_path_the_bridge_documents_is_the_one_the_estate_names() -> None:
    """FR-019d: one mechanism on the node, not two — and both halves say so."""
    assert "textfile" in SUPPLEMENTARY_PUBLISHER
    assert any("textfile" in declared.how for declared in TEXTFILE_METRICS)
