"""Contract: the estate, and the four things a backend must never get wrong.

Absence is assigned only by a successful sweep, staleness never touches another
integration's resources, a re-discovery updates rather than duplicates, and one
tenant's estate is invisible from another. Everything else in this file supports
one of those four.
"""

from __future__ import annotations

import pytest
from conftest import EPOCH, at

from platform.persistence.errors import BoundExceeded, RecordNotFound
from platform.persistence.ports import (
    EstateQuery,
    EstateRepository,
    HealthDerivation,
    HealthSignal,
    PersistenceGateway,
    ReferenceKind,
    Resource,
    ResourceHealth,
    ResourceReference,
    ResourceSource,
    SweepOutcome,
    SweepRecord,
    TenantScope,
)
from platform.persistence.ports.estate_repository import whole_estate

pytestmark = pytest.mark.contract


def resource(
    resource_id: str = "r-1",
    *,
    kind: str = "virtual_machine",
    source: str = "proxmox",
    native_id: str = "qemu/101",
    display_name: str = "checkout-api",
    parent_id: str | None = None,
    labels: tuple[str, ...] = (),
    team_node_id: str | None = None,
) -> Resource:
    """Return a resource as a first discovery would supply it."""
    return Resource(
        resource_id=resource_id,
        kind=kind,
        source=source,
        native_id=native_id,
        display_name=display_name,
        parent_id=parent_id,
        team_node_id=team_node_id,
        attributes={"cores": 4, "memory_mb": 8192},
        labels=labels,
        sources=(
            ResourceSource(
                integration=source,
                native_id=native_id,
                display_name=display_name,
                attributes={"cores": 4},
                observed_at=at(),
            ),
        ),
        first_seen_at=at(),
        last_seen_at=at(),
    )


def derivation(
    state: ResourceHealth = ResourceHealth.HEALTHY,
    *,
    minutes: float = 0.0,
    rule: str = "provider_status",
    raw_status: str = "running",
) -> HealthDerivation:
    """Return a derivation carrying one signal and the raw provider status."""
    return HealthDerivation(
        state=state,
        rule=rule,
        derived_at=at(minutes),
        signals=(
            HealthSignal(
                name="provider_status",
                value=raw_status,
                observed_at=at(minutes),
                source="proxmox",
            ),
        ),
        raw_status=raw_status,
        explanation=f"the provider reported {raw_status}",
    )


async def estate_of(gateway: PersistenceGateway, scope: TenantScope) -> EstateRepository:
    """Return an estate repository, for a read that needs no other port."""
    async with gateway.begin(scope) as uow:
        return uow.estate


# --- Writing and reading -------------------------------------------------------


async def test_a_written_resource_reads_back_whole(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource(labels=("env:prod",), team_node_id="team-checkout"))

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get("r-1")

    assert stored is not None
    assert stored.kind == "virtual_machine"
    assert stored.source == "proxmox"
    assert stored.native_id == "qemu/101"
    assert stored.display_name == "checkout-api"
    assert stored.attributes == {"cores": 4, "memory_mb": 8192}
    assert stored.labels == ("env:prod",)
    assert stored.team_node_id == "team-checkout"
    assert stored.sources[0].integration == "proxmox"


async def test_a_rename_updates_rather_than_duplicating(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-002: identity comes from the source, so a new display name is an update."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource(display_name="checkout-api"))
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource(display_name="checkout-api-v2"))

    async with gateway.begin(scope) as uow:
        found = await uow.estate.query(EstateQuery())
        stored = await uow.estate.get("r-1")

    assert len(found) == 1
    assert stored is not None
    assert stored.display_name == "checkout-api-v2"


async def test_an_upsert_keeps_the_instant_the_resource_was_first_seen(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource())
    async with gateway.begin(scope) as uow:
        later = resource()
        await uow.estate.upsert(
            Resource(
                resource_id=later.resource_id,
                kind=later.kind,
                source=later.source,
                native_id=later.native_id,
                display_name=later.display_name,
                first_seen_at=at(600),
                last_seen_at=at(600),
            )
        )

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get("r-1")

    assert stored is not None
    assert stored.first_seen_at == at()
    assert stored.last_seen_at == at(600)


async def test_a_native_id_lookup_finds_what_a_source_calls_it(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource())

    async with gateway.begin(scope) as uow:
        found = await uow.estate.by_native_id(source="proxmox", native_id="qemu/101")
        missing = await uow.estate.by_native_id(source="proxmox", native_id="qemu/999")

    assert found is not None
    assert found.resource_id == "r-1"
    assert missing is None


# --- Query ---------------------------------------------------------------------


async def test_every_declared_dimension_filters(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(
            resource("r-node", kind="node", native_id="node/pve1", display_name="pve1")
        )
        await uow.estate.upsert(
            resource(
                "r-vm",
                kind="virtual_machine",
                native_id="qemu/101",
                parent_id="r-node",
                labels=("env:prod",),
                team_node_id="team-checkout",
            )
        )
        await uow.estate.upsert(
            resource("r-ct", kind="container", source="docker", native_id="ct/7")
        )
        await uow.estate.record_health("r-vm", derivation(ResourceHealth.DEGRADED))

    async with gateway.begin(scope) as uow:
        estate = uow.estate
        by_kind = await estate.query(EstateQuery(kinds=("virtual_machine",)))
        by_health = await estate.query(EstateQuery(health=(ResourceHealth.DEGRADED,)))
        by_source = await estate.query(EstateQuery(sources=("docker",)))
        by_label = await estate.query(EstateQuery(labels=("env:prod",)))
        by_team = await estate.query(EstateQuery(team_node_id="team-checkout"))
        by_parent = await estate.query(EstateQuery(parent_id="r-node"))
        by_freshness = await estate.query(EstateQuery(observed_before=at(1)))

    assert [found.resource_id for found in by_kind] == ["r-vm"]
    assert [found.resource_id for found in by_health] == ["r-vm"]
    assert [found.resource_id for found in by_source] == ["r-ct"]
    assert [found.resource_id for found in by_label] == ["r-vm"]
    assert [found.resource_id for found in by_team] == ["r-vm"]
    assert [found.resource_id for found in by_parent] == ["r-vm"]
    # Only ``r-vm`` has a derivation at all; the other two have never been
    # observed, and "never" is not "before".
    assert [found.resource_id for found in by_freshness] == ["r-vm"]


async def test_a_query_above_the_page_bound_raises(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(BoundExceeded):
            await uow.estate.query(EstateQuery(limit=10_000))


async def test_absent_resources_are_excluded_unless_asked_for(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-1", native_id="qemu/101"))
        await uow.estate.upsert(resource("r-2", native_id="qemu/102"))
        await uow.estate.mark_absent(source="proxmox", seen_ids=frozenset({"r-1"}), at=at(10))

    async with gateway.begin(scope) as uow:
        default = await uow.estate.query(EstateQuery())
        including = await uow.estate.query(EstateQuery(include_absent=True))

    assert [found.resource_id for found in default] == ["r-1"]
    assert [found.resource_id for found in including] == ["r-1", "r-2"]


# --- Absence and staleness -----------------------------------------------------


async def test_a_successful_sweep_marks_the_gone_resource_absent_and_keeps_its_history(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-003, second half."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-gone", native_id="qemu/102"))
        await uow.estate.record_health("r-gone", derivation(ResourceHealth.HEALTHY))
        marked = await uow.estate.mark_absent(source="proxmox", seen_ids=frozenset(), at=at(10))

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get("r-gone")
        history = await uow.estate.transitions("r-gone")

    assert marked == ("r-gone",)
    assert stored is not None
    assert stored.absent_since == at(10)
    assert stored.reported_health(at(10)) is ResourceHealth.ABSENT
    assert [entry.state for entry in history] == [ResourceHealth.ABSENT, ResourceHealth.HEALTHY]
    assert history[0].previous_state is ResourceHealth.HEALTHY


async def test_marking_absent_twice_does_not_move_the_timestamp(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-gone", native_id="qemu/102"))
        await uow.estate.mark_absent(source="proxmox", seen_ids=frozenset(), at=at(10))
        second = await uow.estate.mark_absent(source="proxmox", seen_ids=frozenset(), at=at(20))

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get("r-gone")

    assert second == ()
    assert stored is not None
    assert stored.absent_since == at(10)


async def test_a_failed_sweep_marks_stale_and_never_absent(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-003, first half — the most damaging bug this component can have."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-1", native_id="qemu/101"))
        await uow.estate.record_health("r-1", derivation(ResourceHealth.HEALTHY))
        marked = await uow.estate.mark_stale(
            source="proxmox", at=at(10), reason="the API returned 503"
        )

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get("r-1")

    assert marked == ("r-1",)
    assert stored is not None
    assert stored.absent_since is None
    assert stored.health is ResourceHealth.STALE
    assert stored.derivation is not None
    assert "503" in stored.derivation.explanation


async def test_one_integrations_failure_leaves_another_integrations_resources_alone(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-vm", source="proxmox", native_id="qemu/101"))
        await uow.estate.upsert(resource("r-ct", source="docker", native_id="ct/7"))
        await uow.estate.record_health("r-ct", derivation(ResourceHealth.HEALTHY))
        await uow.estate.mark_stale(source="proxmox", at=at(10), reason="the API returned 503")
        await uow.estate.mark_absent(source="proxmox", seen_ids=frozenset(), at=at(10))

    async with gateway.begin(scope) as uow:
        untouched = await uow.estate.get("r-ct")

    assert untouched is not None
    assert untouched.health is ResourceHealth.HEALTHY
    assert untouched.absent_since is None


async def test_a_sweep_record_round_trips_and_the_latest_wins(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.record_sweep(
            SweepRecord(
                sweep_id="s-1",
                source="proxmox",
                started_at=at(),
                outcome=SweepOutcome.SUCCEEDED,
                completed_at=at(1),
                seen_count=11,
                provider_calls=3,
            )
        )
        await uow.estate.record_sweep(
            SweepRecord(
                sweep_id="s-2",
                source="proxmox",
                started_at=at(15),
                outcome=SweepOutcome.SUSPENDED,
                cursor="page-2",
                seen_count=5_000,
            )
        )

    async with gateway.begin(scope) as uow:
        latest = await uow.estate.last_sweep("proxmox")
        none_for_other = await uow.estate.last_sweep("docker")

    assert latest is not None
    assert latest.sweep_id == "s-2"
    assert latest.outcome is SweepOutcome.SUSPENDED
    assert latest.cursor == "page-2"
    assert none_for_other is None


# --- Health --------------------------------------------------------------------


async def test_health_records_its_derivation_and_the_raw_provider_status(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource())
        updated = await uow.estate.record_health(
            "r-1", derivation(ResourceHealth.DEGRADED, raw_status="io-error")
        )

    assert updated.health is ResourceHealth.DEGRADED
    assert updated.derivation is not None
    assert updated.derivation.rule == "provider_status"
    assert updated.derivation.raw_status == "io-error"
    assert updated.derivation.signals[0].name == "provider_status"
    assert updated.derivation.signals[0].value == "io-error"


async def test_recording_the_same_state_twice_appends_one_transition(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-001: an unchanged source produces no spurious transitions."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource())
        await uow.estate.record_health("r-1", derivation(ResourceHealth.HEALTHY, minutes=0))
        await uow.estate.record_health("r-1", derivation(ResourceHealth.HEALTHY, minutes=15))
        await uow.estate.record_health("r-1", derivation(ResourceHealth.HEALTHY, minutes=30))

    async with gateway.begin(scope) as uow:
        history = await uow.estate.transitions("r-1")
        stored = await uow.estate.get("r-1")

    assert len(history) == 1
    assert stored is not None
    # The derivation still moves forward, so freshness is measured against the
    # last observation rather than against the last change.
    assert stored.derivation is not None
    assert stored.derivation.derived_at == at(30)


async def test_health_for_an_unknown_resource_raises(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        with pytest.raises(RecordNotFound):
            await uow.estate.record_health("r-nobody", derivation())


async def test_maintenance_is_bounded_distinct_and_clearable(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-008: in the estate, out of the problem count."""
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource())
        await uow.estate.record_health("r-1", derivation(ResourceHealth.UNHEALTHY))
        during = await uow.estate.set_maintenance(
            "r-1", until=at(30), reason="firmware upgrade", at=at(1)
        )

    assert during.reported_health(at(2)) is ResourceHealth.MAINTENANCE
    assert during.reported_health(at(2)) is not ResourceHealth.HEALTHY
    assert during.maintenance_reason == "firmware upgrade"
    # The window is bounded: past it, and while the observation is still fresh,
    # the stored state is what shows again.
    assert during.reported_health(at(31)) is ResourceHealth.UNHEALTHY

    async with gateway.begin(scope) as uow:
        cleared = await uow.estate.clear_maintenance("r-1", at=at(3))

    assert cleared.maintenance_until is None
    assert cleared.reported_health(at(4)) is ResourceHealth.UNHEALTHY


async def test_a_maintenance_window_longer_than_the_bound_raises(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource())
        with pytest.raises(BoundExceeded):
            await uow.estate.set_maintenance(
                "r-1", until=at(60 * 24 * 30), reason="forever", at=at()
            )


# --- Summary -------------------------------------------------------------------


async def test_the_summary_counts_maintenance_in_the_estate_and_out_of_the_problems(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource("r-ok", native_id="qemu/1"))
        await uow.estate.upsert(resource("r-bad", native_id="qemu/2"))
        await uow.estate.upsert(resource("r-maint", native_id="qemu/3"))
        await uow.estate.upsert(
            resource("r-node", kind="node", native_id="node/pve1", source="proxmox")
        )
        await uow.estate.upsert(resource("r-gone", native_id="qemu/4"))
        for resource_id, state in (
            ("r-ok", ResourceHealth.HEALTHY),
            ("r-bad", ResourceHealth.UNHEALTHY),
            ("r-maint", ResourceHealth.UNHEALTHY),
            ("r-node", ResourceHealth.HEALTHY),
        ):
            await uow.estate.record_health(resource_id, derivation(state))
        await uow.estate.set_maintenance("r-maint", until=at(60), reason="upgrade", at=at(1))
        await uow.estate.mark_absent(
            source="proxmox",
            seen_ids=frozenset({"r-ok", "r-bad", "r-maint", "r-node"}),
            at=at(2),
        )
        summary = await uow.estate.summarise(now=at(3))

    assert summary.total == 4
    assert summary.absent == 1
    assert summary.maintenance == 1
    assert summary.problems == 1
    assert summary.by_kind == {"node": 1, "virtual_machine": 3}
    assert summary.by_health[ResourceHealth.MAINTENANCE.value] == 1
    assert summary.captured_at == at(3)


# --- What referenced it --------------------------------------------------------


async def test_a_resource_links_to_the_runs_and_incidents_that_touched_it(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource())
        await uow.estate.link(
            ResourceReference(
                resource_id="r-1",
                reference_kind=ReferenceKind.RUN,
                reference_id="run-9",
                recorded_at=at(5),
                summary="restarted the guest",
            )
        )
        await uow.estate.link(
            ResourceReference(
                resource_id="r-1",
                reference_kind=ReferenceKind.INCIDENT,
                reference_id="inc-3",
                recorded_at=at(6),
            )
        )
        # Idempotent: the same reference twice is one row.
        await uow.estate.link(
            ResourceReference(
                resource_id="r-1",
                reference_kind=ReferenceKind.RUN,
                reference_id="run-9",
                recorded_at=at(7),
            )
        )

    async with gateway.begin(scope) as uow:
        every = await uow.estate.references("r-1")
        runs = await uow.estate.references("r-1", reference_kind=ReferenceKind.RUN)

    assert len(every) == 2
    assert [found.reference_id for found in runs] == ["run-9"]


# --- Tenancy -------------------------------------------------------------------


async def test_an_estate_is_not_visible_from_another_tenant(
    gateway: PersistenceGateway, scope: TenantScope, other_scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(resource())

    async with gateway.begin(other_scope) as uow:
        missing = await uow.estate.get("r-1")
        found = await uow.estate.query(EstateQuery())
        summary = await uow.estate.summarise(now=at())
        marked = await uow.estate.mark_absent(source="proxmox", seen_ids=frozenset(), at=at(10))

    assert missing is None
    assert found == ()
    assert summary.total == 0
    assert marked == ()


# --- Paging past the bound --------------------------------------------------------


async def test_a_cursor_resumes_where_the_last_page_stopped(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The keyset cursor: only resources sorting strictly after the one named."""
    async with gateway.begin(scope) as uow:
        for index in range(5):
            await uow.estate.upsert(
                Resource(
                    resource_id=f"res-{index}",
                    kind="container",
                    source="proxmox",
                    native_id=f"lxc/{index}",
                    first_seen_at=EPOCH,
                    last_seen_at=EPOCH,
                )
            )

        first = await uow.estate.query(EstateQuery(limit=2))
        second = await uow.estate.query(EstateQuery(limit=2, after=first[-1].resource_id))

    assert [resource.resource_id for resource in first] == ["res-0", "res-1"]
    assert [resource.resource_id for resource in second] == ["res-2", "res-3"]


async def test_a_whole_estate_pass_reaches_past_one_page(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """053's truncation, closed. An estate larger than a page is answerable now.

    Read with a page bound of two over five resources: without the cursor this
    is two resources and a caller that cannot tell that from an estate of two.
    """
    async with gateway.begin(scope) as uow:
        for index in range(5):
            await uow.estate.upsert(
                Resource(
                    resource_id=f"res-{index}",
                    kind="container",
                    source="proxmox",
                    native_id=f"lxc/{index}",
                    first_seen_at=EPOCH,
                    last_seen_at=EPOCH,
                )
            )

        everything = await whole_estate(uow.estate, EstateQuery(limit=2))

    assert [resource.resource_id for resource in everything] == [
        f"res-{index}" for index in range(5)
    ]


async def test_a_whole_estate_pass_stops_at_its_page_ceiling(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A bound, not a formality: a pass with no ceiling never returns.

    Returning what was read rather than raising, because a caller enriching what
    it got wants what it got — and the count reaching ``max_pages * limit`` is
    how it can tell it did not reach the end.
    """
    async with gateway.begin(scope) as uow:
        for index in range(5):
            await uow.estate.upsert(
                Resource(
                    resource_id=f"res-{index}",
                    kind="container",
                    source="proxmox",
                    native_id=f"lxc/{index}",
                    first_seen_at=EPOCH,
                    last_seen_at=EPOCH,
                )
            )

        capped = await whole_estate(uow.estate, EstateQuery(limit=2), max_pages=2)

    assert [resource.resource_id for resource in capped] == ["res-0", "res-1", "res-2", "res-3"]


async def test_a_whole_estate_pass_keeps_every_filter_the_query_declares(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        for index, source in enumerate(("proxmox", "kubernetes", "proxmox")):
            await uow.estate.upsert(
                Resource(
                    resource_id=f"res-{index}",
                    kind="container",
                    source=source,
                    native_id=f"lxc/{index}",
                    first_seen_at=EPOCH,
                    last_seen_at=EPOCH,
                )
            )

        found = await whole_estate(uow.estate, EstateQuery(sources=("proxmox",), limit=1))

    assert [resource.resource_id for resource in found] == ["res-0", "res-2"]
