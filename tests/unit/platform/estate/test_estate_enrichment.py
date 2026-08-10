"""Zones from addresses, annotations onto resources, and divergence as content.

Three claims, and the third is the one that is easy to get wrong in a way
nobody notices for months.

**A zone comes from the address, or it does not come at all.** ``ZoneMap`` is a
total function: every address either falls inside a declared network or returns
the empty string. There is no nearest match, no default zone, and no guess from
a name — a guest called ``dmz-proxy`` sitting on the apps network is on the apps
network, and a map that read its name would place it where somebody's naming
convention said rather than where the packets go.

**An annotation may only annotate.** Enrichment reads a file an operator
maintains, and a file can name a machine that was deleted last April. Applying
it must never bring that machine back into the estate: the live source is the
truth about what exists, so an annotation with no resource is a divergence
record and never an upsert.

**Divergence is content.** Both directions of disagreement, plus a resource no
declared network covers, are *stored* and *returned* rather than logged and
dropped. An inventory that quietly agrees with itself is the one nobody can
trust.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from platform.estate.enrichment import (
    ANNOTATION_TYPES,
    Annotation,
    Divergence,
    DivergenceKind,
    EnrichmentPlan,
    OverlappingZones,
    ZoneMap,
    apply_enrichment,
)
from platform.estate.kinds import KIND_CONTAINER, core_registry
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.persistence.ports.estate_repository import EstateQuery, Resource

pytestmark = pytest.mark.unit

SCOPE = TenantScope(org_id="acme", team_node_id="homelab")
AT = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
SOURCE = "proxmox"

ZONES = {
    "10.20.10.0/24": "mgmt",
    "10.20.20.0/24": "infra",
    "10.20.30.0/24": "apps",
    "10.20.40.0/24": "dmz",
}


# --- ZoneMap ------------------------------------------------------------------


def test_an_address_inside_a_declared_network_carries_that_networks_name() -> None:
    zones = ZoneMap.of(ZONES)

    assert zones.zone_for("10.20.30.7") == "apps"
    assert zones.zone_for("10.20.20.1") == "infra"


def test_an_address_no_declared_network_covers_carries_no_zone() -> None:
    """Total, and empty rather than a guess. The caller reports the miss."""
    zones = ZoneMap.of(ZONES)

    assert zones.zone_for("192.168.68.149") == ""
    assert zones.zone_for("") == ""
    assert zones.zone_for("not-an-address") == ""


def test_an_address_with_a_prefix_on_it_is_read_as_the_address() -> None:
    """Proxmox writes ``ip=10.20.30.7/24`` in a guest's network line."""
    assert ZoneMap.of(ZONES).zone_for("10.20.30.7/24") == "apps"


def test_two_networks_that_overlap_are_refused_at_construction() -> None:
    """A map where one address has two zones has no correct answer, and the one
    a lookup happens to find first is not a decision anybody took."""
    with pytest.raises(OverlappingZones) as refused:
        ZoneMap.of({"10.20.0.0/16": "everything", "10.20.30.0/24": "apps"})

    message = str(refused.value)
    assert "10.20.0.0/16" in message
    assert "10.20.30.0/24" in message


def test_a_network_that_is_not_one_is_refused_naming_it() -> None:
    with pytest.raises(ValueError, match="10.20.30.1/24"):
        ZoneMap.of({"10.20.30.1/24": "apps"})


def test_an_empty_map_places_nothing_and_refuses_nothing() -> None:
    assert ZoneMap.of({}).zone_for("10.20.30.7") == ""
    assert ZoneMap.of({}).networks == ()


# --- applying annotations -----------------------------------------------------


async def _store() -> FakePersistence:
    """Return an empty store with one organisation."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(SCOPE.org_id, "Acme")
    return gateway


async def _seeded() -> FakePersistence:
    """Return a store holding two containers reported by the live source."""
    gateway = await _store()
    async with gateway.begin(SCOPE) as uow:
        for native_id, address in (("lxc/100", "10.20.30.7"), ("lxc/101", "10.20.20.4")):
            await uow.estate.upsert(
                Resource(
                    resource_id=f"res-{native_id}",
                    kind=KIND_CONTAINER,
                    source=SOURCE,
                    native_id=native_id,
                    correlation_key=f"HAL9000/{native_id}",
                    display_name=native_id,
                    attributes={"address": address},
                    labels=("lxc",),
                    first_seen_at=AT,
                    last_seen_at=AT,
                )
            )
    return gateway


async def test_an_annotation_lands_on_the_resource_the_live_source_reported() -> None:
    gateway = await _seeded()
    plan = EnrichmentPlan(
        zones=ZoneMap.of(ZONES),
        annotations=(
            Annotation(
                correlation_key="HAL9000/lxc/100", values={"criticality": "high", "tier": "edge"}
            ),
        ),
    )

    report = await apply_enrichment(
        gateway, SCOPE, plan=plan, source=SOURCE, kinds=core_registry(), at=AT
    )

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.by_native_id(source=SOURCE, native_id="lxc/100")
    assert stored is not None
    assert stored.attributes["criticality"] == "high"
    assert stored.attributes["tier"] == "edge"
    assert stored.attributes["zone"] == "apps"
    assert "zone:apps" in stored.labels
    assert report.annotated == 1


async def test_a_resource_with_no_declared_criticality_carries_none() -> None:
    """Absent rather than a default. "unknown criticality" and "medium" are
    different facts, and only one of them is something somebody decided."""
    gateway = await _seeded()
    plan = EnrichmentPlan(
        zones=ZoneMap.of(ZONES),
        annotations=(
            Annotation(correlation_key="HAL9000/lxc/100", values={"criticality": "high"}),
        ),
    )

    await apply_enrichment(gateway, SCOPE, plan=plan, source=SOURCE, kinds=core_registry(), at=AT)

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.by_native_id(source=SOURCE, native_id="lxc/101")
    assert stored is not None
    assert "criticality" not in stored.attributes
    assert stored.attributes["zone"] == "infra"


async def test_an_annotation_for_something_the_source_never_reported_is_a_divergence() -> None:
    """The file's machine that no longer exists. A finding, not a resource."""
    gateway = await _seeded()
    plan = EnrichmentPlan(
        zones=ZoneMap.of(ZONES),
        annotations=(
            Annotation(correlation_key="HAL9000/lxc/999", values={"criticality": "high"}),
        ),
    )

    report = await apply_enrichment(
        gateway, SCOPE, plan=plan, source=SOURCE, kinds=core_registry(), at=AT
    )

    async with gateway.begin(SCOPE) as uow:
        found = await uow.estate.query(EstateQuery(sources=(SOURCE,), limit=50))
    assert {resource.native_id for resource in found} == {"lxc/100", "lxc/101"}

    only_in_file = [
        entry for entry in report.divergences if entry.kind is DivergenceKind.ONLY_IN_FILE
    ]
    assert [entry.subject for entry in only_in_file] == ["HAL9000/lxc/999"]
    assert "no longer" in only_in_file[0].detail


async def test_a_resource_the_file_does_not_declare_is_a_divergence_too() -> None:
    gateway = await _seeded()
    plan = EnrichmentPlan(
        zones=ZoneMap.of(ZONES),
        annotations=(
            Annotation(correlation_key="HAL9000/lxc/100", values={"criticality": "high"}),
        ),
    )

    report = await apply_enrichment(
        gateway, SCOPE, plan=plan, source=SOURCE, kinds=core_registry(), at=AT
    )

    undeclared = [
        entry for entry in report.divergences if entry.kind is DivergenceKind.ONLY_IN_PROVIDER
    ]
    assert [entry.subject for entry in undeclared] == ["HAL9000/lxc/101"]


async def test_an_address_no_network_covers_is_impossible_to_miss() -> None:
    gateway = await _store()
    async with gateway.begin(SCOPE) as uow:
        await uow.estate.upsert(
            Resource(
                resource_id="res-lxc/200",
                kind=KIND_CONTAINER,
                source=SOURCE,
                native_id="lxc/200",
                correlation_key="HAL9000/lxc/200",
                display_name="stray",
                attributes={"address": "192.168.68.9"},
                first_seen_at=AT,
                last_seen_at=AT,
            )
        )

    report = await apply_enrichment(
        gateway,
        SCOPE,
        plan=EnrichmentPlan(zones=ZoneMap.of(ZONES)),
        source=SOURCE,
        kinds=core_registry(),
        at=AT,
    )

    unplaced = [entry for entry in report.divergences if entry.kind is DivergenceKind.NO_ZONE]
    assert [entry.subject for entry in unplaced] == ["HAL9000/lxc/200"]
    assert "192.168.68.9" in unplaced[0].detail

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.by_native_id(source=SOURCE, native_id="lxc/200")
    assert stored is not None
    assert stored.attributes.get("zone", "") == ""


async def test_applying_the_same_plan_twice_changes_nothing() -> None:
    """Enrichment runs after every sweep, so it has to be idempotent or the
    estate would grow a new label per pass."""
    gateway = await _seeded()
    plan = EnrichmentPlan(
        zones=ZoneMap.of(ZONES),
        annotations=(
            Annotation(correlation_key="HAL9000/lxc/100", values={"criticality": "high"}),
        ),
    )

    first = await apply_enrichment(
        gateway, SCOPE, plan=plan, source=SOURCE, kinds=core_registry(), at=AT
    )
    async with gateway.begin(SCOPE) as uow:
        after_one = await uow.estate.by_native_id(source=SOURCE, native_id="lxc/100")

    second = await apply_enrichment(
        gateway, SCOPE, plan=plan, source=SOURCE, kinds=core_registry(), at=AT
    )
    async with gateway.begin(SCOPE) as uow:
        after_two = await uow.estate.by_native_id(source=SOURCE, native_id="lxc/100")

    assert after_one == after_two
    assert first.to_record() == second.to_record()


async def test_an_annotation_the_schema_does_not_declare_is_dropped_not_stored() -> None:
    """The closed bag. A file that grew a field is not a reason for the estate
    to grow a column nothing declares."""
    gateway = await _seeded()
    plan = EnrichmentPlan(
        zones=ZoneMap.of(ZONES),
        annotations=(
            Annotation(
                correlation_key="HAL9000/lxc/100",
                values={"criticality": "high", "hair_colour": "red"},
            ),
        ),
    )

    report = await apply_enrichment(
        gateway, SCOPE, plan=plan, source=SOURCE, kinds=core_registry(), at=AT
    )

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.by_native_id(source=SOURCE, native_id="lxc/100")
    assert stored is not None
    assert "hair_colour" not in stored.attributes
    assert "hair_colour" in report.dropped
    assert "hair_colour" not in ANNOTATION_TYPES


async def test_an_annotation_carrying_something_shaped_like_a_credential_is_screened() -> None:
    """T-008's second half at the point of storage. The value never lands."""
    gateway = await _seeded()
    secret = "ghp_0123456789abcdefghijklmnopqrstuvwxyzAB"
    plan = EnrichmentPlan(
        zones=ZoneMap.of(ZONES),
        annotations=(Annotation(correlation_key="HAL9000/lxc/100", values={"owner": secret}),),
    )

    report = await apply_enrichment(
        gateway, SCOPE, plan=plan, source=SOURCE, kinds=core_registry(), at=AT
    )

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.by_native_id(source=SOURCE, native_id="lxc/100")
    assert stored is not None
    assert secret not in str(stored.attributes)
    assert "owner" in report.screened


def test_a_divergence_renders_as_a_record_a_console_can_mark_a_row_with() -> None:
    record = Divergence(
        kind=DivergenceKind.ONLY_IN_FILE,
        subject="HAL9000/lxc/999",
        detail="declared in the inventory and not reported by proxmox",
    ).to_record()

    assert record == {
        "kind": "only_in_file",
        "subject": "HAL9000/lxc/999",
        "detail": "declared in the inventory and not reported by proxmox",
    }
