"""The four things a Proxmox homelab specifically needs from the bridge.

Each of these comes from a real cluster rather than from a category. Its
observability stack runs inside the estate it observes and produced no alert at
all during that estate's only total outage; it already carries four alert-rule
files nobody here wrote; and the three readings that explained the outage are
published by nothing the Proxmox API can answer.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.observability_bridge import (
    BRIDGE_SOURCE,
    EXPORTER_TEXTFILE,
    PRECEDENCE_SOURCE_BRIDGE,
    PROXMOX_ESTATE_SOURCE,
)
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE
from platform.observation.bridge.exporters import SHIPPED_RULES
from platform.observation.bridge.hosting import (
    OBSERVABILITY_COMPONENTS,
    detect_self_hosting,
)
from platform.observation.bridge.mapping import EstateIndex, map_series
from platform.observation.bridge.ports import AlertRule, MetricPoint, MetricSeries
from platform.observation.bridge.precedence import PrecedenceRule, SignalPrecedence
from platform.observation.bridge.provenance import provenance_change
from platform.observation.bridge.rules import CoverageClaim, overlaps
from platform.observation.bridge.supplementary import (
    TEXTFILE_METRICS,
    published_readings,
)
from platform.observation.detectors.model import (
    Comparison,
    Condition,
    ConditionKind,
    DetectorDeclaration,
)
from platform.observation.sources.port import PollBudget, SignalDeclaration, SignalPage
from platform.persistence.ports import Resource

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 8, 9, 4, 0, tzinfo=UTC)
CLUSTER = "HAL9000"

PVE01 = Resource(
    resource_id="res-pve01",
    kind=KIND_NODE,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"node/{CLUSTER}/pve01",
    display_name="pve01",
)
CT137 = Resource(
    resource_id="res-ct137",
    kind=KIND_CONTAINER,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"lxc/{CLUSTER}/1730000000/137",
    display_name="prometheus",
    parent_id=PVE01.resource_id,
)
CT136 = Resource(
    resource_id="res-ct136",
    kind=KIND_CONTAINER,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"lxc/{CLUSTER}/1730000001/136",
    display_name="alertmanager",
    parent_id=PVE01.resource_id,
)
CT133 = Resource(
    resource_id="res-ct133",
    kind=KIND_CONTAINER,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"lxc/{CLUSTER}/1730000002/133",
    display_name="grafana",
    parent_id=PVE01.resource_id,
)
ESTATE = (PVE01, CT137, CT136, CT133)


def series(metric: str, value: float, /, **labels: str) -> MetricSeries:
    """Return one series carrying a single sample."""
    return MetricSeries(
        metric=metric,
        labels=labels,
        samples=(MetricPoint(observed_at=EPOCH, value=value),),
    )


def datastore_detector() -> DetectorDeclaration:
    """Return a shipped detector that covers a condition an operator may already alert on."""
    return DetectorDeclaration(
        detector_id="datastore-nearly-full",
        name="Datastore nearly full",
        description="a datastore above 90% stops accepting backups before it stops guests",
        resource_kinds=(),
        signal="datastore.used.ratio",
        condition=Condition(
            kind=ConditionKind.THRESHOLD,
            comparison=Comparison.ABOVE,
            fire_value=0.9,
            clear_value=0.85,
        ),
        for_seconds=300,
        recovery_seconds=300,
    )


# --- FR-019a: the operator's own rules ---------------------------------------------


def test_a_rule_the_operator_already_wrote_is_reported_rather_than_duplicated() -> None:
    """Both definitions are shown, so an operator can see what would double-alert."""
    existing = AlertRule(
        name="ProxmoxStorageNearlyFull",
        expression="pve_disk_usage_bytes / pve_disk_size_bytes > 0.9",
        group="storage",
        source_file="cluster-alerts.yml",
        for_seconds=600,
    )
    claim = CoverageClaim(
        detector_id="datastore-nearly-full",
        signal="datastore.used.ratio",
        metrics=("pve_disk_usage_bytes",),
    )

    found = overlaps((datastore_detector(),), (existing,), claims=(claim,))

    assert len(found) == 1
    assert found[0].rule_name == "ProxmoxStorageNearlyFull"
    assert found[0].rule_source_file == "cluster-alerts.yml"
    assert found[0].rule_expression == existing.expression
    assert "a datastore above 90%" in found[0].detector_description
    assert found[0].summary


def test_an_overlap_resolves_by_the_declared_precedence() -> None:
    """FR-006 applies here too: exactly one of the two produces signals."""
    existing = AlertRule(name="X", expression="pve_disk_usage_bytes > 1", source_file="a.yml")
    claim = CoverageClaim(
        detector_id="datastore-nearly-full",
        signal="datastore.used.ratio",
        metrics=("pve_disk_usage_bytes",),
    )
    precedence = SignalPrecedence(
        rules=(
            PrecedenceRule(
                signal="datastore.used.ratio",
                winner=PRECEDENCE_SOURCE_BRIDGE,
                reason="the operator's rule has been tuned for a year and ours has not",
            ),
        )
    )

    found = overlaps((datastore_detector(),), (existing,), claims=(claim,), precedence=precedence)

    assert found[0].winner == PRECEDENCE_SOURCE_BRIDGE
    assert found[0].reason


def test_a_rule_about_something_else_is_not_reported_as_a_duplicate() -> None:
    """A report full of false overlaps is a report an operator stops reading."""
    unrelated = AlertRule(name="NodeDown", expression="up == 0", source_file="a.yml")
    claim = CoverageClaim(
        detector_id="datastore-nearly-full",
        signal="datastore.used.ratio",
        metrics=("pve_disk_usage_bytes",),
    )

    assert overlaps((datastore_detector(),), (unrelated,), claims=(claim,)) == ()


# --- FR-019b: the stack inside the estate ------------------------------------------


def test_a_stack_hosted_inside_the_estate_it_observes_is_detected_and_named() -> None:
    """The reference cluster's whole stack is on one node, and nothing alerted."""
    report = detect_self_hosting(
        {"prometheus": "prometheus:9090", "alertmanager": "alertmanager:9093"},
        resources=ESTATE,
    )

    assert report.self_hosted
    assert {entry.resource_id for entry in report.components} == {
        CT137.resource_id,
        CT136.resource_id,
    }
    assert report.shared_parents == (PVE01.resource_id,)
    assert "pve01" in report.summary or PVE01.resource_id in report.summary


def test_a_stack_outside_the_estate_is_not_reported_as_hosted_inside_it() -> None:
    """A watcher on other hardware is the correct arrangement and raises nothing."""
    report = detect_self_hosting({"prometheus": "monitoring.example.net:9090"}, resources=ESTATE)

    assert not report.self_hosted
    assert report.components == ()


def test_every_declared_component_is_one_an_operator_would_recognise() -> None:
    """The list is what a homelab actually runs, not a taxonomy."""
    assert "prometheus" in OBSERVABILITY_COMPONENTS
    assert "alertmanager" in OBSERVABILITY_COMPONENTS
    assert "loki" in OBSERVABILITY_COMPONENTS


# --- FR-019c and FR-019d: the readings nothing else publishes ----------------------


def test_the_textfile_collectors_readings_reach_the_estate_as_a_published_mapping() -> None:
    """FR-019c: failed units, bridges and thin-pool metadata, in the shape 044 reads."""
    mapping = map_series(
        (
            series(
                "node_systemd_unit_state",
                1.0,
                instance="pve01:9100",
                name="corosync-qdevice.service",
                state="failed",
            ),
            series(
                "node_systemd_unit_state",
                0.0,
                instance="pve01:9100",
                name="pveproxy.service",
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
        rules=SHIPPED_RULES,
        estate=EstateIndex.of(ESTATE),
    )

    published = published_readings(mapping, resource_id=PVE01.resource_id)

    assert published["failed_units"] == ("corosync-qdevice.service",)
    assert published["bridges"] == {"vmbr0": False}
    assert published["thin_pool_metadata"] == {"data-pool/data-pool": 31.98}


def test_a_node_publishing_none_of_them_produces_no_keys_rather_than_empty_ones() -> None:
    """ "Nothing is failing" and "nothing is looking" must not produce the same mapping."""
    mapping = map_series(
        (series("node_load1", 1.0, instance="pve01:9100"),),
        rules=SHIPPED_RULES,
        estate=EstateIndex.of(ESTATE),
    )

    published = published_readings(mapping, resource_id=PVE01.resource_id)

    assert published == {}


def test_the_textfile_collector_is_a_declared_publication_path() -> None:
    """FR-019d: reinventing the mechanism beside the operator's would give a node two."""
    assert TEXTFILE_METRICS
    for declared in TEXTFILE_METRICS:
        assert declared.metric.startswith("node_")
        assert declared.publishes
        assert declared.how
    assert any(EXPORTER_TEXTFILE in declared.how for declared in TEXTFILE_METRICS)


# --- FR-023: provenance ------------------------------------------------------------


class _Polled:
    """The deployment's own source for one signal."""

    @property
    def declaration(self) -> SignalDeclaration:
        """Return a declaration for the polled signal."""
        return SignalDeclaration(source=PROXMOX_ESTATE_SOURCE, signals=("datastore.used.ratio",))

    async def read(
        self, *, resource_ids: tuple[str, ...], at: datetime, budget: PollBudget
    ) -> SignalPage:
        """Return nothing; this source exists to be compared against."""
        del resource_ids, at, budget
        return SignalPage()


class _Bridged:
    """A bridge source covering the same signal and one more."""

    @property
    def declaration(self) -> SignalDeclaration:
        """Return a declaration naming the duplicated signal and a new one."""
        return SignalDeclaration(
            source=BRIDGE_SOURCE, signals=("datastore.used.ratio", "node.filesystem.used.ratio")
        )

    async def read(
        self, *, resource_ids: tuple[str, ...], at: datetime, budget: PollBudget
    ) -> SignalPage:
        """Return nothing; this source exists to be compared against."""
        del resource_ids, at, budget
        return SignalPage()


def test_enabling_a_source_adds_signals_and_takes_none_over_by_default() -> None:
    """T-029: enabling a source must not silently change which detectors fire."""
    report = provenance_change(
        before=(_Polled(),), after=(_Polled(), _Bridged()), precedence=SignalPrecedence()
    )

    assert report.added == ("node.filesystem.used.ratio",)
    assert report.taken_over == ()
    assert report.visible
    assert "datastore.used.ratio" in report.summary


def test_a_declared_takeover_is_reported_as_one() -> None:
    """The change is allowed; being unable to see it is what is not."""
    precedence = SignalPrecedence(
        rules=(
            PrecedenceRule(
                signal="datastore.used.ratio",
                winner=PRECEDENCE_SOURCE_BRIDGE,
                reason="prometheus has a year of this and we have twenty minutes",
            ),
        )
    )

    report = provenance_change(
        before=(_Polled(),), after=(_Polled(), _Bridged()), precedence=precedence
    )

    assert report.taken_over == ("datastore.used.ratio",)
    assert report.detectors_affected((datastore_detector(),)) == ("datastore-nearly-full",)
