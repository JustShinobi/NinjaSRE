"""Cleanup that is safe across replicas, and a pool that is safe across tenants.

The two modules here are the ones where a race is a security bug rather than a
performance one, so most of these tests run something concurrently and assert
that exactly one of the racers won.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from config.constants.security import (
    SANDBOX_INVESTIGATION_LABEL,
    SANDBOX_ORG_LABEL,
    SANDBOX_STATE_LABEL,
    SANDBOX_TEAM_LABEL,
)
from platform.sandbox import (
    EgressPolicy,
    ExecutionRequest,
    ReapableInstance,
    Reaper,
    SandboxProfile,
    SandboxSpec,
)
from platform.sandbox.port import SandboxState
from platform.sandbox.profiles.kubernetes import claims
from platform.sandbox.profiles.kubernetes.runner import KubernetesSandbox
from platform.sandbox.profiles.process.runner import ProcessSandbox
from platform.sandbox.trace import CollectingSandboxEvents, SandboxEventKind

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "contract" / "sandbox"))

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _api():  # type: ignore[no-untyped-def]
    """Return a simulated cluster, imported where the path has been set up."""
    from engines import SimulatedKubernetesApi

    return SimulatedKubernetesApi()


def _spec(investigation: str, *, team: str = "platform", org: str = "acme") -> SandboxSpec:
    """Return a spec for one investigation."""
    return SandboxSpec(
        org_id=org,
        team_id=team,
        investigation_id=investigation,
        egress=EgressPolicy(proxy_url="http://127.0.0.1:8081"),
        image="ninjasre/sandbox:test",
    )


class _Source:
    """A reapable source whose leases and deletes can be observed."""

    def __init__(self, instances: tuple[ReapableInstance, ...]) -> None:
        self.instances = list(instances)
        self.leases: dict[str, str] = {}
        self.destroyed: list[str] = []
        self.fail: set[str] = set()
        self._lock = asyncio.Lock()

    async def list_reapable(self) -> tuple[ReapableInstance, ...]:
        return tuple(self.instances)

    async def acquire_lease(
        self, sandbox_id: str, *, holder: str, lease_seconds: float, now: datetime
    ) -> bool:
        async with self._lock:
            if sandbox_id in self.leases:
                return False
            self.leases[sandbox_id] = holder
            return True

    async def destroy(self, sandbox_id: str) -> None:
        if sandbox_id in self.fail:
            raise RuntimeError("the cluster refused the delete")
        self.destroyed.append(sandbox_id)


def _reapable(sandbox_id: str, *, investigation: str, expires_in: float, pooled: bool = False):  # type: ignore[no-untyped-def]
    """Return one reapable instance expiring ``expires_in`` seconds from ``NOW``."""
    return ReapableInstance(
        sandbox_id=sandbox_id,
        org_id="acme",
        team_id="platform",
        investigation_id=investigation,
        expires_at=NOW + timedelta(seconds=expires_in),
        profile=SandboxProfile.KUBERNETES,
        pooled=pooled,
    )


async def test_the_reaper_removes_what_has_expired_and_leaves_what_has_not() -> None:
    source = _Source(
        (
            _reapable("live", investigation="inv-1", expires_in=300),
            _reapable("stale", investigation="inv-1", expires_in=-1),
        )
    )
    report = await Reaper(source).sweep(live_runs={"inv-1"}, now=NOW)

    assert report.expired == ("stale",)
    assert report.orphaned == ()
    assert source.destroyed == ["stale"]
    assert report.clean


async def test_the_reaper_collects_an_orphan_before_its_ttl_elapses() -> None:
    """A killed agent leaves no orphans after one sweep, rather than after a TTL."""
    source = _Source(
        (
            _reapable("owned", investigation="inv-live", expires_in=600),
            _reapable("orphan", investigation="inv-killed", expires_in=600),
        )
    )
    report = await Reaper(source).sweep(live_runs={"inv-live"}, now=NOW)

    assert report.orphaned == ("orphan",)
    assert source.destroyed == ["orphan"]


async def test_a_pooled_instance_is_not_an_orphan() -> None:
    """An idle pool member belongs to no investigation on purpose."""
    source = _Source((_reapable("idle", investigation="", expires_in=600, pooled=True),))
    report = await Reaper(source).sweep(live_runs={"inv-live"}, now=NOW)

    assert report.destroyed == ()
    assert source.destroyed == []


async def test_two_reapers_sweeping_together_delete_each_instance_once() -> None:
    """Concurrency safety is the requirement, so it is asserted concurrently."""
    source = _Source(
        tuple(_reapable(f"s{n}", investigation="gone", expires_in=-1) for n in range(8))
    )
    first, second = Reaper(source, holder="a"), Reaper(source, holder="b")

    reports = await asyncio.gather(
        first.sweep(live_runs=set(), now=NOW), second.sweep(live_runs=set(), now=NOW)
    )

    assert sorted(source.destroyed) == [f"s{n}" for n in range(8)]
    assert len(source.destroyed) == len(set(source.destroyed))
    assert sum(len(report.destroyed) for report in reports) == 8
    assert sum(len(report.skipped_leased) for report in reports) == 8


async def test_one_failed_delete_does_not_end_the_sweep() -> None:
    source = _Source(
        (
            _reapable("bad", investigation="gone", expires_in=-1),
            _reapable("good", investigation="gone", expires_in=-1),
        )
    )
    source.fail = {"bad"}
    report = await Reaper(source).sweep(live_runs=set(), now=NOW)

    assert source.destroyed == ["good"]
    assert not report.clean
    assert report.failures and "bad" in report.failures[0]


async def test_reaping_is_recorded_with_the_reason_it_happened() -> None:
    events = CollectingSandboxEvents()
    source = _Source(
        (
            _reapable("stale", investigation="gone", expires_in=-1),
            _reapable("orphan", investigation="killed", expires_in=600),
        )
    )
    await Reaper(source, events=events).sweep(live_runs=set(), now=NOW)

    kinds = {event.kind for event in events.events}
    assert kinds == {SandboxEventKind.EXPIRED, SandboxEventKind.REAPED}
    assert all(event.reason for event in events.events)


async def test_a_process_sandbox_reaped_mid_run_leaves_nothing_behind(tmp_path: Path) -> None:
    """The same, end to end, on the profile whose sandboxes are real directories."""
    sandbox = ProcessSandbox(namespace_available=False)
    instance = await sandbox.provision(_spec("inv-killed"))
    scratch = Path(instance.scratch_path)
    assert scratch.is_dir()

    running = asyncio.create_task(
        sandbox.execute(
            instance,
            ExecutionRequest(command=(sys.executable, "-I", "-c", "import time; time.sleep(600)")),
        )
    )
    await asyncio.sleep(0.2)

    report = await Reaper(sandbox).sweep(live_runs=set())
    running.cancel()
    await asyncio.gather(running, return_exceptions=True)

    assert report.orphaned == (instance.sandbox_id,)
    assert not scratch.exists()
    assert await sandbox.list_reapable() == ()


async def test_the_warm_pool_hands_one_idle_instance_to_one_investigation() -> None:
    """A claim is exclusive, and it is what gives an instance a tenant at all."""
    api = _api()
    sandbox = KubernetesSandbox(api=api, pool_size=2)
    assert await sandbox.pool.replenish() == 2
    assert (await sandbox.pool_status()).idle == 2

    first = await sandbox.pool.claim(_spec("inv-1"))
    assert first is not None
    assert first.investigation_id == "inv-1"
    assert (await sandbox.pool_status()).idle == 1

    second = await sandbox.pool.claim(_spec("inv-2"))
    assert second is not None
    assert second.pod != first.pod


async def test_two_investigations_racing_for_one_instance_produce_one_claim() -> None:
    api = _api()
    sandbox = KubernetesSandbox(api=api, pool_size=1)
    await sandbox.pool.replenish()

    results = await asyncio.gather(
        sandbox.pool.claim(_spec("inv-a")), sandbox.pool.claim(_spec("inv-b"))
    )
    assert sum(1 for result in results if result is not None) == 1


async def test_a_claimed_instance_is_never_offered_to_another_tenant() -> None:
    """The single-tenant guarantee, checked at bind rather than assumed."""
    api = _api()
    sandbox = KubernetesSandbox(api=api, pool_size=1)
    await sandbox.pool.replenish()

    mine = await sandbox.pool.claim(_spec("inv-a", org="acme"))
    assert mine is not None

    # Directly attempt the bind another organisation would attempt. The pool
    # would not offer this pod; the claim refuses it anyway, which is the layer
    # that has to hold when the pool's own filtering is wrong.
    stolen = await claims.bind(
        api, mine.pod, _spec("inv-b", org="globex"), holder="other", lease_seconds=30
    )
    assert stolen is None

    pod = await api.get_pod(mine.pod)
    assert pod is not None
    labels = pod["metadata"]["labels"]
    assert labels[SANDBOX_ORG_LABEL] == "acme"
    assert labels[SANDBOX_INVESTIGATION_LABEL] == "inv-a"
    assert labels[SANDBOX_STATE_LABEL] == str(SandboxState.CLAIMED)


async def test_an_exhausted_pool_provisions_on_demand_rather_than_refusing() -> None:
    """the warm pool's edge case: a burst is slower, never a failed investigation."""
    api = _api()
    sandbox = KubernetesSandbox(api=api, pool_size=1)
    await sandbox.pool.replenish()

    first = await sandbox.provision(_spec("inv-1"))
    status = await sandbox.pool_status()
    assert status.exhausted

    second = await sandbox.provision(_spec("inv-2"))
    assert second.sandbox_id != first.sandbox_id
    assert second.investigation_id == "inv-2"

    await sandbox.release(first)
    await sandbox.release(second)


async def test_a_lapsed_claim_lets_the_instance_be_taken_back() -> None:
    api = _api()
    sandbox = KubernetesSandbox(api=api, pool_size=1)
    await sandbox.pool.replenish()

    held = await sandbox.pool.claim(_spec("inv-crashed"), lease_seconds=0.0)
    assert held is not None
    assert held.is_expired()

    # The pod now carries another team's labels, so it is not re-offered to a
    # different tenant even once the lease lapses — expiry frees the *claim*,
    # not the tenancy.
    same_team = await claims.bind(api, held.pod, _spec("inv-next"), holder="next", lease_seconds=30)
    assert same_team is not None
    assert same_team.investigation_id == "inv-next"

    other_tenant = await claims.bind(
        api, held.pod, _spec("inv-other", org="globex"), holder="other", lease_seconds=30
    )
    assert other_tenant is None


async def test_releasing_a_claimed_instance_destroys_it_and_replenishes_the_pool() -> None:
    """A claimed instance never returns to the pool; a fresh one takes its place."""
    api = _api()
    sandbox = KubernetesSandbox(api=api, pool_size=1)
    await sandbox.pool.replenish()

    instance = await sandbox.provision(_spec("inv-1"))
    pods_before = {pod["metadata"]["name"] for pod in await api.list_pods()}
    await sandbox.release(instance)
    pods_after = {pod["metadata"]["name"] for pod in await api.list_pods()}

    assert (await sandbox.pool_status()).idle == 1
    assert pods_after != pods_before, "the released pod must not be the pooled one"


async def test_a_pooled_pod_carries_no_tenant_at_all() -> None:
    """The reason there is no reset step to get wrong: there is nothing to reset."""
    api = _api()
    sandbox = KubernetesSandbox(api=api, pool_size=1)
    await sandbox.pool.replenish()

    pod = (await api.list_pods())[0]
    labels = pod["metadata"]["labels"]
    assert labels[SANDBOX_STATE_LABEL] == str(SandboxState.IDLE)
    assert SANDBOX_ORG_LABEL not in labels
    assert SANDBOX_TEAM_LABEL not in labels
    assert SANDBOX_INVESTIGATION_LABEL not in labels


async def test_two_reapers_over_a_cluster_delete_each_pod_once() -> None:
    """The same, against the profile whose instances outlive the process that made them."""
    api = _api()
    sandbox = KubernetesSandbox(api=api, pool_size=0)
    instances = [await sandbox.provision(_spec(f"inv-{n}")) for n in range(4)]
    for instance in instances:
        api.seed_expired(f"ninjasre-sandbox-{instance.sandbox_id}")

    reports = await asyncio.gather(
        Reaper(sandbox, holder="a").sweep(live_runs=set()),
        Reaper(sandbox, holder="b").sweep(live_runs=set()),
    )
    destroyed = [name for report in reports for name in report.destroyed]

    assert sorted(destroyed) == sorted(instance.sandbox_id for instance in instances)
    assert len(destroyed) == len(set(destroyed))
    assert await api.list_pods() == ()
