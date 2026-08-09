"""Asking for "this guest's metrics" and "this guest's logs" without knowing PromQL.

An investigation reaches for evidence about a resource. Making it compose a
Prometheus selector and a Loki stream selector first would mean the agent had to
learn two query languages before it could look at anything, and would mean two
more places where a wrong query looks like a healthy guest.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.observability_bridge import (
    MAX_SERIES_PER_RESOURCE,
    PROXMOX_ESTATE_SOURCE,
)
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE
from platform.observation.bridge.catalogue import (
    SHIPPED_LOG_SELECTORS,
    LogSelectorRule,
    ResourceObservability,
)
from platform.observation.bridge.exporters import SHIPPED_RULES
from platform.observation.bridge.mapping import EstateIndex, SeriesView, map_series
from platform.observation.bridge.ports import MetricPoint, MetricSeries
from platform.persistence.ports.estate_repository import Resource

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)
CLUSTER = "HAL9000"


def series(metric: str, value: float = 1.0, /, **labels: str) -> MetricSeries:
    """Return one series carrying a single sample."""
    return MetricSeries(
        metric=metric,
        labels=labels,
        samples=(MetricPoint(observed_at=EPOCH, value=value),),
    )


def resource(native_id: str, kind: str, display_name: str = "") -> Resource:
    """Return one estate resource."""
    return Resource(
        resource_id=f"res-{abs(hash(native_id)):032x}"[:36],
        kind=kind,
        source=PROXMOX_ESTATE_SOURCE,
        native_id=native_id,
        display_name=display_name,
    )


PVE01 = resource(f"node/{CLUSTER}/pve01", KIND_NODE, "pve01")
CT100 = resource(f"lxc/{CLUSTER}/1734000000/100", KIND_CONTAINER, "plex")
RESOURCES = (PVE01, CT100)
ESTATE = EstateIndex.of(RESOURCES)

SERIES = (
    series("pve_cpu_usage_ratio", 0.62, id="lxc/100"),
    series("pve_memory_usage_bytes", 8.0, id="lxc/100"),
    series("node_load1", 4.1, instance="pve01:9100"),
)


def observability() -> ResourceObservability:
    """Return the catalogue for the fixture estate and series."""
    return ResourceObservability.of(
        map_series(SERIES, rules=SHIPPED_RULES, estate=ESTATE),
        resources=RESOURCES,
    )


def test_a_resource_exposes_the_series_mapped_to_it() -> None:
    """SC-006: an investigation asks for a guest's metrics and gets them."""
    found = observability().metrics_for(CT100.resource_id)

    assert {entry.metric for entry in found} == {"pve_cpu_usage_ratio", "pve_memory_usage_bytes"}
    assert {entry.latest_value for entry in found} == {0.62, 8.0}
    assert all(entry.view is SeriesView.HYPERVISOR for entry in found)


def test_a_resource_with_no_mapped_series_says_so_rather_than_raising() -> None:
    """A guest nothing scrapes is a normal answer, and an empty one."""
    unknown = resource(f"lxc/{CLUSTER}/1/999", KIND_CONTAINER)

    assert observability().metrics_for(unknown.resource_id) == ()


def test_each_exposed_series_carries_the_selector_that_would_re_read_it() -> None:
    """A history read needs a selector, and the investigation should not write one."""
    found = observability().metrics_for(CT100.resource_id)

    assert all(entry.matcher.startswith(entry.metric) for entry in found)
    assert all('id="lxc/100"' in entry.matcher for entry in found)


def test_the_series_a_resource_exposes_are_bounded() -> None:
    """An investigation wants what describes a guest, not everything mentioning it."""
    many = tuple(
        series(f"pve_metric_{index}", float(index), id="lxc/100")
        for index in range(MAX_SERIES_PER_RESOURCE + 10)
    )
    catalogue = ResourceObservability.of(
        map_series(many, rules=SHIPPED_RULES, estate=ESTATE), resources=RESOURCES
    )

    assert len(catalogue.metrics_for(CT100.resource_id)) == MAX_SERIES_PER_RESOURCE


def test_a_resource_exposes_the_log_stream_selector_that_applies_to_it() -> None:
    """FR-013: "this guest's logs" resolves to a selector nobody had to write."""
    catalogue = observability()

    guest = catalogue.log_selector_for(CT100.resource_id)
    node = catalogue.log_selector_for(PVE01.resource_id)

    assert guest is not None
    assert "100" in guest.selector
    assert node is not None
    assert "pve01" in node.selector


def test_a_kind_with_no_declared_selector_returns_nothing_rather_than_a_guess() -> None:
    """A selector nobody declared would query a stream that may not exist."""
    catalogue = ResourceObservability.of(
        map_series((), rules=SHIPPED_RULES, estate=ESTATE),
        resources=RESOURCES,
        log_selectors=(),
    )

    assert catalogue.log_selector_for(CT100.resource_id) is None


def test_a_deployment_declares_its_own_log_selector() -> None:
    """Log labels are a deployment's own convention, so the rules are configuration."""
    rule = LogSelectorRule(
        rule_id="my-own",
        resource_kind=KIND_CONTAINER,
        template='{container="{name}"}',
        description="my promtail labels every container stream with its display name",
    )
    catalogue = ResourceObservability.of(
        map_series((), rules=SHIPPED_RULES, estate=ESTATE),
        resources=RESOURCES,
        log_selectors=(rule,),
    )

    selector = catalogue.log_selector_for(CT100.resource_id)

    assert selector is not None
    assert selector.selector == '{container="plex"}'
    assert selector.rule_id == "my-own"


def test_every_shipped_log_selector_explains_itself() -> None:
    """A selector nobody can read is one nobody will correct."""
    assert SHIPPED_LOG_SELECTORS
    for rule in SHIPPED_LOG_SELECTORS:
        assert rule.description
        assert rule.template
