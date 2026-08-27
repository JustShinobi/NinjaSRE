"""Somebody else's alert becoming one of our incidents, through the one lifecycle.

The temptation this file exists to refuse is a parallel path: an "alert" object
with its own list, its own console screen and its own close semantics, sitting
beside incidents and meaning almost the same thing. Alertmanager is the source
most likely to tempt it, because its payload already looks like an incident.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from config.constants.notifications import SEVERITY_CRITICAL
from config.constants.observability_bridge import PROXMOX_ESTATE_SOURCE
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.notifications.models import Severity
from platform.observation.bridge.alerts import (
    ALERT_STATUS_RESOLVED,
    SOURCE_RESOLVED_REASON,
    IncomingAlert,
    apply_resolution,
    correlate,
    raise_for_incoming_alert,
    resolution_for,
)
from platform.observation.bridge.exporters import SHIPPED_RULES
from platform.observation.bridge.mapping import EstateIndex
from platform.observation.detectors.model import (
    Comparison,
    Condition,
    ConditionKind,
    DetectorDeclaration,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
    Resource,
    TenantScope,
)

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 8, 9, 3, 14, tzinfo=UTC)
CLUSTER = "HAL9000"
ALERTS_MODULE = (
    Path(__file__).resolve().parents[5] / "platform" / "observation" / "bridge" / "alerts.py"
)

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
)
ESTATE = EstateIndex.of((PVE01, CT100))


def alert(**overrides: object) -> IncomingAlert:
    """Return one firing Alertmanager alert about the reference cluster's node."""
    base = IncomingAlert(
        source="alertmanager",
        fingerprint="c0ffee",
        alert_name="NodeFilesystemAlmostFull",
        summary="/ on pve02 is 80% full",
        description="the root filesystem has been above 80% for fifteen minutes",
        severity=SEVERITY_CRITICAL,
        labels={"instance": "pve01:9100", "job": "node", "severity": SEVERITY_CRITICAL},
        starts_at=EPOCH,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


async def lifecycle() -> tuple[IncidentLifecycle, FakePersistence, TenantScope]:
    """Return a lifecycle over an in-memory store with one organisation."""
    persistence = FakePersistence()
    async with persistence.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    scope = TenantScope(org_id="acme")
    async with persistence.begin(scope) as uow:
        return IncidentLifecycle(store=uow.incidents), persistence, scope


def test_an_alert_is_correlated_to_the_resource_it_names() -> None:
    """FR-009: the alert says pve01 and the incident is about the node called pve01."""
    found = correlate(alert().labels, rules=SHIPPED_RULES, estate=ESTATE)

    assert found.resource_id == PVE01.resource_id
    assert found.rule_id == "node-exporter-machine"
    assert found.correlated


def test_an_alert_naming_an_unknown_resource_still_opens_an_incident_marked_uncorrelated() -> None:
    """An alert about something we do not know is still an alert somebody sent."""
    unknown = alert(labels={"instance": "unknown-host:9100", "job": "node"})

    found = correlate(unknown.labels, rules=SHIPPED_RULES, estate=ESTATE)
    request = raise_for_incoming_alert(unknown, rules=SHIPPED_RULES, estate=ESTATE)

    assert not found.correlated
    assert found.reason
    assert request.subjects
    assert request.labels["correlated"] == "no"


def test_a_correlated_alert_carries_the_resource_as_its_subject() -> None:
    """The incident points at the estate resource, not at a label set."""
    request = raise_for_incoming_alert(alert(), rules=SHIPPED_RULES, estate=ESTATE)

    assert [subject.resource_id for subject in request.subjects] == [PVE01.resource_id]
    assert request.labels["correlated"] == "yes"
    assert request.origin is IncidentOrigin.ALERT


def test_the_sources_own_grouping_is_respected_rather_than_re_derived() -> None:
    """FR-011: two alerts in one Alertmanager group are one incident."""
    first = alert(fingerprint="aaa", group_key='{}:{alertname="NodeDown"}')
    second = alert(fingerprint="bbb", group_key='{}:{alertname="NodeDown"}')

    one = raise_for_incoming_alert(first, rules=SHIPPED_RULES, estate=ESTATE)
    two = raise_for_incoming_alert(second, rules=SHIPPED_RULES, estate=ESTATE)

    assert one.correlation_key == two.correlation_key
    assert one.labels["grouped_by"] == "group_key"


def test_an_ungrouped_alert_correlates_on_the_upstreams_fingerprint() -> None:
    """Without a group key the upstream's fingerprint is what it will resolve under."""
    one = raise_for_incoming_alert(alert(), rules=SHIPPED_RULES, estate=ESTATE)
    two = raise_for_incoming_alert(alert(fingerprint="other"), rules=SHIPPED_RULES, estate=ESTATE)

    assert one.correlation_key != two.correlation_key
    assert one.labels["grouped_by"] == "fingerprint"


@pytest.mark.asyncio
async def test_an_alert_and_a_detected_condition_produce_structurally_identical_incidents() -> None:
    """SC-004: one lifecycle. The two differ in origin and in nothing else structural."""
    life, _, _ = await lifecycle()

    from_alert = await life.raise_incident(
        raise_for_incoming_alert(alert(), rules=SHIPPED_RULES, estate=ESTATE), now=EPOCH
    )
    from_detector = await life.raise_incident(
        IncidentRaise(
            correlation_key="detector:node-filesystem-full",
            title="NodeFilesystemAlmostFull",
            summary="/ on pve02 is 80% full",
            origin=IncidentOrigin.DETECTOR,
            origin_id="node-filesystem-full",
            severity=SEVERITY_CRITICAL,
            subjects=(IncidentSubject(resource_id=PVE01.resource_id, detail="80% full"),),
        ),
        now=EPOCH,
    )

    assert type(from_alert) is type(from_detector)
    differing = {
        name
        for name in from_alert.__slots__
        if getattr(from_alert, name) != getattr(from_detector, name)
    }
    assert differing <= {
        "incident_id",
        # Derived from ``incident_id``, so two incidents that are allowed to
        # carry different identifiers are allowed to carry different addresses
        # for the same reason. A shared address would be the defect.
        "public_id",
        "correlation_key",
        "origin",
        "origin_id",
        "subjects",
        "labels",
    }
    assert from_alert.state is from_detector.state
    assert from_alert.severity == from_detector.severity


@pytest.mark.asyncio
async def test_a_resolution_closes_its_incident_as_source_resolved() -> None:
    """SC-005: the upstream went green and this deployment agrees with it."""
    life, _, _ = await lifecycle()
    opened = await life.raise_incident(
        raise_for_incoming_alert(alert(), rules=SHIPPED_RULES, estate=ESTATE), now=EPOCH
    )

    resolved = alert(status=ALERT_STATUS_RESOLVED, ends_at=EPOCH + timedelta(minutes=10))
    closed = await apply_resolution(
        life, resolution_for(resolved), now=EPOCH + timedelta(minutes=10)
    )

    assert closed is not None
    assert closed.incident_id == opened.incident_id
    assert closed.state is IncidentState.RESOLVED
    assert SOURCE_RESOLVED_REASON in closed.close_reason
    assert "alertmanager" in closed.close_reason


@pytest.mark.asyncio
async def test_a_resolution_for_an_incident_nobody_opened_is_not_an_error() -> None:
    """A deployment that started after the alert fired still gets the resolution."""
    life, _, _ = await lifecycle()

    closed = await apply_resolution(
        life, resolution_for(alert(status=ALERT_STATUS_RESOLVED)), now=EPOCH
    )

    assert closed is None


def test_a_resolution_is_refused_for_an_alert_that_is_still_firing() -> None:
    """Closing an incident because a firing alert arrived would be a very bad bug."""
    with pytest.raises(ValueError, match="firing"):
        resolution_for(alert())


def test_the_alert_path_builds_no_incident_of_its_own() -> None:
    """T-015: there is no second path. This module composes the one that exists.

    Structural, because "we use the lifecycle" is the kind of claim that stays
    true right up until somebody adds a fast path for one field.
    """
    tree = ast.parse(ALERTS_MODULE.read_text(encoding="utf-8"))
    constructed = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "Incident" not in constructed
    assert "IncidentRaise" not in constructed


def test_a_detector_over_an_alert_signal_is_not_what_this_does() -> None:
    """A guard against the other shortcut: an alert is not turned into a detector."""
    declaration = DetectorDeclaration(
        detector_id="not-used-here",
        name="unused",
        description="present only so this test names the thing it is ruling out",
        resource_kinds=(),
        signal="alert",
        condition=Condition(
            kind=ConditionKind.THRESHOLD, comparison=Comparison.ABOVE, fire_value=1.0
        ),
        for_seconds=60,
        recovery_seconds=60,
        severity=Severity.HIGH,
    )
    source = ALERTS_MODULE.read_text(encoding="utf-8")

    assert declaration.detector_id not in source
    assert "DetectorDeclaration" not in source
