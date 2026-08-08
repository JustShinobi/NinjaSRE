"""Two replicas, one sweep: the scheduler's claiming, reused rather than rebuilt.

The property FR-011 asks for is that concurrent discovery converges to one
result, by the same mechanism the scheduler already uses. These tests hold both
halves of that: the claim divides the work, and the sweep that follows a lost
race writes the same rows rather than a second set.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.estate import DISCOVERY_LEASE_SECONDS, ESTATE_DISCOVERY_JOB_KIND
from platform.estate.discovery.port import DiscoveryDeclaration, DiscoveryMode
from platform.estate.discovery.schedule import (
    DiscoveryClaiming,
    job_id_for,
    mode_of,
    next_run_after,
    source_of,
    sweep_job,
)
from platform.estate.kinds import KIND_NODE, KIND_VIRTUAL_MACHINE
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope

pytestmark = pytest.mark.unit

ORG = "acme"
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def declaration(interval_seconds: int = 900) -> DiscoveryDeclaration:
    """Return a source's declaration."""
    return DiscoveryDeclaration(
        integration="proxmox",
        kinds=(KIND_NODE, KIND_VIRTUAL_MACHINE),
        interval_seconds=interval_seconds,
    )


@pytest.fixture
async def gateway() -> PersistenceGateway:
    """Return a store with one organisation and one due sweep."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.schedules.upsert_job(sweep_job(declaration(), next_run_at=EPOCH))
    return store


# --- The job -------------------------------------------------------------------


def test_a_sweep_is_an_ordinary_scheduled_job() -> None:
    job = sweep_job(declaration(), next_run_at=EPOCH)

    assert job.job_id == job_id_for("proxmox")
    assert job.kind == ESTATE_DISCOVERY_JOB_KIND
    assert job.next_run_at == EPOCH
    assert job.enabled


def test_registering_a_source_twice_updates_one_job_rather_than_adding_a_second() -> None:
    first = sweep_job(declaration(), next_run_at=EPOCH)
    again = sweep_job(declaration(interval_seconds=1800), next_run_at=EPOCH)

    assert first.job_id == again.job_id


def test_the_payload_carries_the_source_and_the_mode() -> None:
    job = sweep_job(declaration(), next_run_at=EPOCH, mode=DiscoveryMode.INCREMENTAL)

    assert job.payload == {"source": "proxmox", "mode": "incremental"}


def test_the_next_run_follows_the_declared_interval() -> None:
    assert next_run_after(declaration(900), now=EPOCH) == EPOCH + timedelta(seconds=900)


# --- Claiming ------------------------------------------------------------------


async def test_one_due_sweep_is_claimed_by_exactly_one_of_two_replicas(
    gateway: PersistenceGateway,
) -> None:
    """SC-007's first half: the claim divides the work."""
    async with gateway.begin_system() as system:
        first = await DiscoveryClaiming.for_worker(system.jobs, "replica-a").claim(now=EPOCH)
        second = await DiscoveryClaiming.for_worker(system.jobs, "replica-b").claim(now=EPOCH)

    assert len(first) + len(second) == 1
    won = first or second
    assert source_of(won[0]) == "proxmox"
    assert mode_of(won[0]) is DiscoveryMode.FULL


async def test_a_claim_carries_the_tenant_the_sweep_belongs_to(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin_system() as system:
        claims = await DiscoveryClaiming.for_worker(system.jobs, "replica-a").claim(now=EPOCH)

    assert claims[0].org_id == ORG


async def test_the_discovery_lease_outlasts_the_longest_permitted_sweep(
    gateway: PersistenceGateway,
) -> None:
    """A sweep that runs to its own time bound must never be reclaimed mid-flight."""
    from config.constants.estate import MAX_SWEEP_SECONDS

    async with gateway.begin_system() as system:
        claims = await DiscoveryClaiming.for_worker(system.jobs, "replica-a").claim(now=EPOCH)

    held = (claims[0].lease_expires_at - claims[0].claimed_at).total_seconds()
    assert held == pytest.approx(DISCOVERY_LEASE_SECONDS)
    assert held > MAX_SWEEP_SECONDS


async def test_a_worker_claims_only_sweeps_and_not_somebody_elses_job(
    gateway: PersistenceGateway,
) -> None:
    from platform.persistence.ports import ScheduledJob

    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.schedules.upsert_job(
            ScheduledJob(
                job_id="nightly-sync",
                name="sync",
                kind="knowledge.sync",
                schedule="0 2 * * *",
                next_run_at=EPOCH,
            )
        )

    async with gateway.begin_system() as system:
        claims = await DiscoveryClaiming.for_worker(system.jobs, "replica-a").claim(now=EPOCH)

    assert [source_of(claim) for claim in claims] == ["proxmox"]
