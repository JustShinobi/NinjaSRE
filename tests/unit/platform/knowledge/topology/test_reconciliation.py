"""Re-discovery reconciles: what it removes, what it keeps, and what it must never touch.

Two assertions here decide whether topology discovery is safe to run on a
schedule, and they pull in opposite directions.

SC-003 says a healthy run removes what is genuinely gone — otherwise the graph
accumulates dependencies that were retired two quarters ago and the agent
reasons about them.

SC-004 says a *degraded* run removes nothing. A Kubernetes API having a bad
minute reports a partial estate, and the difference between "this dependency no
longer exists" and "I could not see it just now" is a team's topology.

Between them sits the operator's own writing: annotations, and edges a human drew
that no scraper can observe. Neither is discovery's to remove, under any health.
"""

from __future__ import annotations

import pytest

from platform.knowledge.topology.discovery.port import DiscoveredTopology, DiscoveryHealth
from platform.knowledge.topology.models import DependencyEdge, DependencyKind
from platform.knowledge.topology.queries import TopologyQueries
from platform.knowledge.topology.reconciliation import TopologyReconciler
from platform.knowledge.topology.write import TopologyWriter
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import Clock

pytestmark = pytest.mark.unit

SOURCE = "kubernetes"

PAYMENTS = DependencyEdge(from_node_id="checkout", to_node_id="payments", kind=DependencyKind.CALLS)
LEGACY = DependencyEdge(from_node_id="checkout", to_node_id="legacy", kind=DependencyKind.CALLS)


def discovered(
    *edges: DependencyEdge, health: DiscoveryHealth = DiscoveryHealth.HEALTHY
) -> DiscoveredTopology:
    """Return one discovery run's output over ``checkout``."""
    return DiscoveredTopology(source=SOURCE, edges=edges, health=health, covered=("checkout",))


async def seed(gateway: PersistenceGateway, scope: TenantScope, clock: Clock) -> TopologyReconciler:
    """Run a first healthy discovery and return the reconciler that did it."""
    reconciler = TopologyReconciler(gateway=gateway, scope=scope, clock=clock)
    await reconciler.apply(discovered(PAYMENTS, LEGACY))
    return reconciler


async def test_a_healthy_rediscovery_removes_what_is_gone_and_keeps_annotations(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """SC-003, with both halves in one fixture because they interact.

    The annotation is on the edge that survives, and the operator-authored edge
    is one discovery has never reported. A reconciliation that removed either
    would pass a test that only checked the stale edge was gone.
    """
    reconciler = await seed(gateway, scope, clock)
    writer = TopologyWriter(gateway=gateway, scope=scope, clock=clock)
    await writer.annotate_dependency(
        "checkout", "payments", DependencyKind.CALLS, {"note": "only during failover"}
    )
    await writer.upsert_dependency(
        DependencyEdge(
            from_node_id="checkout",
            to_node_id="failover-dc",
            kind=DependencyKind.DEPENDS_ON,
            operator_authored=True,
        )
    )

    clock.advance(1)
    report = await reconciler.apply(discovered(PAYMENTS))

    assert LEGACY.key in report.removed
    assert PAYMENTS.key in report.refreshed
    assert ("checkout", "failover-dc", "depends_on") not in report.removed

    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)
    edges = {edge.key: edge for edge in await queries.dependency_edges("checkout")}

    assert LEGACY.key not in edges
    assert edges[PAYMENTS.key].annotations["note"] == "only during failover"
    assert edges[PAYMENTS.key].verified_at == clock()
    assert ("checkout", "failover-dc", "depends_on") in edges


async def test_a_degraded_discovery_marks_unverified_rather_than_deleting(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """SC-004.

    The edge stays, keeps the timestamp of the last run that *did* see it, and is
    reported as unverified — so an agent reading it can discount it rather than
    never seeing it at all.
    """
    reconciler = await seed(gateway, scope, clock)
    first_seen = clock()

    clock.advance(1)
    report = await reconciler.apply(discovered(PAYMENTS, health=DiscoveryHealth.DEGRADED))

    assert report.removed == ()
    assert LEGACY.key in report.unverified

    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)
    edges = {edge.key: edge for edge in await queries.dependency_edges("checkout")}

    assert edges[LEGACY.key].unverified is True
    assert edges[LEGACY.key].verified_at == first_seen
    assert edges[PAYMENTS.key].unverified is False


async def test_a_failed_discovery_changes_nothing_at_all(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    # A source that returned nothing because it could not run has observed
    # nothing, and marking the whole estate unverified on the strength of it
    # would make the label meaningless within a week of one flaky adapter.
    reconciler = await seed(gateway, scope, clock)

    clock.advance(1)
    report = await reconciler.apply(
        DiscoveredTopology(
            source=SOURCE, health=DiscoveryHealth.FAILED, reason="connection refused"
        )
    )

    assert report.removed == ()
    assert report.unverified == ()
    assert report.applied is False

    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)
    edges = {edge.key: edge for edge in await queries.dependency_edges("checkout")}
    assert set(edges) == {PAYMENTS.key, LEGACY.key}


async def test_the_reconciliation_diff_is_recordable_for_audit(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    reconciler = await seed(gateway, scope, clock)

    clock.advance(1)
    record = (await reconciler.apply(discovered(PAYMENTS))).to_record()

    assert record["source"] == SOURCE
    assert record["health"] == DiscoveryHealth.HEALTHY.value
    assert record["removed"] == ["checkout->legacy (calls)"]
    assert record["at"] == clock().isoformat()
