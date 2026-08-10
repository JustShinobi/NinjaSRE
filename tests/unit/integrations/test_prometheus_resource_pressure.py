"""Asking Prometheus about a guest's pressure, from the host and not from inside.

This is the one place in the feature where the signal map stops being a
description and becomes a query. A container shares the host's kernel, so the
counters visible inside it are the host's seen through a namespace that was
never built to publish them — and a query aimed there returns a number that is
wrong, plausible, and shaped exactly like the right one.

So the assertions are in two directions and both are load-bearing:

**The selector contains the guest's own identifier.** Without it the query
matches every guest on the cluster, and the answer is the cluster's memory
rather than this container's.

**The selector contains no in-guest metric name.** A query built from
``node_memory_*`` or ``container_memory_*`` is reading a collector inside the
guest, and there is no assertion about the *result* that would catch it — both
shapes come back as a series with a number in it.
"""

from __future__ import annotations

import pytest

from config.constants.signals import SIGNAL_KEY_INSTANCE, SIGNAL_KEY_VMID
from integrations.prometheus.pressure import (
    HOST_SIDE_SERIES,
    IN_GUEST_SERIES,
    PressureQuery,
    pressure_queries,
    pressure_source,
)
from platform.estate.kinds import KIND_CONTAINER, KIND_DATASTORE, KIND_NODE, KIND_VIRTUAL_MACHINE

pytestmark = pytest.mark.unit


def queries_for(kind: str, *, vmid: int = 0, address: str = "") -> tuple[PressureQuery, ...]:
    """Return the queries the map produces for one resource shape."""
    source = pressure_source(kind, vmid=vmid, address=address)
    assert source is not None, f"{kind}: the map answered nothing about pressure"
    return pressure_queries(source, kind=kind)


class TestAContainersPressureQuery:
    def test_every_selector_names_the_guests_own_identifier(self) -> None:
        for query in queries_for(KIND_CONTAINER, vmid=100):
            assert 'id="lxc/100"' in query.promql, query.promql

    def test_no_selector_names_a_metric_collected_inside_the_guest(self) -> None:
        """Acceptance 2's negative half, and the half a result assertion misses."""
        promql = " ".join(query.promql for query in queries_for(KIND_CONTAINER, vmid=100))

        for forbidden in IN_GUEST_SERIES:
            assert forbidden not in promql, (
                f"the pressure query reads {forbidden}, which is a collector inside the "
                f"guest — the number it returns is the host's, misattributed"
            )

    def test_every_selector_is_a_host_side_series(self) -> None:
        for query in queries_for(KIND_CONTAINER, vmid=100):
            assert any(series in query.promql for series in HOST_SIDE_SERIES), query.promql

    def test_the_queries_cover_memory_cpu_and_disk(self) -> None:
        named = {query.name for query in queries_for(KIND_CONTAINER, vmid=100)}

        assert {"memory", "cpu", "disk"} <= named

    def test_each_query_says_what_it_is_for(self) -> None:
        for query in queries_for(KIND_CONTAINER, vmid=100):
            assert query.question.strip(), f"{query.name}: a query nobody can interpret"


class TestTheOtherKinds:
    def test_a_virtual_machine_is_asked_about_the_same_way(self) -> None:
        for query in queries_for(KIND_VIRTUAL_MACHINE, vmid=201):
            assert 'id="qemu/201"' in query.promql, query.promql

    def test_a_node_is_asked_about_by_its_scrape_target(self) -> None:
        source = pressure_source(KIND_NODE, address="10.20.10.11")

        assert source is not None
        assert source.keyed_by == SIGNAL_KEY_INSTANCE
        for query in pressure_queries(source, kind=KIND_NODE):
            assert "10.20.10.11" in query.promql, query.promql

    def test_a_kind_with_no_pressure_series_answers_nothing_rather_than_guessing(self) -> None:
        assert pressure_source(KIND_DATASTORE) is None

    def test_a_guest_with_no_identifier_answers_nothing_rather_than_matching_everything(
        self,
    ) -> None:
        """An unkeyed selector matches every guest, and the answer looks like a number."""
        assert pressure_source(KIND_CONTAINER, vmid=0) is None


class TestTheMapIsWhatDecides:
    def test_the_selector_key_comes_from_the_maps_entry_rather_than_from_the_kind(self) -> None:
        """The ablation this feature is measured by: turn the map off and the
        query has nothing to filter on."""
        source = pressure_source(KIND_CONTAINER, vmid=100)

        assert source is not None
        assert source.keyed_by == SIGNAL_KEY_VMID
        assert source.key == "100"
        assert source.integration == "prometheus"

    def test_the_maps_reasoning_travels_with_the_queries(self) -> None:
        source = pressure_source(KIND_CONTAINER, vmid=100)

        assert source is not None
        assert "kernel" in source.detail
