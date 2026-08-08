"""SC-006: a summary and a query over ten thousand resources, inside their budget.

The number this defends is the one on the first screen an operator sees. An
estate summary that takes four seconds is a dashboard nobody leaves open, and a
dashboard nobody leaves open is a dashboard that does not tell anybody anything.

Three properties, and each of them is a different way the summary could be fast
in a benchmark and slow in a deployment.

**The summary is one pass.** Nine counts, one walk. Assembling it from nine
queries would meet no budget at any size worth having.

**A filtered query does not degrade with the estate.** Asking for one kind out
of ten thousand resources costs what asking for one kind costs, not what the
estate costs.

**Freshness is applied without a second pass.** The overlay that turns an aged
observation into ``stale`` is computed per resource during the same walk, so the
budget covers the answer an operator actually reads rather than the raw one.

This runs against the in-memory backend, which is what makes it cheap enough for
every commit. It is a floor rather than a ceiling: the same shapes over
PostgreSQL are measured by ``tests/contract/persistence/test_estate_scale.py``,
under ``make test-postgres``, where the row hydration and the round trip are
real and this file has neither.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.estate import (
    ESTATE_DISCOVERY_BUDGET_SECONDS,
    ESTATE_SUMMARY_BUDGET_RESOURCES,
    ESTATE_SUMMARY_BUDGET_SECONDS,
    MAX_ESTATE_PAGE_SIZE,
)
from platform.estate.discovery.port import (
    DiscoveredResource,
    DiscoveryDeclaration,
    DiscoveryMode,
    DiscoveryPage,
    SweepBudget,
)
from platform.estate.discovery.sweep import EstateSweeper
from platform.estate.kinds import (
    KIND_CONTAINER,
    KIND_DATASTORE,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
    core_registry,
)
from platform.estate.service import EstateService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    EstateQuery,
    HealthDerivation,
    PersistenceGateway,
    Resource,
    ResourceHealth,
    SweepOutcome,
    TenantScope,
)

pytestmark = pytest.mark.benchmark

ORG = "acme"
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

#: The estate size the budget is declared against.
RESOURCE_COUNT = ESTATE_SUMMARY_BUDGET_RESOURCES

#: Cycled so the summary has something to count in every bucket rather than one
#: kind repeated ten thousand times, which would be a benchmark of one branch.
KINDS = (KIND_VIRTUAL_MACHINE, KIND_CONTAINER, KIND_DATASTORE, KIND_NODE)
STATES = (
    ResourceHealth.HEALTHY,
    ResourceHealth.HEALTHY,
    ResourceHealth.DEGRADED,
    ResourceHealth.UNHEALTHY,
    ResourceHealth.UNKNOWN,
)


@pytest.fixture(scope="module")
def seeded() -> PersistenceGateway:
    """Return a store holding a ten-thousand-resource estate.

    Seeded once for the module. Building it per test would make the fixture the
    thing being measured.
    """
    import asyncio

    store = FakePersistence()

    async def build() -> None:
        async with store.begin_system() as system:
            await system.orgs.create_organisation(ORG, "Acme")
        async with store.begin(TenantScope(org_id=ORG)) as uow:
            for index in range(RESOURCE_COUNT):
                kind = KINDS[index % len(KINDS)]
                state = STATES[index % len(STATES)]
                resource_id = f"res-{index:06d}"
                await uow.estate.upsert(
                    Resource(
                        resource_id=resource_id,
                        kind=kind,
                        source="proxmox" if index % 2 else "docker",
                        native_id=f"native/{index}",
                        display_name=f"resource-{index}",
                        labels=("env:prod",) if index % 3 == 0 else (),
                        health=state,
                        derivation=HealthDerivation(
                            state=state,
                            rule="provider_status",
                            derived_at=EPOCH,
                            raw_status=state.value,
                        ),
                        first_seen_at=EPOCH,
                        last_seen_at=EPOCH,
                    )
                )

    asyncio.run(build())
    return store


@pytest.fixture(scope="module")
def service(seeded: PersistenceGateway) -> EstateService:
    """Return the estate service over the seeded store."""
    return EstateService(gateway=seeded, kinds=core_registry())


def _elapsed(started: float) -> float:
    return time.perf_counter() - started


async def test_the_estate_really_holds_ten_thousand_resources(
    seeded: PersistenceGateway,
) -> None:
    """The budget assertions below would all pass against an empty store."""
    async with seeded.begin(TenantScope(org_id=ORG)) as uow:
        summary = await uow.estate.summarise(now=EPOCH)

    assert summary.total == RESOURCE_COUNT
    assert set(summary.by_kind) == set(KINDS)
    assert summary.problems == RESOURCE_COUNT * 2 // len(STATES)


async def test_a_ten_thousand_resource_summary_answers_within_budget(
    service: EstateService,
) -> None:
    """SC-006."""
    scope = TenantScope(org_id=ORG)
    started = time.perf_counter()
    summary = await service.summarise(scope, now=EPOCH + timedelta(minutes=1))
    elapsed = _elapsed(started)

    assert summary.total == RESOURCE_COUNT
    assert elapsed < ESTATE_SUMMARY_BUDGET_SECONDS, (
        f"the summary took {elapsed:.3f}s against a budget of "
        f"{ESTATE_SUMMARY_BUDGET_SECONDS}s at {RESOURCE_COUNT} resources"
    )


async def test_the_summary_still_answers_within_budget_once_everything_is_stale(
    service: EstateService,
) -> None:
    """The freshness overlay is per resource, so it is the case worth measuring."""
    scope = TenantScope(org_id=ORG)
    long_after = EPOCH + timedelta(days=30)

    started = time.perf_counter()
    summary = await service.summarise(scope, now=long_after)
    elapsed = _elapsed(started)

    assert summary.by_health[ResourceHealth.STALE.value] == RESOURCE_COUNT
    assert summary.problems == 0
    assert elapsed < ESTATE_SUMMARY_BUDGET_SECONDS


async def test_a_filtered_query_over_the_whole_estate_answers_within_budget(
    service: EstateService,
) -> None:
    scope = TenantScope(org_id=ORG)
    started = time.perf_counter()
    found = await service.query(
        scope,
        EstateQuery(
            kinds=(KIND_VIRTUAL_MACHINE,),
            health=(ResourceHealth.UNHEALTHY,),
            labels=("env:prod",),
            limit=MAX_ESTATE_PAGE_SIZE,
        ),
        now=EPOCH + timedelta(minutes=1),
    )
    elapsed = _elapsed(started)

    assert found, "the filter matched nothing, so the timing measures nothing"
    assert all(view.resource.kind == KIND_VIRTUAL_MACHINE for view in found)
    assert elapsed < ESTATE_SUMMARY_BUDGET_SECONDS


async def test_a_query_returns_no_more_than_the_page_bound(
    service: EstateService,
) -> None:
    """Ten thousand resources must not arrive in one response."""
    scope = TenantScope(org_id=ORG)
    found = await service.query(scope, EstateQuery(limit=MAX_ESTATE_PAGE_SIZE), now=EPOCH)

    assert len(found) == MAX_ESTATE_PAGE_SIZE


# --- Discovering them in the first place ---------------------------------------


@dataclass
class BulkReader:
    """A source that reports ten thousand guests in pages of a thousand.

    The spec's own edge case: a first connection where the whole estate arrives
    at once. The mitigation is that the sweep *suspends and resumes* rather than
    that the bound is raised until the first connection fits inside it, so what
    this measures is the whole chain of passes rather than one of them.
    """

    total: int = RESOURCE_COUNT
    page_size: int = 1_000
    pages_read: int = 0

    @property
    def declaration(self) -> DiscoveryDeclaration:
        """Return what this source says about itself."""
        return DiscoveryDeclaration(integration="proxmox", kinds=(KIND_NODE, KIND_CONTAINER))

    async def discover(
        self,
        *,
        mode: DiscoveryMode,
        cursor: str = "",
        budget: SweepBudget,
    ) -> DiscoveryPage:
        """Return the next thousand guests."""
        self.pages_read += 1
        start = int(cursor) if cursor else 0
        stop = min(start + self.page_size, self.total)
        return DiscoveryPage(
            resources=tuple(
                DiscoveredResource(
                    kind=KIND_CONTAINER,
                    native_id=f"ct/{index}",
                    display_name=f"guest-{index:05d}",
                    attributes={"cores": 2, "memory_bytes": 1_073_741_824},
                    provider_status="running" if index % 7 else "stopped",
                    observed_at=EPOCH,
                )
                for index in range(start, stop)
            ),
            complete=stop >= self.total,
            cursor="" if stop >= self.total else str(stop),
        )


async def test_ten_thousand_resources_arriving_at_once_are_discovered_and_summarised() -> None:
    """The other half of the budget: discovered, not only read back.

    A first connection reporting the whole estate is bounded rather than
    refused: the sweep takes what its budget allows, suspends at a cursor, and
    the next one resumes. What must not happen — and what this asserts — is that
    the pass which finally completes decommissions everything the earlier passes
    ingested, because it holds only its own identifiers.
    """
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    scope = TenantScope(org_id=ORG)
    sweeper = EstateSweeper(gateway=store, kinds=core_registry())
    reader = BulkReader()

    started = time.perf_counter()
    passes = 0
    outcome = SweepOutcome.SUSPENDED
    while outcome is SweepOutcome.SUSPENDED and passes < 10:
        passes += 1
        report = await sweeper.sweep(scope, reader, now=EPOCH + timedelta(minutes=passes))
        outcome = report.outcome
    elapsed = _elapsed(started)

    assert outcome is SweepOutcome.SUCCEEDED, f"the sweep never completed after {passes} passes"
    # More than one pass, or the resource bound is not being exercised at all.
    assert passes > 1

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        summary = await uow.estate.summarise(now=EPOCH + timedelta(minutes=passes))

    assert summary.total == RESOURCE_COUNT
    assert summary.absent == 0, "the completing pass decommissioned what an earlier one ingested"
    assert summary.problems == RESOURCE_COUNT // 7 + 1
    assert elapsed < ESTATE_DISCOVERY_BUDGET_SECONDS, (
        f"discovering {RESOURCE_COUNT} resources took {elapsed:.1f}s against a budget of "
        f"{ESTATE_DISCOVERY_BUDGET_SECONDS}s"
    )
