"""One discovery pass: what it ingests, what it may conclude, and what it may not.

The assertions that matter here are all negative. A failed sweep marks nothing
absent. An incremental sweep marks nothing absent. A suspended sweep marks
nothing absent. Only a full sweep that a source said was complete is entitled to
decide that something is gone, and every other path in this file exists to prove
that the entitlement is not leaking.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from platform.estate.discovery.port import (
    DiscoveredResource,
    DiscoveryDeclaration,
    DiscoveryMode,
    DiscoveryPage,
    ResourceReader,
    SweepBudget,
)
from platform.estate.discovery.sweep import EstateSweeper
from platform.estate.identity import derive_resource_id
from platform.estate.kinds import KIND_NODE, KIND_VIRTUAL_MACHINE, core_registry
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    EstateQuery,
    PersistenceGateway,
    ResourceHealth,
    SweepOutcome,
    TenantScope,
)

pytestmark = pytest.mark.unit

ORG = "acme"
SOURCE = "proxmox"
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def guest(native_id: str, *, name: str = "", status: str = "running") -> DiscoveredResource:
    """Return a virtual machine as a hypervisor would report it."""
    return DiscoveredResource(
        kind=KIND_VIRTUAL_MACHINE,
        native_id=native_id,
        display_name=name or native_id,
        parent_native_id="node/pve1",
        attributes={"cores": 4, "memory_bytes": 8_589_934_592},
        provider_status=status,
        observed_at=at(),
    )


def node(native_id: str = "node/pve1") -> DiscoveredResource:
    """Return the node the guests hang from."""
    return DiscoveredResource(
        kind=KIND_NODE,
        native_id=native_id,
        display_name="pve1",
        attributes={"cpu_count": 16},
        provider_status="online",
        observed_at=at(),
    )


class Boom(RuntimeError):
    """What an integration client raises when the provider will not answer."""


@dataclass
class FakeReader:
    """A source whose pages, failures, and completeness a test decides.

    Holds no credential and has nowhere to put one, which is the property
    ``test_discovery_has_nowhere_to_put_a_credential`` reads off it.
    """

    pages: list[DiscoveryPage] = field(default_factory=list)
    supports_incremental: bool = False
    fails_with: Exception | None = None
    calls: list[tuple[DiscoveryMode, str]] = field(default_factory=list)

    @property
    def declaration(self) -> DiscoveryDeclaration:
        """Return what this source says about itself."""
        return DiscoveryDeclaration(
            integration=SOURCE,
            kinds=(KIND_NODE, KIND_VIRTUAL_MACHINE),
            supports_incremental=self.supports_incremental,
        )

    async def discover(
        self,
        *,
        mode: DiscoveryMode,
        cursor: str = "",
        budget: SweepBudget,
    ) -> DiscoveryPage:
        """Return the page this test lined up for ``cursor``."""
        self.calls.append((mode, cursor))
        if self.fails_with is not None:
            raise self.fails_with
        index = int(cursor) if cursor else 0
        return self.pages[index]


def one_page(*resources: DiscoveredResource, complete: bool = True) -> list[DiscoveryPage]:
    """Return a source that answers everything in a single call."""
    return [DiscoveryPage(resources=resources, complete=complete)]


@pytest.fixture
async def gateway() -> PersistenceGateway:
    """Return a store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return store


@pytest.fixture
def scope() -> TenantScope:
    """Return the tenant every sweep in this file runs for."""
    return TenantScope(org_id=ORG)


@pytest.fixture
def sweeper(gateway: PersistenceGateway) -> EstateSweeper:
    """Return a sweeper over the core kinds."""
    return EstateSweeper(gateway=gateway, kinds=core_registry())


# --- Ingestion -----------------------------------------------------------------


async def test_a_first_sweep_stores_what_the_source_reported(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    reader = FakeReader(pages=one_page(node(), guest("qemu/101", name="checkout")))

    report = await sweeper.sweep(scope, reader, now=at())

    assert report.outcome is SweepOutcome.SUCCEEDED
    assert report.discovered == 2
    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())
    assert {found.display_name for found in stored} == {"pve1", "checkout"}


async def test_a_parent_named_by_native_id_becomes_a_parent_reference(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    reader = FakeReader(pages=one_page(node(), guest("qemu/101")))

    await sweeper.sweep(scope, reader, now=at())

    async with gateway.begin(scope) as uow:
        child = await uow.estate.get(derive_resource_id(source=SOURCE, native_id="qemu/101"))
    assert child is not None
    assert child.parent_id == derive_resource_id(source=SOURCE, native_id="node/pve1")


async def test_sweeping_twice_against_an_unchanged_source_changes_nothing(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-001: no duplicates, and no spurious transitions."""
    reader = FakeReader(pages=one_page(node(), guest("qemu/101")))

    await sweeper.sweep(scope, reader, now=at())
    await sweeper.sweep(scope, reader, now=at(15))

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())
        history = await uow.estate.transitions(
            derive_resource_id(source=SOURCE, native_id="qemu/101")
        )
    assert len(stored) == 2
    assert len(history) == 1


async def test_an_attribute_the_kind_never_declared_is_dropped(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    invented = DiscoveredResource(
        kind=KIND_VIRTUAL_MACHINE,
        native_id="qemu/101",
        display_name="checkout",
        attributes={"cores": 2, "vendor_extension": "anything at all"},
        provider_status="running",
    )
    report = await sweeper.sweep(scope, FakeReader(pages=one_page(invented)), now=at())

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get(derive_resource_id(source=SOURCE, native_id="qemu/101"))
    assert stored is not None
    assert stored.attributes == {"cores": 2}
    assert "vendor_extension" in report.dropped_attributes


async def test_a_resource_of_an_undeclared_kind_is_skipped_and_named(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    reader = FakeReader(
        pages=one_page(
            node(),
            DiscoveredResource(kind="teapot", native_id="teapot/1", display_name="short"),
        )
    )

    report = await sweeper.sweep(scope, reader, now=at())

    assert report.skipped_kinds == ("teapot",)
    async with gateway.begin(scope) as uow:
        assert len(await uow.estate.query(EstateQuery())) == 1


async def test_a_resource_with_no_native_identifier_is_skipped_not_generated(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """T-020: rejected with a named error, never stored under a generated id."""
    reader = FakeReader(pages=one_page(node(), DiscoveredResource(kind=KIND_NODE, native_id="  ")))

    report = await sweeper.sweep(scope, reader, now=at())

    assert report.unidentified == 1
    async with gateway.begin(scope) as uow:
        assert len(await uow.estate.query(EstateQuery())) == 1


# --- Absence, and everything that must not cause it ----------------------------


async def test_a_complete_full_sweep_marks_the_gone_resource_absent(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    reader = FakeReader(pages=one_page(node(), guest("qemu/101"), guest("qemu/102")))
    await sweeper.sweep(scope, reader, now=at())

    reader.pages = one_page(node(), guest("qemu/101"))
    report = await sweeper.sweep(scope, reader, now=at(15))

    gone = derive_resource_id(source=SOURCE, native_id="qemu/102")
    assert report.absent == (gone,)
    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get(gone)
    assert stored is not None
    assert stored.absent_since == at(15)
    assert stored.reported_health(at(15)) is ResourceHealth.ABSENT


async def test_a_source_whose_clock_runs_slow_is_not_decommissioned(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """One of the spec's edge cases: clock skew between us and the source.

    ``last_seen_at`` is the sweep's own instant rather than the provider's
    reading time. Taking the provider's would make absence depend on whose
    clock is right — and a source whose clock runs an hour slow would have a
    resumed sweep decommission everything an earlier pass ingested.
    """
    behind = DiscoveredResource(
        kind=KIND_VIRTUAL_MACHINE,
        native_id="qemu/101",
        display_name="checkout",
        provider_status="running",
        observed_at=at(-600),
    )
    reader = FakeReader(pages=one_page(node(), behind))

    await sweeper.sweep(scope, reader, now=at())

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get(derive_resource_id(source=SOURCE, native_id="qemu/101"))

    assert stored is not None
    assert stored.last_seen_at == at()
    # The provider's own reading time is kept, on its contribution.
    assert stored.sources[0].observed_at == at(-600)


async def test_a_failed_sweep_marks_stale_and_nothing_absent(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-003, and the single most damaging bug this component can have."""
    reader = FakeReader(pages=one_page(node(), guest("qemu/101")))
    await sweeper.sweep(scope, reader, now=at())

    reader.fails_with = Boom("the API returned 503")
    report = await sweeper.sweep(scope, reader, now=at(15))

    assert report.outcome is SweepOutcome.FAILED
    assert report.absent == ()
    assert len(report.stale) == 2
    assert "503" in report.reason
    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())
    assert all(found.absent_since is None for found in stored)
    assert all(found.health is ResourceHealth.STALE for found in stored)


async def test_a_failed_sweep_leaves_another_integrations_resources_untouched(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    await sweeper.sweep(scope, FakeReader(pages=one_page(node(), guest("qemu/101"))), now=at())

    other = FakeReader(
        pages=one_page(
            DiscoveredResource(
                kind=KIND_NODE,
                native_id="host/1",
                display_name="docker-host",
                provider_status="online",
            )
        )
    )
    object.__setattr__(other, "integration_name", "docker")
    await sweeper.sweep(scope, other, now=at(1), source="docker")

    failing = FakeReader(pages=[], fails_with=Boom("gone"))
    await sweeper.sweep(scope, failing, now=at(15))

    async with gateway.begin(scope) as uow:
        untouched = await uow.estate.by_native_id(source="docker", native_id="host/1")
    assert untouched is not None
    assert untouched.health is not ResourceHealth.STALE


async def test_an_incremental_sweep_never_marks_anything_absent(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    reader = FakeReader(
        pages=one_page(node(), guest("qemu/101"), guest("qemu/102")),
        supports_incremental=True,
    )
    await sweeper.sweep(scope, reader, now=at(), mode=DiscoveryMode.FULL)

    # The delta mentions one guest. The other is not gone; it simply did not
    # change, which is what an incremental answer means.
    reader.pages = one_page(guest("qemu/101"))
    report = await sweeper.sweep(scope, reader, now=at(15), mode=DiscoveryMode.INCREMENTAL)

    assert report.mode is DiscoveryMode.INCREMENTAL
    assert report.absent == ()
    async with gateway.begin(scope) as uow:
        stored = await uow.estate.get(derive_resource_id(source=SOURCE, native_id="qemu/102"))
    assert stored is not None
    assert stored.absent_since is None


async def test_a_source_that_cannot_do_incremental_falls_back_to_a_full_sweep(
    sweeper: EstateSweeper, scope: TenantScope
) -> None:
    reader = FakeReader(pages=one_page(node()), supports_incremental=False)

    report = await sweeper.sweep(scope, reader, now=at(), mode=DiscoveryMode.INCREMENTAL)

    assert report.mode is DiscoveryMode.FULL
    assert reader.calls == [(DiscoveryMode.FULL, "")]


# --- Bounds --------------------------------------------------------------------


async def test_exceeding_the_resource_bound_suspends_and_resumes_at_the_cursor(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """T-012: suspended and resumed, never truncated."""
    first = DiscoveryPage(
        resources=(node(), guest("qemu/101")), complete=False, cursor="1", provider_calls=1
    )
    second = DiscoveryPage(resources=(guest("qemu/102"),), complete=True, provider_calls=1)
    reader = FakeReader(pages=[first, second])
    tight = SweepBudget(max_resources=2)

    suspended = await sweeper.sweep(scope, reader, now=at(), budget=tight)

    assert suspended.outcome is SweepOutcome.SUSPENDED
    assert suspended.cursor == "1"
    # A suspended sweep saw part of the estate, so it concludes nothing about
    # the part it did not see.
    assert suspended.absent == ()

    resumed = await sweeper.sweep(scope, reader, now=at(1))

    assert resumed.outcome is SweepOutcome.SUCCEEDED
    assert reader.calls[-1] == (DiscoveryMode.FULL, "1")
    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())
    assert len(stored) == 3


async def test_exceeding_the_provider_call_bound_suspends(
    sweeper: EstateSweeper, scope: TenantScope
) -> None:
    pages = [
        DiscoveryPage(
            resources=(guest(f"qemu/{n}"),), complete=False, cursor=str(n), provider_calls=1
        )
        for n in range(1, 5)
    ]
    reader = FakeReader(
        pages=[DiscoveryPage(resources=(node(),), complete=False, cursor="1")] + pages
    )

    report = await sweeper.sweep(scope, reader, now=at(), budget=SweepBudget(max_provider_calls=2))

    assert report.outcome is SweepOutcome.SUSPENDED
    assert report.provider_calls <= 2


async def test_exceeding_the_time_bound_suspends(
    sweeper: EstateSweeper, scope: TenantScope
) -> None:
    ticks = iter([at(), at(2), at(4), at(6), at(8), at(10)])
    slow = EstateSweeper(
        gateway=sweeper.gateway, kinds=core_registry(), clock=lambda: next(ticks, at(10))
    )
    reader = FakeReader(
        pages=[
            DiscoveryPage(resources=(node(),), complete=False, cursor="1"),
            DiscoveryPage(resources=(guest("qemu/101"),), complete=True),
        ]
    )

    report = await slow.sweep(scope, reader, now=at(), budget=SweepBudget(max_seconds=30.0))

    assert report.outcome is SweepOutcome.SUSPENDED


# --- Convergence ---------------------------------------------------------------


async def test_two_replicas_sweeping_concurrently_converge_to_one_result(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-007. Identity and transition keys are derived, so a race has one answer."""
    resources = (node(), guest("qemu/101"), guest("qemu/102"))
    first = EstateSweeper(gateway=gateway, kinds=core_registry())
    second = EstateSweeper(gateway=gateway, kinds=core_registry())

    await first.sweep(scope, FakeReader(pages=one_page(*resources)), now=at())
    await second.sweep(scope, FakeReader(pages=one_page(*resources)), now=at())

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())
        history = await uow.estate.transitions(
            derive_resource_id(source=SOURCE, native_id="qemu/101")
        )
    assert len(stored) == 3
    assert len(history) == 1


async def test_two_replicas_both_concluding_an_absence_record_it_once(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    sweeper = EstateSweeper(gateway=gateway, kinds=core_registry())
    await sweeper.sweep(scope, FakeReader(pages=one_page(node(), guest("qemu/101"))), now=at())

    gone = FakeReader(pages=one_page(node()))
    await sweeper.sweep(scope, gone, now=at(15))
    await EstateSweeper(gateway=gateway, kinds=core_registry()).sweep(scope, gone, now=at(15))

    absent = derive_resource_id(source=SOURCE, native_id="qemu/101")
    async with gateway.begin(scope) as uow:
        history = await uow.estate.transitions(absent)
        stored = await uow.estate.get(absent)
    assert stored is not None
    assert stored.absent_since == at(15)
    assert [entry.state for entry in history].count(ResourceHealth.ABSENT) == 1


# --- The credential boundary (NFR-003) -----------------------------------------


def test_discovery_has_nowhere_to_put_a_credential() -> None:
    """T-011: the protocol has no parameter a secret could arrive in."""
    parameters = set(inspect.signature(ResourceReader.discover).parameters)

    assert parameters == {"self", "mode", "cursor", "budget"}


def test_the_sweep_takes_no_credential_either() -> None:
    forbidden = {"token", "secret", "password", "credential", "key", "api_key", "auth"}

    for method in (EstateSweeper.__init__, EstateSweeper.sweep):
        names = {name.lower() for name in inspect.signature(method).parameters}
        assert not names & forbidden, f"{method.__qualname__} accepts a credential-shaped argument"


def test_the_sweep_module_imports_nothing_from_the_credential_layer() -> None:
    """A structural check, because an import is how the boundary would be crossed."""
    import platform.estate.discovery.sweep as module

    source = inspect.getsource(module)

    assert "platform.credentials" not in source
    assert "reveal" not in source


# --- The sweep record ----------------------------------------------------------


async def test_every_sweep_is_recorded_with_what_it_cost(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    await sweeper.sweep(scope, FakeReader(pages=one_page(node(), guest("qemu/101"))), now=at())

    async with gateway.begin(scope) as uow:
        recorded = await uow.estate.last_sweep(SOURCE)

    assert recorded is not None
    assert recorded.outcome is SweepOutcome.SUCCEEDED
    assert recorded.seen_count == 2
    assert recorded.provider_calls == 1
    assert recorded.completed_at is not None
