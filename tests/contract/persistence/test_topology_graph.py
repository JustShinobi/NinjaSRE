"""Contract: the bounded catalogue, and what happens without a graph."""

from __future__ import annotations

import inspect

import pytest
from conftest import POSTGRES
from sqlalchemy import text

from config.constants.persistence import (
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_RESULTS,
    TOPOLOGY_GRAPH_NAME,
)
from platform.persistence.errors import BoundExceeded, TopologyUnavailable
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    EdgeKind,
    NodeKind,
    PersistenceGateway,
    TenantScope,
    TopologyEdge,
    TopologyGraph,
    TopologyNode,
    UnitOfWork,
)
from platform.persistence.postgres.gateway import PostgresPersistence

pytestmark = pytest.mark.contract

#: The catalogue. Adding a shape is a row here, a row in the plan's table, and a
#: review — not something a caller can do by composing.
QUERY_CATALOGUE = frozenset(
    {
        "upsert_node",
        "upsert_edge",
        "delete_edge",
        "edges_from",
        "direct_dependencies",
        "direct_dependents",
        "transitive_dependencies",
        "transitive_dependents",
        "blast_radius",
        "shortest_path",
        "components_for_episode",
        "episodes_for_component",
    }
)


async def chain(uow: UnitOfWork, *node_ids: str) -> None:
    """Wire ``a -> b -> c``: each node depends on the next."""
    for upstream, downstream in zip(node_ids, node_ids[1:], strict=False):
        await uow.topology.upsert_edge(TopologyEdge(from_node_id=upstream, to_node_id=downstream))


def test_the_catalogue_is_closed_and_takes_no_query_string() -> None:
    """FR-016, as a property of the signatures rather than a rule to remember.

    Nothing here accepts a ``query``, ``cypher``, or ``statement`` parameter, so
    there is no way to hand this port a query — and therefore no way for a model
    to generate one that reaches it.
    """
    traversals = {
        name for name in dir(TopologyGraph) if not name.startswith("_") and name != "availability"
    }
    assert traversals == QUERY_CATALOGUE

    forbidden = {"query", "cypher", "statement", "sql"}
    for name in traversals:
        parameters = set(inspect.signature(getattr(TopologyGraph, name)).parameters)
        assert not parameters & forbidden, f"{name} accepts a query string"


async def test_upserting_a_node_merges_rather_than_replaces(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Topology arrives from several discovery sources. A Kubernetes scraper that
    # learns a namespace must not erase the owner a config sync recorded.
    async with gateway.begin(scope) as uow:
        await uow.topology.upsert_node(
            TopologyNode(node_id="checkout", name="checkout", owner_node_id="payments")
        )
        merged = await uow.topology.upsert_node(
            TopologyNode(node_id="checkout", properties={"namespace": "prod"})
        )

    assert merged.owner_node_id == "payments"
    assert merged.name == "checkout"
    assert merged.properties["namespace"] == "prod"


async def test_an_edge_creates_endpoints_it_has_never_seen(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Discovery sees an edge before both ends often enough that failing would
    # mean dropping real topology on ordering alone.
    async with gateway.begin(scope) as uow:
        await uow.topology.upsert_edge(TopologyEdge(from_node_id="checkout", to_node_id="postgres"))
        dependencies = await uow.topology.direct_dependencies("checkout")

    assert [node.node_id for node in dependencies.nodes] == ["postgres"]


async def test_edges_from_carries_the_properties_a_traversal_cannot(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The one shape that returns edges, and why reconciliation needs it.

    Every traversal returns nodes, so a caller reading one cannot tell an
    annotated edge from a bare one. Discovery has to, or it deletes the
    annotation an operator wrote on the dependency it could not observe.
    """
    async with gateway.begin(scope) as uow:
        await uow.topology.upsert_edge(
            TopologyEdge(
                from_node_id="checkout",
                to_node_id="payments",
                kind=EdgeKind.CALLS,
                properties={"note": "only during failover"},
            )
        )
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="checkout", to_node_id="postgres", kind=EdgeKind.READS_FROM)
        )
        edges = await uow.topology.edges_from("checkout")

    assert [(edge.to_node_id, edge.kind) for edge in edges] == [
        ("payments", EdgeKind.CALLS),
        ("postgres", EdgeKind.READS_FROM),
    ]
    assert edges[0].properties["note"] == "only during failover"


async def test_deleting_an_edge_keeps_both_endpoints(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A service whose last dependency was retired is still a service, and
    # deleting the node would take its annotations and its owner with it.
    async with gateway.begin(scope) as uow:
        await uow.topology.upsert_node(TopologyNode(node_id="payments", name="payments"))
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="checkout", to_node_id="payments", kind=EdgeKind.CALLS)
        )

        removed = await uow.topology.delete_edge(
            TopologyEdge(from_node_id="checkout", to_node_id="payments", kind=EdgeKind.CALLS)
        )
        again = await uow.topology.delete_edge(
            TopologyEdge(from_node_id="checkout", to_node_id="payments", kind=EdgeKind.CALLS)
        )

        assert removed is True
        assert again is False
        assert await uow.topology.edges_from("checkout") == ()
        assert (await uow.topology.direct_dependencies("checkout")).nodes == ()
        path = await uow.topology.shortest_path("payments", "payments")

    assert [node.node_id for node in path] == ["payments"]


async def test_deleting_one_kind_leaves_the_other_edge_between_the_same_pair(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Two services can genuinely relate twice — a service that both calls an API
    # and reads its database has two dependencies, and collapsing them would lose
    # one on every reconciliation.
    async with gateway.begin(scope) as uow:
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="checkout", to_node_id="payments", kind=EdgeKind.CALLS)
        )
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="checkout", to_node_id="payments", kind=EdgeKind.READS_FROM)
        )
        await uow.topology.delete_edge(
            TopologyEdge(from_node_id="checkout", to_node_id="payments", kind=EdgeKind.CALLS)
        )
        edges = await uow.topology.edges_from("checkout")

    assert [edge.kind for edge in edges] == [EdgeKind.READS_FROM]


async def test_edges_from_excludes_involvement(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="ep-1", to_node_id="checkout", kind=EdgeKind.INVOLVED)
        )
        assert await uow.topology.edges_from("ep-1") == ()


async def test_dependencies_and_dependents_are_the_same_edge_read_both_ways(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await chain(uow, "web", "checkout", "postgres")

        assert [n.node_id for n in (await uow.topology.direct_dependencies("checkout")).nodes] == [
            "postgres"
        ]
        assert [n.node_id for n in (await uow.topology.direct_dependents("checkout")).nodes] == [
            "web"
        ]


async def test_blast_radius_reports_how_far_away_each_thing_is(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The services one hop out are the ones an operator pages; the ones three
    # hops out are context.
    async with gateway.begin(scope) as uow:
        await chain(uow, "mobile", "web", "checkout", "postgres")
        radius = await uow.topology.blast_radius("postgres", depth=3)

    assert [(entry.node.node_id, entry.depth) for entry in radius.reaches] == [
        ("checkout", 1),
        ("web", 2),
        ("mobile", 3),
    ]
    assert radius.truncated is False


async def test_depth_bounds_the_traversal(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await chain(uow, "mobile", "web", "checkout", "postgres")
        near = await uow.topology.transitive_dependents("postgres", depth=1)

    assert [node.node_id for node in near.nodes] == ["checkout"]


async def test_a_depth_above_the_bound_is_refused_not_clamped(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A blast radius silently computed at depth 5 when the caller asked for 40
    # looks complete and is not.
    async with gateway.begin(scope) as uow:
        with pytest.raises(BoundExceeded) as failure:
            await uow.topology.blast_radius("postgres", depth=MAX_GRAPH_DEPTH + 1)

    assert failure.value.constant == "MAX_GRAPH_DEPTH"


async def test_shortest_path_includes_both_endpoints(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await chain(uow, "web", "checkout", "postgres")
        path = await uow.topology.shortest_path("web", "postgres")

    assert [node.node_id for node in path] == ["web", "checkout", "postgres"]


async def test_no_path_is_an_empty_path(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await chain(uow, "web", "checkout")
        await uow.topology.upsert_node(TopologyNode(node_id="search", name="search"))

        assert await uow.topology.shortest_path("web", "search") == ()


async def test_an_episode_links_to_the_components_it_involved(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.topology.upsert_node(
            TopologyNode(node_id="ep-1", kind=NodeKind.EPISODE, name="Checkout 5xx")
        )
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="ep-1", to_node_id="checkout", kind=EdgeKind.INVOLVED)
        )

        components = await uow.topology.components_for_episode("ep-1")
        episodes = await uow.topology.episodes_for_component("checkout")

    assert [node.node_id for node in components.nodes] == ["checkout"]
    assert [node.node_id for node in episodes.nodes] == ["ep-1"]


async def test_an_involvement_edge_is_not_a_dependency(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Otherwise every service that ever appeared in an incident becomes a
    # dependent of every other one that did.
    async with gateway.begin(scope) as uow:
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="ep-1", to_node_id="checkout", kind=EdgeKind.INVOLVED)
        )
        dependents = await uow.topology.direct_dependents("checkout")

    assert dependents.nodes == ()


async def test_without_a_graph_the_platform_degrades_rather_than_lies(
    scope: TenantScope,
) -> None:
    """FR-002.

    ``availability`` still answers — it is how a caller finds out whether the
    others will. The traversals raise, because an empty blast radius and an
    unknown blast radius lead to opposite decisions.
    """
    store = FakePersistence(topology_available=False)
    async with store.begin_system() as system:
        await system.orgs.create_organisation(scope.org_id, "Acme Corp")

    async with store.begin(scope) as uow:
        status = await uow.topology.availability()
        assert status.available is False
        assert status.reason

        with pytest.raises(TopologyUnavailable):
            await uow.topology.blast_radius("checkout")

        # Everything else still works. That is what "degraded" has to mean.
        assert await uow.episodes.count() == 0

    health = await store.health()
    assert health.is_ready is True
    assert health.state.value == "degraded"


async def test_a_page_cut_short_is_the_same_page_on_every_backend_and_every_run(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Truncation has to be deterministic, or the answer depends on the storage.

    A hub with more dependents than the result bound produces a partial answer.
    Which part is not a detail: an operator comparing two runs, or comparing what
    the console shows against what the agent reasoned over, is entitled to see
    the same services. Ordering by node id and *then* cutting is what makes the
    page a property of the graph rather than of the order rows came back in.

    This runs against both backends, which is the point — it is the assertion
    that they agree, not merely that each is self-consistent.
    """
    async with gateway.begin(scope) as uow:
        # Ids that do not sort in insertion order, so "the lowest 500" and "the
        # first 500 stored" are different sets and the test can tell them apart.
        for index in reversed(range(MAX_GRAPH_RESULTS + 50)):
            await uow.topology.upsert_edge(
                TopologyEdge(from_node_id=f"caller-{index:05d}", to_node_id="shared-postgres")
            )

        first = await uow.topology.direct_dependents("shared-postgres")
        again = await uow.topology.direct_dependents("shared-postgres")

    assert first.truncated is True
    assert [node.node_id for node in first.nodes] == [
        f"caller-{index:05d}" for index in range(MAX_GRAPH_RESULTS)
    ]
    # Same question, same answer — including when the bound cut it.
    assert [node.node_id for node in again.nodes] == [node.node_id for node in first.nodes]


async def test_transitive_dependencies_walks_the_chain_and_stops_at_the_depth_asked_for(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """One traversal answers what a per-node walk used to ask for in many."""
    async with gateway.begin(scope) as uow:
        await chain(uow, "checkout", "payments", "ledger", "postgres")

        two = await uow.topology.transitive_dependencies("checkout", depth=2)
        three = await uow.topology.transitive_dependencies("checkout", depth=3)

    assert [node.node_id for node in two.nodes] == ["ledger", "payments"]
    assert [node.node_id for node in three.nodes] == ["ledger", "payments", "postgres"]
    assert three.truncated is False


async def test_transitive_dependencies_leaves_a_service_out_of_its_own_dependency_set(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A cycle terminates, and the origin is not one of its own dependencies.

    ``checkout -> payments -> checkout`` is legal in a real system. Reporting
    ``checkout`` here would be true of the graph and useless to an operator.
    """
    async with gateway.begin(scope) as uow:
        await chain(uow, "checkout", "payments", "checkout")

        found = await uow.topology.transitive_dependencies("checkout", depth=MAX_GRAPH_DEPTH)

    assert [node.node_id for node in found.nodes] == ["payments"]


async def test_transitive_dependencies_never_crosses_an_involvement_edge(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """An episode an origin touched is not something the origin depends on."""
    async with gateway.begin(scope) as uow:
        await chain(uow, "checkout", "payments")
        await uow.topology.upsert_edge(
            TopologyEdge(from_node_id="checkout", to_node_id="ep-1", kind=EdgeKind.INVOLVED)
        )

        found = await uow.topology.transitive_dependencies("checkout", depth=MAX_GRAPH_DEPTH)

    assert [node.node_id for node in found.nodes] == ["payments"]


async def test_transitive_dependencies_refuses_a_depth_above_the_bound(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Refused rather than clamped, like every other bounded traversal."""
    async with gateway.begin(scope) as uow:
        with pytest.raises(BoundExceeded) as failure:
            await uow.topology.transitive_dependencies("checkout", depth=MAX_GRAPH_DEPTH + 1)

    assert failure.value.constant == "MAX_GRAPH_DEPTH"


async def test_the_graph_is_bootstrapped_with_the_indexes_its_access_paths_need(
    gateway: PersistenceGateway, backend_name: str
) -> None:
    """Apache AGE creates no index of its own, and every write pays for it.

    Three access paths carry the whole catalogue, and none of them is served by
    anything AGE builds:

    - a traversal and an upsert both anchor on ``{node_id: ...}``, which AGE
      rewrites into a containment test over the whole property map — so the
      index has to be GIN on ``properties``. A btree over the extracted key
      looks right and is never used, because it does not match the predicate.
    - ``MERGE (a)-[e:Edge]->(b)`` and every hop of a traversal hunt an edge by
      its endpoints, and without an index that is a sequential scan of every
      edge in the graph, on every single write.

    Measured, the last one is the expensive one: it makes an edge write cost
    O(edges), so populating the graph costs O(edges²). Discovery reconciles
    continuously rather than loading once, so this is the steady state and not a
    one-off import.
    """
    if backend_name != POSTGRES:
        pytest.skip("index creation is a property of the PostgreSQL backend")

    assert isinstance(gateway, PostgresPersistence)
    async with gateway.engine.begin() as conn:
        rows = await conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE schemaname = :graph"),
            {"graph": TOPOLOGY_GRAPH_NAME},
        )
    definitions = [str(row[0]) for row in rows]

    assert any("USING gin" in d and "properties" in d and '"Node"' in d for d in definitions), (
        f"no GIN index on Node.properties; the anchor lookup scans every node. Found: {definitions}"
    )
    assert any("start_id" in d and '"Edge"' in d for d in definitions), (
        f"no index on Edge.start_id; every edge write scans every edge. Found: {definitions}"
    )
    assert any("end_id" in d and '"Edge"' in d for d in definitions), (
        f"no index on Edge.end_id; a dependents traversal scans every edge. Found: {definitions}"
    )
