"""SC-001: a depth-3 blast radius on a ten-thousand-service graph, and what it reports.

Two properties, and the second is the one that matters during an incident.

**It stays inside the budget.** A blast radius is asked for while somebody is
writing an incident update, and a traversal that takes four seconds is one the
agent will have moved past.

**It says when it is partial.** A hub service with more dependents than the
result bound produces an answer that is a *lower* bound on the impact, and an
operator who publishes "four services affected" when the answer is "at least
four" has published something wrong. The flag travels on the answer and the
capability renders it as a sentence.

This runs against the in-memory backend, which enforces the same bounds and is
what makes the assertion cheap enough to run on every commit. The same
traversal over PostgreSQL and Apache AGE is measured by
``tests/contract/persistence/test_scale.py``, which needs a database and runs as
its own CI job — one of these two proves the layer bounds its own walk, and the
other proves the backend does.
"""

from __future__ import annotations

import time

import pytest

from config.constants.persistence import (
    DEFAULT_GRAPH_DEPTH,
    GRAPH_TRAVERSAL_LATENCY_BUDGET_MS,
    MAX_GRAPH_RESULTS,
)
from platform.knowledge.topology.queries import TopologyQueries
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope, TopologyEdge

pytestmark = pytest.mark.benchmark

#: SC-001's topology.
SERVICE_COUNT = 10_000

ORG = "acme"
TEAM = "team-payments"


@pytest.fixture
async def graph() -> PersistenceGateway:
    """Yield a gateway holding a ten-thousand-service dependency tree.

    Three-way branching: every service depends on its parent, so ``svc-0`` is
    what everything transitively rests on and its blast radius is the whole
    estate — bounded, which is the point.
    """
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme Corp")
    async with store.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
        for index in range(1, SERVICE_COUNT):
            await uow.topology.upsert_edge(
                TopologyEdge(from_node_id=f"svc-{index}", to_node_id=f"svc-{index // 3}")
            )
    return store


async def test_a_depth_three_blast_radius_over_ten_thousand_services_stays_bounded(
    graph: PersistenceGateway,
) -> None:
    """SC-001, the latency half."""
    queries = TopologyQueries(gateway=graph, scope=TenantScope(org_id=ORG, team_node_id=TEAM))

    # One warm pass, so the measurement is of the traversal rather than of
    # whatever the first call happens to construct.
    await queries.blast_radius("svc-0", depth=1)

    started = time.perf_counter()
    radius = await queries.blast_radius("svc-0", depth=DEFAULT_GRAPH_DEPTH)
    elapsed = (time.perf_counter() - started) * 1000.0

    assert elapsed <= GRAPH_TRAVERSAL_LATENCY_BUDGET_MS, (
        f"depth-{DEFAULT_GRAPH_DEPTH} blast radius over {SERVICE_COUNT} services took "
        f"{elapsed:.1f}ms, above the {GRAPH_TRAVERSAL_LATENCY_BUDGET_MS}ms budget"
    )
    # Three hops of three-way branching reach 3 + 9 + 27. The exact count matters
    # less than that it is bounded *and* non-trivial: a traversal that returned
    # nothing would also have been fast.
    assert 10 <= len(radius.reaches) <= 60
    assert max(entry.depth for entry in radius.reaches) == DEFAULT_GRAPH_DEPTH


async def test_a_hub_service_reports_that_its_blast_radius_is_a_lower_bound() -> None:
    """SC-001, the truncation half."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme Corp")

    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    async with store.begin(scope) as uow:
        for index in range(MAX_GRAPH_RESULTS + 50):
            await uow.topology.upsert_edge(
                TopologyEdge(from_node_id=f"caller-{index:05d}", to_node_id="shared-postgres")
            )

    answer = await TopologyQueries(gateway=store, scope=scope).query("shared-postgres", depth=1)

    assert answer.truncated is True
    assert len(answer.blast_radius.reaches) == MAX_GRAPH_RESULTS
    await store.close()
