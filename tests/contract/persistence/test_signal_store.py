"""Contract: the signal history, and the four things a backend must never get wrong.

Appending the same observation twice is one sample, a window returns exactly the
samples inside it in the order a detector reads them, the retention sweep
removes what no window still reaches, and one tenant's observations are
invisible from another.

The first of those is the load-bearing one. A signal store that let a retry
double a sample would make every average over a window wrong by an amount
nobody could see, and the detectors that read those windows would fire on the
retry rather than on the estate.
"""

from __future__ import annotations

import pytest
from conftest import at

from platform.persistence.errors import BoundExceeded
from platform.persistence.ports import (
    PersistenceGateway,
    Signal,
    SignalKind,
    SignalQuery,
    SignalStore,
    TenantScope,
)
from platform.persistence.ports.signal_store import retention_seconds, signal_key

pytestmark = pytest.mark.contract


def sample(
    *,
    name: str = "storage.used_percent",
    resource_id: str = "store-cove",
    minutes: float = 0.0,
    value: float = 50.0,
    source: str = "poller:proxmox",
    interval_seconds: int = 60,
) -> Signal:
    """Return one numeric observation, keyed the way every writer keys one."""
    observed_at = at(minutes)
    return Signal(
        signal_id=signal_key(name, resource_id, observed_at),
        name=name,
        resource_id=resource_id,
        source=source,
        kind=SignalKind.NUMBER,
        observed_at=observed_at,
        value=value,
        interval_seconds=interval_seconds,
        labels={"node": "node01"},
    )


# --- Appending -----------------------------------------------------------------


async def test_a_sample_appended_twice_is_one_sample(gateway: PersistenceGateway) -> None:
    """A retry, a restart, and a second replica all write the same row."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        signals: SignalStore = uow.signals
        await signals.append([sample()])
        await signals.append([sample()])

        stored = await signals.window(SignalQuery(names=("storage.used_percent",)))

    assert len(stored) == 1
    assert stored[0].value == 50.0


async def test_a_second_reading_at_a_later_instant_is_a_second_sample(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(minutes=0, value=50.0), sample(minutes=1, value=51.0)])
        stored = await uow.signals.window(SignalQuery())

    assert [entry.value for entry in stored] == [50.0, 51.0]


async def test_a_window_returns_oldest_first(gateway: PersistenceGateway) -> None:
    """A rate of change over a reversed window is the right size with the wrong sign."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(
            [sample(minutes=2, value=52.0), sample(minutes=0, value=50.0), sample(minutes=1)]
        )
        stored = await uow.signals.window(SignalQuery())

    assert [entry.observed_at for entry in stored] == [at(0), at(1), at(2)]


# --- Querying a window ----------------------------------------------------------


async def test_a_window_excludes_what_falls_outside_it(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(minutes=minute) for minute in (0, 5, 10, 15)])

        inside = await uow.signals.window(SignalQuery(since=at(5), until=at(10)))

    assert [entry.observed_at for entry in inside] == [at(5), at(10)]


async def test_a_window_filters_by_name_resource_and_source(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(
            [
                sample(name="storage.used_percent", resource_id="store-cove"),
                sample(name="storage.used_percent", resource_id="store-ridge"),
                sample(name="node.load", resource_id="store-cove"),
                sample(name="storage.used_percent", resource_id="store-cove", source="metrics"),
            ]
        )

        by_name = await uow.signals.window(SignalQuery(names=("node.load",)))
        by_resource = await uow.signals.window(SignalQuery(resource_ids=("store-ridge",)))
        by_source = await uow.signals.window(SignalQuery(sources=("metrics",)))

    assert [entry.name for entry in by_name] == ["node.load"]
    assert [entry.resource_id for entry in by_resource] == ["store-ridge"]
    assert [entry.source for entry in by_source] == ["metrics"]


async def test_a_window_above_the_page_bound_is_refused(gateway: PersistenceGateway) -> None:
    """Raising rather than clamping: a verdict must not depend on paging."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        with pytest.raises(BoundExceeded, match="MAX_SIGNAL_PAGE_SIZE"):
            await uow.signals.window(SignalQuery(limit=100_000))


# --- Silence --------------------------------------------------------------------


async def test_the_latest_sample_is_returned_however_old_it_is(
    gateway: PersistenceGateway,
) -> None:
    """The read that makes "it stopped reporting" answerable at all."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(minutes=-600), sample(minutes=-500)])

        recent = await uow.signals.window(SignalQuery(since=at(-10)))
        latest = await uow.signals.latest(names=("storage.used_percent",))

    assert recent == ()
    assert [entry.observed_at for entry in latest] == [at(-500)]


async def test_the_latest_is_one_sample_per_name_and_resource(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(
            [
                sample(resource_id="store-cove", minutes=0),
                sample(resource_id="store-cove", minutes=3),
                sample(resource_id="store-ridge", minutes=1),
                sample(name="node.load", resource_id="store-cove", minutes=2),
            ]
        )

        latest = await uow.signals.latest()

    assert sorted((entry.name, entry.resource_id, entry.observed_at) for entry in latest) == [
        ("node.load", "store-cove", at(2)),
        ("storage.used_percent", "store-cove", at(3)),
        ("storage.used_percent", "store-ridge", at(1)),
    ]


async def test_a_source_that_promised_nothing_is_never_silent() -> None:
    """Nothing can be concluded from the silence of something that never spoke."""
    promised = sample(interval_seconds=60, minutes=-60)
    unpromised = sample(interval_seconds=0, minutes=-60)

    assert promised.is_silent_at(at())
    assert not unpromised.is_silent_at(at())


async def test_one_missed_report_is_not_silence() -> None:
    """Three intervals, because a single hiccup would page somebody nightly."""
    signal = sample(interval_seconds=60, minutes=-1.5)

    assert not signal.is_silent_at(at())
    assert sample(interval_seconds=60, minutes=-4).is_silent_at(at())


# --- Retention ------------------------------------------------------------------


async def test_the_sweep_removes_only_what_no_window_still_reaches(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(minutes=minute) for minute in (-120, -60, -1)])

        removed = await uow.signals.prune(before=at(-30))
        left = await uow.signals.latest()

    assert removed == 2
    assert [entry.observed_at for entry in left] == [at(-1)]


def test_retention_is_the_longest_declared_window_and_no_longer() -> None:
    """An operator who lengthens a window must not have to remember retention."""
    assert retention_seconds([300, 3_600, 900]) == 3_600


def test_a_deployment_with_no_detectors_still_bounds_its_table() -> None:
    assert retention_seconds([]) > 0


# --- Tenancy ---------------------------------------------------------------------


async def test_one_tenants_observations_are_invisible_from_another(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample()])

    async with gateway.begin(TenantScope(org_id="globex")) as other:
        assert await other.signals.window(SignalQuery()) == ()
        assert await other.signals.latest() == ()


async def test_a_sweep_in_one_tenant_leaves_another_alone(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="globex")) as uow:
        await uow.signals.append([sample(minutes=-120)])

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(minutes=-120)])
        assert await uow.signals.prune(before=at(-30)) == 1

    async with gateway.begin(TenantScope(org_id="globex")) as other:
        assert len(await other.signals.latest()) == 1
