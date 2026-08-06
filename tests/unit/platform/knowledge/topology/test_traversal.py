"""A topology cycle terminates, and a bounded traversal says when it was cut.

``A -> B -> A`` is legal in real systems — two services that call each other, a
cache that is also a dependency of what populates it — and a traversal that
recursed on it would hang an investigation rather than answer it. SC-002 is the
assertion that it does not, and it is written first because the visited set that
makes it true is easy to leave out and impossible to notice without this test.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from config.constants.knowledge import TOPOLOGY_VERIFICATION_STALE_DAYS
from config.constants.persistence import MAX_GRAPH_DEPTH, MAX_GRAPH_RESULTS
from config.prompts.knowledge import TOPOLOGY_DISABLED
from platform.knowledge.policy import KnowledgePolicy
from platform.knowledge.topology.models import DependencyEdge, ServiceNode
from platform.knowledge.topology.queries import TopologyQueries
from platform.knowledge.topology.write import TopologyWriter
from platform.persistence.errors import BoundExceeded
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import NodeKind, PersistenceGateway, TenantScope, TopologyEdge
from tests.unit.platform.knowledge.conftest import Clock

pytestmark = pytest.mark.unit


async def wire(gateway: PersistenceGateway, scope: TenantScope, *pairs: tuple[str, str]) -> None:
    """Store one dependency edge per pair, from the first onto the second."""
    async with gateway.begin(scope) as uow:
        for upstream, downstream in pairs:
            await uow.topology.upsert_edge(
                TopologyEdge(from_node_id=upstream, to_node_id=downstream)
            )


async def test_a_cycle_does_not_cause_infinite_traversal(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """SC-002.

    The origin is excluded from its own dependency set. A cycle would otherwise
    report ``checkout`` as one of ``checkout``'s dependencies, which is true of
    the graph and useless to an operator.
    """
    await wire(gateway, scope, ("checkout", "payments"), ("payments", "checkout"))
    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)

    found = await queries.dependencies("checkout", depth=MAX_GRAPH_DEPTH)

    assert found.names() == ("payments",)
    assert found.truncated is False


async def test_a_longer_cycle_terminates_and_reports_every_member_once(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    await wire(
        gateway,
        scope,
        ("checkout", "payments"),
        ("payments", "ledger"),
        ("ledger", "checkout"),
    )
    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)

    found = await queries.dependencies("checkout", depth=MAX_GRAPH_DEPTH)
    radius = await queries.blast_radius("checkout", depth=MAX_GRAPH_DEPTH)

    assert sorted(found.names()) == ["ledger", "payments"]
    assert sorted(entry.service.node_id for entry in radius.reaches) == ["ledger", "payments"]


async def test_an_unknown_service_returns_an_empty_answer_cleanly(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """Acceptance scenario 2: the investigation continues.

    Empty is a gap in the topology data, not a failure — ``searched`` stays true,
    because the graph was asked and answered.
    """
    await wire(gateway, scope, ("checkout", "payments"))
    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)

    answer = await queries.query("nowhere-in-particular")

    assert answer.empty is True
    assert answer.searched is True
    assert answer.reason == ""


async def test_a_depth_above_the_bound_is_refused_rather_than_clamped(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    # A blast radius silently computed at depth 5 when the caller asked for 40
    # looks complete and is not.
    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)

    with pytest.raises(BoundExceeded) as failure:
        await queries.query("checkout", depth=MAX_GRAPH_DEPTH + 1)

    assert failure.value.constant == "MAX_GRAPH_DEPTH"


async def test_a_hub_service_reports_that_the_answer_was_cut(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """FR-004: the impact statement is a lower bound and says so."""
    async with gateway.begin(scope) as uow:
        for index in range(MAX_GRAPH_RESULTS + 1):
            await uow.topology.upsert_edge(
                TopologyEdge(from_node_id="checkout", to_node_id=f"backend-{index:04d}")
            )
    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)

    answer = await queries.query("checkout", depth=1)

    assert answer.truncated is True
    assert len(answer.dependencies.services) == MAX_GRAPH_RESULTS


async def test_an_unavailable_graph_degrades_and_the_degradation_is_recorded(
    scope: TenantScope, clock: Clock
) -> None:
    """FR-009 and SC-009.

    ``searched=False`` with a reason, not an empty answer. "Nothing depends on
    this service" and "we cannot tell you what depends on this service" lead to
    opposite decisions.
    """
    store = FakePersistence(topology_available=False)
    async with store.begin_system() as system:
        await system.orgs.create_organisation(scope.org_id, "Acme Corp")
    queries = TopologyQueries(gateway=store, scope=scope, clock=clock)

    answer = await queries.query("checkout")

    assert answer.searched is False
    assert answer.reason
    assert answer.empty is True

    available, reason = await queries.available()
    assert available is False
    assert reason

    summary = queries.ledger.trace_summary()
    assert summary["topology_queries"] == 1
    assert summary["topology_degradations"] == 1

    await store.close()


async def test_a_disabled_switch_is_not_an_unavailable_graph(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    await wire(gateway, scope, ("checkout", "payments"))
    queries = TopologyQueries(
        gateway=gateway,
        scope=scope,
        policy=KnowledgePolicy(topology_enabled=False),
        clock=clock,
    )

    answer = await queries.query("checkout")

    assert answer.searched is False
    assert answer.reason == TOPOLOGY_DISABLED


async def test_every_returned_service_carries_when_it_was_last_verified(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """T014: the agent can discount an edge nobody has confirmed recently."""
    writer = TopologyWriter(gateway=gateway, scope=scope, clock=clock)
    await writer.upsert_service(
        ServiceNode(node_id="payments", kind=NodeKind.SERVICE, source="kubernetes")
    )
    await writer.upsert_dependency(
        DependencyEdge(from_node_id="checkout", to_node_id="payments", source="kubernetes")
    )

    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)
    fresh = await queries.query("checkout")
    payments = fresh.dependencies.services[0]

    assert payments.verified_at == clock()
    assert fresh.stale_services(clock()) == ()

    # A fortnight later nobody has re-verified it, and the answer says so.
    later = clock() + timedelta(days=TOPOLOGY_VERIFICATION_STALE_DAYS + 1)
    assert [service.node_id for service in fresh.stale_services(later)] == ["payments"]
