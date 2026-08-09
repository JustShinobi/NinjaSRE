"""Contract: the ten things the observability bridge claims, each proven once.

One test per success criterion, against real collaborators — the real
configuration schema, the real incident lifecycle, the real evaluation tick, the
real signal store — because every one of these claims is about a join between
two parts of the system and a test against a stand-in would prove the stand-in.

The last three are the ones that matter most on a homelab: a deployment with no
observability stack at all must pass everything, enabling a source must not
silently change what fires, and nothing this feature adds may become a
dependency of the features it sits beside.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from config.constants.notifications import SEVERITY_CRITICAL
from config.constants.observability_bridge import (
    BRIDGE_SOURCE,
    EXPORTER_NODE,
    EXPORTER_PROXMOX,
    PRECEDENCE_SOURCE_BRIDGE,
    PROXMOX_ESTATE_SOURCE,
)
from platform.config_service.schema.policies import (
    ObservabilityBridgeSettings,
    ObservationPolicySettings,
    SignalPrecedenceSettings,
)
from platform.estate.kinds import KIND_CONTAINER, KIND_DATASTORE, KIND_NODE
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.notifications.models import Severity
from platform.observation.bridge import config as bridge_config
from platform.observation.bridge.alerts import (
    ALERT_STATUS_RESOLVED,
    IncomingAlert,
    apply_resolution,
    raise_for_incoming_alert,
    resolution_for,
)
from platform.observation.bridge.availability import (
    SourceOutage,
    failures_for_outage,
    outage_for,
    raise_for_outage,
)
from platform.observation.bridge.catalogue import ResourceObservability
from platform.observation.bridge.dashboards import DashboardMapping, dashboard_link
from platform.observation.bridge.errors import MetricsSourceUnreachable
from platform.observation.bridge.exporters import SHIPPED_RULES
from platform.observation.bridge.history import MetricsHistorySource
from platform.observation.bridge.logs import LogReader
from platform.observation.bridge.mapping import EstateIndex, map_series
from platform.observation.bridge.ports import LogLine, MetricPoint, MetricSeries
from platform.observation.bridge.precedence import SignalPrecedence
from platform.observation.bridge.provenance import provenance_change
from platform.observation.bridge.verification import verify_metrics_source
from platform.observation.detectors.model import (
    Comparison,
    Condition,
    ConditionKind,
    DetectorDeclaration,
)
from platform.observation.evaluation import EvaluationTick
from platform.observation.sources.poller import Poller
from platform.observation.sources.port import (
    PollBudget,
    SignalDeclaration,
    SignalPage,
    SignalReading,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
    PersistenceGateway,
    Resource,
    TenantScope,
)

pytestmark = pytest.mark.contract

EPOCH = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)
CLUSTER = "HAL9000"
REPO_ROOT = Path(__file__).resolve().parents[3]

PVE01 = Resource(
    resource_id="res-pve01",
    kind=KIND_NODE,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"node/{CLUSTER}/pve01",
    display_name="pve01",
)
CT100 = Resource(
    resource_id="res-ct100",
    kind=KIND_CONTAINER,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"lxc/{CLUSTER}/1734000000/100",
    display_name="plex",
    parent_id=PVE01.resource_id,
)
TERACHAD = Resource(
    resource_id="res-terachad",
    kind=KIND_DATASTORE,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"datastore/{CLUSTER}/pve02/TeraChad",
    display_name="TeraChad",
)
RESOURCES = (PVE01, CT100, TERACHAD)
ESTATE = EstateIndex.of(RESOURCES)

DATASTORE_SIGNAL = "datastore.used.ratio"


def series(metric: str, value: float, /, **labels: str) -> MetricSeries:
    """Return one series carrying a single sample."""
    return MetricSeries(
        metric=metric,
        labels=labels,
        samples=(MetricPoint(observed_at=EPOCH, value=value),),
    )


def climbing(metric: str, minutes: int, value: float, /, **labels: str) -> MetricSeries:
    """Return one series holding ``minutes`` of history at ``value``."""
    return MetricSeries(
        metric=metric,
        labels=labels,
        samples=tuple(
            MetricPoint(observed_at=EPOCH - timedelta(minutes=minutes - offset), value=value)
            for offset in range(minutes + 1)
        ),
    )


@dataclass
class StubMetrics:
    """A metrics system answering with whatever a test configured."""

    answers: tuple[MetricSeries, ...] = ()
    fails: Exception | None = None
    calls: int = 0

    async def series(self, *, matchers: tuple[str, ...], at: datetime) -> tuple[MetricSeries, ...]:
        """Return the configured series, or raise."""
        del matchers, at
        self.calls += 1
        if self.fails is not None:
            raise self.fails
        return self.answers

    async def history(
        self,
        *,
        matchers: tuple[str, ...],
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> tuple[MetricSeries, ...]:
        """Return the configured series, or raise."""
        del matchers, start, end, step_seconds
        self.calls += 1
        if self.fails is not None:
            raise self.fails
        return self.answers


@dataclass
class StubLogs:
    """A log system with a declared retention and a pile of lines."""

    retention: int = 86_400
    available: int = 5

    async def retention_seconds(self) -> int:
        """Return the declared retention."""
        return self.retention

    async def lines(
        self, *, selector: str, start: datetime, end: datetime, limit: int
    ) -> tuple[LogLine, ...]:
        """Return up to ``limit`` lines."""
        del selector, start
        return tuple(
            LogLine(observed_at=end - timedelta(seconds=index), line=f"line {index}")
            for index in range(min(self.available, limit))
        )


@dataclass
class StubDashboards:
    """A dashboard system that is reachable."""

    async def check(self) -> None:
        """Return normally."""


@dataclass
class PolledDatastore:
    """The deployment's own poller for the datastore signal."""

    value: float = 0.5
    polls: list[datetime] = field(default_factory=list)

    @property
    def declaration(self) -> SignalDeclaration:
        """Return this source's declaration."""
        return SignalDeclaration(source=PROXMOX_ESTATE_SOURCE, signals=(DATASTORE_SIGNAL,))

    async def read(
        self, *, resource_ids: tuple[str, ...], at: datetime, budget: PollBudget
    ) -> SignalPage:
        """Return one reading per resource asked about."""
        del budget
        self.polls.append(at)
        return SignalPage(
            readings=tuple(
                SignalReading(name=DATASTORE_SIGNAL, resource_id=resource_id, value=self.value)
                for resource_id in resource_ids
            )
        )


def datastore_detector() -> DetectorDeclaration:
    """Return the shipped-shape detector both sources could feed."""
    return DetectorDeclaration(
        detector_id="datastore-nearly-full",
        name="Datastore nearly full",
        description="a datastore above 90% stops accepting backups before it stops guests",
        resource_kinds=(KIND_DATASTORE,),
        signal=DATASTORE_SIGNAL,
        condition=Condition(
            kind=ConditionKind.THRESHOLD,
            comparison=Comparison.ABOVE,
            fire_value=0.9,
            clear_value=0.85,
        ),
        for_seconds=600,
        recovery_seconds=300,
        severity=Severity.CRITICAL,
    )


def history_source(metrics: StubMetrics) -> MetricsHistorySource:
    """Return a bridge-backed source for the datastore signal."""
    return MetricsHistorySource(
        metrics=metrics,
        signal_name=DATASTORE_SIGNAL,
        matcher="pve_disk_usage_ratio",
        rules=SHIPPED_RULES,
        estate=ESTATE,
    )


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    """Return an in-memory gateway with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    yield store


# --- SC-001 ------------------------------------------------------------------------


async def test_sc001_verification_reports_which_expected_exporters_are_present() -> None:
    """SC-001: a real query, and a per-exporter answer."""
    metrics = StubMetrics(answers=(series("pve_up", 1.0, id="node/pve01"),))

    verification = await verify_metrics_source(metrics, at=EPOCH, name="prometheus")

    assert metrics.calls == 1
    assert [entry.exporter for entry in verification.present] == [EXPORTER_PROXMOX]
    assert EXPORTER_NODE in {entry.exporter for entry in verification.absent}


# --- SC-002 ------------------------------------------------------------------------


def test_sc002_series_map_to_resources_and_unmapped_ones_are_reported() -> None:
    """SC-002: the join, and the visible gap where it did not happen."""
    mapping = map_series(
        (
            series("pve_disk_usage_ratio", 0.96, id="storage/pve02/TeraChad"),
            series("mystery_total", 1.0, app="something"),
        ),
        rules=SHIPPED_RULES,
        estate=ESTATE,
    )

    assert [entry.resource_id for entry in mapping.mapped] == [TERACHAD.resource_id]
    assert mapping.unmapped[0].metric == "mystery_total"
    assert mapping.unmapped[0].labels == {"app": "something"}


# --- SC-003 ------------------------------------------------------------------------


async def test_sc003_a_detector_fires_on_history_the_deployment_never_polled(
    gateway: PersistenceGateway,
) -> None:
    """SC-003: the condition held for ten minutes and this deployment saw none of it."""
    metrics = StubMetrics(
        answers=(climbing("pve_disk_usage_ratio", 12, 0.96, id="storage/pve02/TeraChad"),)
    )
    scope = TenantScope(org_id="acme")

    samples = await Poller(reader=history_source(metrics)).poll(
        resource_ids=(TERACHAD.resource_id,), now=EPOCH
    )
    async with gateway.begin(scope) as uow:
        await uow.signals.append(samples)
        outcome = await EvaluationTick(detectors=(datastore_detector(),)).run(
            uow.signals, resources=(TERACHAD,), now=EPOCH
        )

    assert [entry.detector_id for entry in outcome.findings] == ["datastore-nearly-full"]
    assert {sample.source for sample in samples} == {BRIDGE_SOURCE}


# --- SC-004 ------------------------------------------------------------------------


async def test_sc004_an_alert_and_a_detected_condition_are_structurally_identical(
    gateway: PersistenceGateway,
) -> None:
    """SC-004: one lifecycle, one shape, one console screen."""
    scope = TenantScope(org_id="acme")
    alert = IncomingAlert(
        source="alertmanager",
        fingerprint="deadbeef",
        alert_name="ProxmoxStorageCritical",
        summary="TeraChad is 96% full",
        severity=SEVERITY_CRITICAL,
        labels={"id": "storage/pve02/TeraChad"},
        starts_at=EPOCH,
    )

    async with gateway.begin(scope) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        from_alert = await lifecycle.raise_incident(
            raise_for_incoming_alert(alert, rules=SHIPPED_RULES, estate=ESTATE), now=EPOCH
        )
        from_detector = await lifecycle.raise_incident(
            IncidentRaise(
                correlation_key="detector:datastore-nearly-full",
                title="Datastore nearly full",
                summary="TeraChad is 96% full",
                origin=IncidentOrigin.DETECTOR,
                origin_id="datastore-nearly-full",
                severity=SEVERITY_CRITICAL,
                subjects=(IncidentSubject(resource_id=TERACHAD.resource_id, detail="96% full"),),
            ),
            now=EPOCH,
        )

    assert type(from_alert) is type(from_detector)
    assert from_alert.state is from_detector.state
    assert from_alert.severity == from_detector.severity
    assert [subject.resource_id for subject in from_alert.subjects] == [
        subject.resource_id for subject in from_detector.subjects
    ]
    assert from_alert.origin is IncidentOrigin.ALERT
    assert from_detector.origin is IncidentOrigin.DETECTOR


# --- SC-005 ------------------------------------------------------------------------


async def test_sc005_an_alert_resolution_closes_its_incident_as_source_resolved(
    gateway: PersistenceGateway,
) -> None:
    """SC-005: the upstream went green and this deployment agrees, on the record."""
    scope = TenantScope(org_id="acme")
    firing = IncomingAlert(
        source="alertmanager",
        fingerprint="deadbeef",
        alert_name="ProxmoxStorageCritical",
        summary="TeraChad is 96% full",
        labels={"id": "storage/pve02/TeraChad"},
    )

    async with gateway.begin(scope) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        opened = await lifecycle.raise_incident(
            raise_for_incoming_alert(firing, rules=SHIPPED_RULES, estate=ESTATE), now=EPOCH
        )
        resolved = await apply_resolution(
            lifecycle,
            resolution_for(
                IncomingAlert(
                    source="alertmanager",
                    fingerprint="deadbeef",
                    alert_name="ProxmoxStorageCritical",
                    status=ALERT_STATUS_RESOLVED,
                )
            ),
            now=EPOCH + timedelta(minutes=30),
        )
        timeline = await uow.incidents.timeline(opened.incident_id)

    assert resolved is not None
    assert resolved.state is IncidentState.RESOLVED
    assert "alertmanager" in resolved.close_reason
    assert any("resolved" in entry.cause for entry in timeline)


# --- SC-006 ------------------------------------------------------------------------


async def test_sc006_an_investigation_gets_a_resources_metrics_and_logs_without_a_query() -> None:
    """SC-006: no PromQL and no LogQL crossed the boundary into the investigation."""
    mapping = map_series(
        (series("pve_cpu_usage_ratio", 0.62, id="lxc/100"),),
        rules=SHIPPED_RULES,
        estate=ESTATE,
    )
    catalogue = ResourceObservability.of(mapping, resources=RESOURCES)

    metrics = catalogue.metrics_for(CT100.resource_id)
    stream = catalogue.log_selector_for(CT100.resource_id)
    assert stream is not None
    answer = await LogReader(source=StubLogs()).read(stream.selector, at=EPOCH)

    assert [entry.metric for entry in metrics] == ["pve_cpu_usage_ratio"]
    assert metrics[0].latest_value == 0.62
    assert answer.lines
    assert answer.complete


# --- SC-007 ------------------------------------------------------------------------


async def test_sc007_a_report_links_to_the_mapped_dashboard_and_omits_it_when_none_is() -> None:
    """SC-007: the window, and the honest absence."""
    mapping = DashboardMapping(
        dashboard_uid="pve-storage",
        title="Proxmox storage",
        base_url="https://grafana.lan",
        resource_kinds=(KIND_DATASTORE,),
        description="the datastore fill panel",
    )

    linked = await dashboard_link(
        StubDashboards(),
        mappings=(mapping,),
        resource_kind=KIND_DATASTORE,
        detector_id="datastore-nearly-full",
        opened_at=EPOCH,
        closed_at=EPOCH + timedelta(minutes=15),
    )
    unmapped = await dashboard_link(
        StubDashboards(),
        mappings=(mapping,),
        resource_kind=KIND_CONTAINER,
        detector_id="guest-cpu-saturated",
        opened_at=EPOCH,
        closed_at=EPOCH,
    )

    assert linked.link is not None
    assert "from=" in linked.link.url and "to=" in linked.link.url
    assert unmapped.link is None
    assert "no dashboard" in unmapped.omitted_because


# --- SC-008 ------------------------------------------------------------------------


async def test_sc008_an_unavailable_source_raises_and_its_detectors_cannot_evaluate() -> None:
    """SC-008: the failure mode that makes monitoring dangerous, refused twice over."""
    metrics = StubMetrics(fails=MetricsSourceUnreachable("prometheus", reason="refused"))
    detector = datastore_detector()

    with pytest.raises(MetricsSourceUnreachable) as raised:
        await Poller(reader=history_source(metrics)).poll(
            resource_ids=(TERACHAD.resource_id,), now=EPOCH
        )

    outage = outage_for(raised.value, source="prometheus", at=EPOCH, signals=(DATASTORE_SIGNAL,))
    failures = failures_for_outage((detector,), outage=outage)
    incident = raise_for_outage(outage)

    assert [failure.detector_id for failure in failures] == [detector.detector_id]
    assert "nothing is watching" in failures[0].summary
    assert incident.origin is IncidentOrigin.DETECTOR
    assert "prometheus" in incident.summary


# --- SC-009 ------------------------------------------------------------------------


async def test_sc009_a_deployment_with_no_observability_stack_watches_by_its_own_polling(
    gateway: PersistenceGateway,
) -> None:
    """SC-009: the common case. Nothing configured, everything still works."""
    resolved = bridge_config.read(ObservationPolicySettings().bridge)
    assert not resolved.enabled
    assert not resolved.metrics_enabled
    assert not resolved.logs_enabled
    assert resolved.problems == ()

    polled = PolledDatastore(value=0.96)
    kept, silenced = resolved.precedence.select((polled,))
    assert kept == (polled,)
    assert silenced == ()

    scope = TenantScope(org_id="acme")
    samples: list[object] = []
    for offset in range(0, 13, 2):
        samples.extend(
            await Poller(reader=polled).poll(
                resource_ids=(TERACHAD.resource_id,), now=EPOCH - timedelta(minutes=12 - offset)
            )
        )
    async with gateway.begin(scope) as uow:
        await uow.signals.append(samples)  # type: ignore[arg-type]
        outcome = await EvaluationTick(detectors=(datastore_detector(),)).run(
            uow.signals, resources=(TERACHAD,), now=EPOCH
        )

    assert [entry.detector_id for entry in outcome.findings] == ["datastore-nearly-full"]


# --- SC-010 ------------------------------------------------------------------------


def test_sc010_duplicate_coverage_resolves_by_declared_precedence() -> None:
    """SC-010: one condition, two sources, one of them producing."""
    settings = ObservabilityBridgeSettings(
        enabled=True,
        precedence=(
            SignalPrecedenceSettings(
                signal=DATASTORE_SIGNAL,
                winner=PRECEDENCE_SOURCE_BRIDGE,
                reason="prometheus has a year of this datastore and we have twenty minutes",
            ),
        ),
    )
    resolved = bridge_config.read(settings)
    polled = PolledDatastore()
    bridged = history_source(StubMetrics())

    kept, silenced = resolved.precedence.select((polled, bridged))
    report = provenance_change(
        before=(polled,), after=(polled, bridged), precedence=resolved.precedence
    )

    assert [reader.declaration.source for reader in kept] == [BRIDGE_SOURCE]
    assert [entry.signal for entry in silenced] == [DATASTORE_SIGNAL]
    assert report.taken_over == (DATASTORE_SIGNAL,)
    assert report.detectors_affected((datastore_detector(),)) == ("datastore-nearly-full",)


# --- The optionality the whole feature rests on ------------------------------------


def test_no_feature_beside_this_one_depends_on_the_bridge() -> None:
    """T-030: NFR-004 — the estate, observation and the hypervisor work without this.

    Structural, over the whole tree. "It is optional" is a claim that stays true
    exactly until one import makes it false, and the import that would do it
    looks entirely reasonable at the moment somebody writes it.
    """
    forbidden = "platform.observation.bridge"
    watched = (
        REPO_ROOT / "platform" / "estate",
        REPO_ROOT / "platform" / "incidents",
        REPO_ROOT / "platform" / "observation" / "detectors",
        REPO_ROOT / "platform" / "observation" / "sources",
        REPO_ROOT / "integrations",
        REPO_ROOT / "capabilities",
        REPO_ROOT / "core",
    )
    offences: list[str] = []

    for root in watched:
        for module in sorted(root.rglob("*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(forbidden):
                    offences.append(f"{module.relative_to(REPO_ROOT)}: {node.module}")
                if isinstance(node, ast.Import):
                    offences.extend(
                        f"{module.relative_to(REPO_ROOT)}: {alias.name}"
                        for alias in node.names
                        if alias.name.startswith(forbidden)
                    )

    assert offences == []


def test_the_bridge_is_absent_from_the_default_configuration_document() -> None:
    """A deployment that never mentions the bridge is not opted into it."""
    settings = ObservationPolicySettings()

    assert settings.bridge.enabled is False
    assert settings.bridge.metrics.enabled is False
    assert settings.bridge.logs.enabled is False
    assert settings.bridge.dashboards == ()
    assert settings.bridge.precedence == ()


def test_an_outage_of_the_bridge_leaves_locally_gathered_signals_untouched() -> None:
    """Per-signal precedence exists so a self-hosted Prometheus takes only its own."""
    outage = SourceOutage(
        source="prometheus", reason="refused", at=EPOCH, signals=("guest.cpu.ratio",)
    )
    local = datastore_detector()

    assert failures_for_outage((local,), outage=outage) == ()
    assert SignalPrecedence().produces(signal=DATASTORE_SIGNAL, source=PROXMOX_ESTATE_SOURCE)
