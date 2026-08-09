"""Associating a metric series with the thing it measures, and saying what did not.

This is the whole value of the bridge. A Prometheus full of series nobody has
joined to an estate is a second place to look, which is what the operator
already had. The join is by declared label rules, and every property tested here
exists because the alternative is a mapping gap nobody can see.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.observability_bridge import (
    MAX_MAPPED_SERIES,
    MAX_UNMAPPED_REPORTED,
    PROXMOX_ESTATE_SOURCE,
)
from platform.estate.kinds import KIND_CONTAINER, KIND_DATASTORE, KIND_NODE
from platform.observation.bridge.exporters import SHIPPED_RULES
from platform.observation.bridge.mapping import (
    EstateIndex,
    LabelRule,
    MappingSchedule,
    SeriesView,
    map_series,
)
from platform.observation.bridge.ports import MetricPoint, MetricSeries
from platform.persistence.ports.estate_repository import Resource

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)
CLUSTER = "HAL9000"


def series(metric: str, /, **labels: str) -> MetricSeries:
    """Return one series carrying a single sample."""
    return MetricSeries(
        metric=metric,
        labels=labels,
        samples=(MetricPoint(observed_at=EPOCH, value=1.0),),
    )


def resource(
    native_id: str,
    kind: str,
    *,
    resource_id: str = "",
    absent_since: datetime | None = None,
) -> Resource:
    """Return one estate resource, identified the way discovery identifies it."""
    return Resource(
        resource_id=resource_id or f"res-{abs(hash(native_id)):032x}"[:36],
        kind=kind,
        source=PROXMOX_ESTATE_SOURCE,
        native_id=native_id,
        absent_since=absent_since,
    )


PVE01 = resource(f"node/{CLUSTER}/pve01", KIND_NODE)
CT100 = resource(f"lxc/{CLUSTER}/1734000000/100", KIND_CONTAINER)
LOCAL_LVM = resource(f"datastore/{CLUSTER}/pve02/local-lvm", KIND_DATASTORE)
ESTATE = EstateIndex.of((PVE01, CT100, LOCAL_LVM))


def test_a_guest_series_lands_on_the_guest_resource() -> None:
    """SC-002: series map to the resources they describe, through the shipped rules."""
    mapping = map_series(
        (series("pve_guest_info", id="lxc/100", node="pve01"),),
        rules=SHIPPED_RULES,
        estate=ESTATE,
    )

    assert mapping.unmapped == ()
    assert [entry.resource_id for entry in mapping.mapped] == [CT100.resource_id]
    assert mapping.mapped[0].view is SeriesView.HYPERVISOR


def test_a_node_exporter_series_lands_on_the_node_resource() -> None:
    """Node exporter metrics map to Proxmox node resources."""
    mapping = map_series(
        (series("node_filesystem_avail_bytes", instance="pve01:9100", job="node"),),
        rules=SHIPPED_RULES,
        estate=ESTATE,
    )

    assert [entry.resource_id for entry in mapping.mapped] == [PVE01.resource_id]
    assert mapping.mapped[0].view is SeriesView.NODE


def test_a_datastore_series_lands_on_the_datastore_of_that_node() -> None:
    """A share visible from two nodes is two resources, and the label says which."""
    mapping = map_series(
        (series("pve_disk_usage_bytes", id="storage/pve02/local-lvm"),),
        rules=SHIPPED_RULES,
        estate=ESTATE,
    )

    assert [entry.resource_id for entry in mapping.mapped] == [LOCAL_LVM.resource_id]


def test_a_guests_own_exporter_is_distinguishable_from_the_hypervisors_view() -> None:
    """A guest scraping itself and the cluster describing it are two different views."""
    mapping = map_series(
        (
            series("pve_cpu_usage_ratio", id="lxc/100"),
            series("node_load1", instance="plex:9100", vmid="100", type="lxc"),
        ),
        rules=SHIPPED_RULES,
        estate=ESTATE,
    )

    views = {entry.view for entry in mapping.mapped}
    assert views == {SeriesView.HYPERVISOR, SeriesView.GUEST}
    assert {entry.resource_id for entry in mapping.mapped} == {CT100.resource_id}


def test_unmapped_series_are_reported_with_their_labels() -> None:
    """SC-002: a mapping gap is visible rather than silent."""
    stray = series("mystery_metric_total", app="something", instance="10.0.0.9:9000")

    mapping = map_series((stray,), rules=SHIPPED_RULES, estate=ESTATE)

    assert mapping.mapped == ()
    assert len(mapping.unmapped) == 1
    assert mapping.unmapped[0].metric == "mystery_metric_total"
    assert mapping.unmapped[0].labels == stray.labels
    assert mapping.unmapped[0].reason


def test_a_series_naming_a_resource_the_estate_does_not_hold_is_reported_not_invented() -> None:
    """Nothing here creates a resource. An unknown guest is a mapping gap, not an estate write."""
    mapping = map_series(
        (series("pve_guest_info", id="lxc/999"),), rules=SHIPPED_RULES, estate=ESTATE
    )

    assert mapping.mapped == ()
    assert "estate" in mapping.unmapped[0].reason
    assert mapping.resource_ids <= {PVE01.resource_id, CT100.resource_id, LOCAL_LVM.resource_id}


def test_a_destroyed_guest_maps_to_the_absent_resource_rather_than_a_new_one() -> None:
    """T-010: metrics outlive a guest, and the history belongs to the guest that had it."""
    destroyed = resource(
        f"lxc/{CLUSTER}/1733000000/140", KIND_CONTAINER, absent_since=EPOCH - timedelta(days=1)
    )
    estate = EstateIndex.of((PVE01, destroyed))

    mapping = map_series(
        (series("pve_guest_info", id="lxc/140"),), rules=SHIPPED_RULES, estate=estate
    )

    assert [entry.resource_id for entry in mapping.mapped] == [destroyed.resource_id]
    assert mapping.resource_ids == {destroyed.resource_id}


def test_a_reused_vmid_prefers_the_guest_that_still_exists() -> None:
    """Two resources, one live: the series is about the one that is running."""
    old = resource(f"lxc/{CLUSTER}/1733000000/100", KIND_CONTAINER, absent_since=EPOCH)
    estate = EstateIndex.of((old, CT100))

    mapping = map_series(
        (series("pve_guest_info", id="lxc/100"),), rules=SHIPPED_RULES, estate=estate
    )

    assert [entry.resource_id for entry in mapping.mapped] == [CT100.resource_id]


def test_two_live_candidates_are_reported_rather_than_guessed() -> None:
    """An ambiguous join is a mapping gap. Picking one would be a silent wrong answer."""
    other_cluster = resource("lxc/OTHER/1733000000/100", KIND_CONTAINER)
    estate = EstateIndex.of((CT100, other_cluster))

    mapping = map_series(
        (series("pve_guest_info", id="lxc/100"),), rules=SHIPPED_RULES, estate=estate
    )

    assert mapping.mapped == ()
    assert "ambiguous" in mapping.unmapped[0].reason


def test_mapping_is_bounded_and_says_so_rather_than_enumerating_everything() -> None:
    """NFR-001: high cardinality is truncated with a stated bound, never silently."""
    many = tuple(
        series("pve_guest_info", id="lxc/100", replica=str(index))
        for index in range(MAX_MAPPED_SERIES + 50)
    )

    mapping = map_series(many, rules=SHIPPED_RULES, estate=ESTATE)

    assert len(mapping.mapped) == MAX_MAPPED_SERIES
    assert mapping.truncated
    assert mapping.considered == MAX_MAPPED_SERIES


def test_unmapped_reporting_is_bounded_and_keeps_the_total() -> None:
    """A sample plus a count. Every stray series would be a report nobody reads."""
    many = tuple(
        series("mystery_metric_total", replica=str(index))
        for index in range(MAX_UNMAPPED_REPORTED + 25)
    )

    mapping = map_series(many, rules=SHIPPED_RULES, estate=ESTATE)

    assert len(mapping.unmapped) == MAX_UNMAPPED_REPORTED
    assert mapping.unmapped_total == MAX_UNMAPPED_REPORTED + 25


def test_a_deployment_declares_its_own_rule_without_new_code() -> None:
    """FR-002: label rules are configuration, and a deployment supplies its own."""
    rule = LabelRule(
        rule_id="my-own",
        metric_prefixes=("app_",),
        resource_kind=KIND_CONTAINER,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="lxc/*/*/{ct}",
        view=SeriesView.GUEST,
        description="my application exporter tags every series with its container id",
    )

    mapping = map_series((series("app_requests_total", ct="100"),), rules=(rule,), estate=ESTATE)

    assert [entry.resource_id for entry in mapping.mapped] == [CT100.resource_id]
    assert mapping.mapped[0].rule_id == "my-own"


def test_a_rule_names_the_labels_it_needs_so_a_missing_one_is_a_reason() -> None:
    """A rule whose labels are absent explains itself instead of quietly not matching."""
    rule = LabelRule(
        rule_id="needs-vmid",
        metric_prefixes=("app_",),
        resource_kind=KIND_CONTAINER,
        integration=PROXMOX_ESTATE_SOURCE,
        native_template="lxc/*/*/{ct}",
    )
    assert rule.required_labels == ("ct",)

    mapping = map_series((series("app_requests_total", other="1"),), rules=(rule,), estate=ESTATE)

    assert "ct" in mapping.unmapped[0].reason


def test_mapping_runs_on_a_schedule_rather_than_per_query() -> None:
    """T-009: the join changes when the estate changes, not when a detector evaluates."""
    schedule = MappingSchedule()

    assert schedule.is_due(last_mapped_at=None, now=EPOCH)
    assert not schedule.is_due(last_mapped_at=EPOCH, now=EPOCH + timedelta(seconds=30))
    assert schedule.is_due(
        last_mapped_at=EPOCH, now=EPOCH + timedelta(seconds=schedule.interval_seconds)
    )


def test_every_shipped_rule_explains_itself() -> None:
    """A rule nobody can read is a rule nobody will override when it is wrong."""
    assert SHIPPED_RULES
    identifiers = [rule.rule_id for rule in SHIPPED_RULES]
    assert len(identifiers) == len(set(identifiers))
    for rule in SHIPPED_RULES:
        assert rule.description
        assert rule.metric_prefixes
        assert rule.native_template
