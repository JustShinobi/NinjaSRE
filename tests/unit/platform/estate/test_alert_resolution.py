"""An alert's labels, and the estate resource they are about.

The four cases the resolution has to get right, and the one it must never take
quietly: a target nothing in the estate holds is a finding about the estate, not
a payload to drop.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from core.domain.alerts.normalisation import NormalisedAlert
from core.domain.alerts.sources import AlertSource
from platform.estate.alert_resolution import (
    AlertMatch,
    AlertResolution,
    ResolvedTarget,
    UnresolvedAlertTarget,
    resolve_alert,
)
from platform.estate.enrichment import ZoneMap
from platform.persistence.ports.estate_repository import Resource

CLUSTER = "hal9000"


def guest(
    vmid: int,
    *,
    name: str,
    address: str = "",
    zone: str = "",
    domain: str = "",
    kind: str = "container",
) -> Resource:
    """Return a swept container carrying the attributes 053 and 054 declare."""
    attributes: dict[str, Any] = {"vmid": vmid}
    if address:
        attributes["address"] = address
    if zone:
        attributes["zone"] = zone
    if domain:
        attributes["domain"] = domain
    return Resource(
        resource_id=f"proxmox:{kind}/{CLUSTER}/{vmid}",
        kind=kind,
        source="proxmox",
        native_id=f"{kind}/{CLUSTER}/{vmid}",
        display_name=name,
        attributes=attributes,
    )


#: A small estate in the shape 053 stores one: two zones, addresses on the
#: guests, one guest serving a declared domain.
ESTATE: tuple[Resource, ...] = (
    guest(110, name="adguard", address="10.20.20.10", zone="apps", domain="dns.example.net"),
    guest(111, name="clickhouse", address="10.20.20.11", zone="apps"),
    guest(210, name="gitea", address="10.20.30.10", zone="infra"),
    Resource(
        resource_id="proxmox:node/hal9000/pve1",
        kind="node",
        source="proxmox",
        native_id=f"node/{CLUSTER}/pve1",
        display_name="pve1",
        attributes={"address": "10.20.10.1", "zone": "mgmt"},
    ),
)


def alert(labels: Mapping[str, str], *, name: str = "ContainerUnderPressure") -> NormalisedAlert:
    """Return the normalised alert carrying ``labels``."""
    return NormalisedAlert(
        alert_source=AlertSource.ALERTMANAGER,
        alert_name=name,
        summary="memory usage above 90%",
        labels=dict(labels),
    )


def test_an_instance_label_resolves_to_the_resource_holding_that_address() -> None:
    """The commonest Alertmanager shape: a scrape target's own address."""
    resolution = resolve_alert(alert({"instance": "10.20.20.11:9100"}), resources=ESTATE)

    assert resolution.unresolved is None
    resolved = resolution.resolved
    assert resolved is not None
    assert resolved.resource_id == "proxmox:container/hal9000/111"
    assert resolved.matched_on is AlertMatch.ADDRESS
    assert resolved.label == "instance"
    assert resolved.value == "10.20.20.11"
    assert resolved.zone == "apps"


def test_a_vmid_label_resolves_the_guest_directly() -> None:
    """A pve-exporter series is keyed by the guest's own number, so nothing is parsed.

    The alert also carries the *host's* address, which is what a host-side
    exporter labels a guest's series with. Resolving that instead would produce
    an investigation of the hypervisor about a container's memory.
    """
    resolution = resolve_alert(
        alert({"vmid": "110", "instance": "10.20.10.1:9221"}), resources=ESTATE
    )

    resolved = resolution.resolved
    assert resolved is not None
    assert resolved.resource_id == "proxmox:container/hal9000/110"
    assert resolved.matched_on is AlertMatch.VMID
    assert resolved.display_name == "adguard"


def test_a_blackbox_target_resolves_through_the_declared_domain() -> None:
    """``services.yaml`` says which workload answers a domain; the alert says the domain."""
    resolution = resolve_alert(
        alert({"target": "https://dns.example.net/health"}, name="ProbeFailed"),
        resources=ESTATE,
    )

    resolved = resolution.resolved
    assert resolved is not None
    assert resolved.resource_id == "proxmox:container/hal9000/110"
    assert resolved.matched_on is AlertMatch.DOMAIN
    assert resolved.value == "dns.example.net"


def test_an_unmatched_target_is_a_finding_and_never_a_silent_none() -> None:
    """An alert for something nobody swept is information about the estate."""
    resolution = resolve_alert(alert({"instance": "10.20.20.99:9100"}), resources=ESTATE)

    assert resolution.resolved is None
    unresolved = resolution.unresolved
    assert unresolved is not None
    assert unresolved.value == "10.20.20.99"
    assert unresolved.label == "instance"
    assert "10.20.20.99" in unresolved.why


def test_an_unmatched_address_carries_the_zone_its_neighbours_sit_in() -> None:
    """The ``/24`` step of the spec: the estate itself says which network this is."""
    resolution = resolve_alert(alert({"instance": "10.20.20.99:9100"}), resources=ESTATE)

    assert resolution.unresolved is not None
    assert resolution.unresolved.zone == "apps"


def test_a_declared_zone_map_outranks_what_the_neighbours_imply() -> None:
    """An operator's declared network is a decision; a neighbourhood is an inference."""
    zones = ZoneMap.of({"10.20.20.0/24": "apps-declared"})
    resolution = resolve_alert(
        alert({"instance": "10.20.20.99:9100"}), resources=ESTATE, zones=zones
    )

    assert resolution.unresolved is not None
    assert resolution.unresolved.zone == "apps-declared"


def test_an_alert_whose_labels_name_no_target_at_all_is_still_a_finding() -> None:
    """Nothing to look up is a different sentence, and still not a discard."""
    resolution = resolve_alert(alert({"severity": "critical"}), resources=ESTATE)

    assert resolution.resolved is None
    assert resolution.unresolved is not None
    assert resolution.unresolved.label == ""
    assert resolution.unresolved.value == ""


def test_the_first_label_that_names_a_target_is_the_one_reported() -> None:
    """Declared order, so a finding names the most specific target the alert carried."""
    resolution = resolve_alert(
        alert({"vmid": "999", "instance": "10.20.20.99:9100"}), resources=ESTATE
    )

    assert resolution.unresolved is not None
    assert resolution.unresolved.label == "vmid"
    assert resolution.unresolved.value == "999"


def test_a_resolution_is_exactly_one_of_the_two() -> None:
    """Neither is a target nobody accounted for; both is two answers."""
    with pytest.raises(ValueError, match="exactly one"):
        AlertResolution()
    with pytest.raises(ValueError, match="exactly one"):
        AlertResolution(
            resolved=ResolvedTarget(
                resource_id="r",
                kind="container",
                display_name="r",
                matched_on=AlertMatch.VMID,
                label="vmid",
                value="1",
            ),
            unresolved=UnresolvedAlertTarget(label="vmid", value="1", why="both"),
        )


def test_a_resolution_round_trips_through_its_record() -> None:
    """The webhook stores it on an incident and a route reads it back."""
    resolution = resolve_alert(alert({"vmid": "110"}), resources=ESTATE)
    assert resolution.resolved is not None
    assert ResolvedTarget.from_record(resolution.resolved.to_record()) == resolution.resolved

    finding = resolve_alert(alert({"vmid": "999"}), resources=ESTATE).unresolved
    assert finding is not None
    assert UnresolvedAlertTarget.from_record(finding.to_record()) == finding
