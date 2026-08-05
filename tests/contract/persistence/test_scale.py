"""SC-002 and SC-003: the two claims that are only true at size.

Every other test in this directory would pass against a store that scanned. A
sequential scan over ten episodes is instant, and so is a breadth-first walk of
a twelve-node graph — which is why "top-k returns quickly" and "blast radius is
bounded" have to be checked against a corpus large enough for the wrong
implementation to be slow.

These run only against PostgreSQL, and only when the suite was asked for it. The
fakes search exhaustively on purpose — it makes their answers a stable
specification — so timing them would measure Python rather than the design.

The budgets are the constants, not numbers invented here. If
``VECTOR_SEARCH_LATENCY_BUDGET_MS`` moves, the promise moves with it, and this
is what notices.
"""

from __future__ import annotations

import time

import pytest
from conftest import POSTGRES, PRIMARY_ORG
from sqlalchemy import text

from config.constants.persistence import (
    DEFAULT_GRAPH_DEPTH,
    EPISODE_VECTOR_NAMESPACE,
    GRAPH_TRAVERSAL_LATENCY_BUDGET_MS,
    MIGRATION_BACKFILL_BATCH_SIZE,
    VECTOR_SEARCH_LATENCY_BUDGET_MS,
)
from platform.persistence.ports import (
    PersistenceGateway,
    TenantScope,
    TopologyEdge,
    VectorRecord,
)
from platform.persistence.postgres.gateway import PostgresUnitOfWork

pytestmark = pytest.mark.contract

#: SC-002's corpus.
EPISODE_COUNT = 100_000

#: SC-003's topology.
SERVICE_COUNT = 10_000

#: Narrow enough to build a hundred thousand quickly, wide enough that HNSW is
#: doing real work rather than degenerating into a scan.
DIMENSION = 64

#: Enough samples that one unlucky moment does not decide the verdict. The
#: median is what gets asserted, rather than a single reading.
SEARCH_SAMPLES = 20

#: Every seeded episode carries this, so a filtered search has something to
#: match and the metadata path is measured rather than skipped.
SEEDED_METADATA = '{"environment": "production"}'

#: The episode whose vector becomes the query. Searching near a point that is
#: actually in the corpus is what an operator's query looks like; a random point
#: in 64 dimensions is nearly equidistant from everything, which would make the
#: timing say nothing.
NEEDLE_SOURCE = "ep-7"


@pytest.fixture
def postgres_only(backend_name: str) -> None:
    """Skip a test that only means something against the real store."""
    if backend_name != POSTGRES:
        pytest.skip("SC-002 and SC-003 measure PostgreSQL; the fakes search exhaustively.")


async def _seed_episodes(gateway: PersistenceGateway, scope: TenantScope) -> tuple[float, ...]:
    """Write ``EPISODE_COUNT`` vectors and return one to search near.

    Generated in the server rather than in Python. Two reasons, and the second
    is the one that decided it.

    A hundred thousand round trips through the port's ``upsert`` would make this
    a test of insert throughput, which is not what SC-002 claims — the rest of
    the suite is what exercises ``upsert``.

    And asyncpg's ``COPY`` is binary-framed, with no encoder for pgvector's
    ``vector``. Registering one is possible and is a codec that would then have
    to be registered on every pooled connection, in production, to serve a test.
    ``generate_series`` and a volatile ``random()`` produce the same corpus with
    nothing to maintain.
    """
    async with gateway.begin(scope) as uow:
        await uow.vectors.ensure(EPISODE_VECTOR_NAMESPACE, model="bench", dimension=DIMENSION)
        descriptor = await uow.vectors.describe(EPISODE_VECTOR_NAMESPACE)

    assert descriptor is not None
    table = f"ninjasre_vec_{EPISODE_VECTOR_NAMESPACE}_g{descriptor.generation}"

    # Batched, at the size a migration's backfill uses. One statement for a
    # hundred thousand rows exceeds DATABASE_STATEMENT_TIMEOUT_MS — which is
    # the timeout doing its job, and the reason FR-008 says a bulk write is
    # batched rather than attempted whole.
    for first in range(0, EPISODE_COUNT, MIGRATION_BACKFILL_BATCH_SIZE):
        last = min(first + MIGRATION_BACKFILL_BATCH_SIZE, EPISODE_COUNT) - 1
        async with gateway.begin(scope) as uow:
            assert isinstance(uow, PostgresUnitOfWork)
            await uow.session.execute(
                text(
                    f"INSERT INTO {table} (org_id, vector_id, embedding, metadata) "  # noqa: S608
                    f"SELECT :org_id, 'ep-' || n, "
                    # Correlated with n on purpose. The obvious
                    # ``ARRAY(SELECT random() ...)`` does not mention the outer
                    # row, so PostgreSQL evaluates it once and every episode
                    # gets the *same* vector — a corpus of a hundred thousand
                    # identical points, which any index answers instantly and
                    # which would have made this benchmark meaningless.
                    # Deterministic too, so a slow run is a real regression
                    # rather than an unlucky corpus.
                    f"  ARRAY(SELECT sin(n * 0.37 + d * 1.13) * cos(n * 0.11 - d * 0.29) "
                    f"        FROM generate_series(1, CAST(:dimension AS integer)) AS d"
                    f"       )::vector, "
                    f"  CAST(:metadata AS jsonb) "
                    f"FROM generate_series(CAST(:first AS bigint), CAST(:last AS bigint)) AS n"
                ),
                {
                    "org_id": PRIMARY_ORG,
                    "dimension": DIMENSION,
                    "metadata": SEEDED_METADATA,
                    "first": first,
                    "last": last,
                },
            )

    # The needle is one of the stored vectors, read back.
    async with gateway.begin(scope) as uow:
        assert isinstance(uow, PostgresUnitOfWork)
        stored = await uow.session.scalar(
            text(f"SELECT embedding::text FROM {table} WHERE vector_id = :id"),  # noqa: S608
            {"id": NEEDLE_SOURCE},
        )

    assert isinstance(stored, str)
    return tuple(float(value) for value in stored.strip("[]").split(","))


@pytest.mark.usefixtures("postgres_only")
async def test_top_k_over_a_hundred_thousand_episodes_stays_within_budget(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-002."""
    needle = await _seed_episodes(gateway, scope)

    async with gateway.begin(scope) as uow:
        assert await uow.vectors.count(EPISODE_VECTOR_NAMESPACE) == EPISODE_COUNT

        # One warm search first. The first query after a bulk load pays for
        # planning and for pulling the index into shared buffers, and neither is
        # what an operator experiences during an incident.
        await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, needle)

        timings: list[float] = []
        for _ in range(SEARCH_SAMPLES):
            started = time.perf_counter()
            matches = await uow.vectors.search(EPISODE_VECTOR_NAMESPACE, needle, k=10)
            timings.append((time.perf_counter() - started) * 1000.0)
            assert len(matches) == 10

    timings.sort()
    median = timings[len(timings) // 2]
    assert median <= VECTOR_SEARCH_LATENCY_BUDGET_MS, (
        f"top-k over {EPISODE_COUNT} episodes took a median {median:.1f}ms, "
        f"above the {VECTOR_SEARCH_LATENCY_BUDGET_MS}ms budget"
    )

    # Fast and wrong is not a passing SC-002. HNSW is approximate, so this asks
    # for the one thing the approximation must not lose: a vector that is
    # *exactly* the query comes back first, and the results are ordered by
    # similarity rather than merely returned.
    async with gateway.begin(scope) as uow:
        await uow.vectors.upsert(
            EPISODE_VECTOR_NAMESPACE,
            [
                VectorRecord(
                    vector_id="ep-exact",
                    embedding=needle,
                    metadata={"environment": "production"},
                )
            ],
        )
        matches = await uow.vectors.search(
            EPISODE_VECTOR_NAMESPACE, needle, k=5, filters={"environment": "production"}
        )

    # ``ep-exact`` and the episode the needle was read from hold the same
    # vector, so they tie at a similarity of 1.0 and the id breaks it. Asserting
    # which of the two comes first would be testing the tie-break; what SC-002
    # needs is that an exact match is at the top at all, and that the ordering
    # below it is by similarity.
    assert {match.vector_id for match in matches[:2]} == {NEEDLE_SOURCE, "ep-exact"}
    assert matches[0].score == pytest.approx(1.0, abs=1e-6)
    assert matches[1].score == pytest.approx(1.0, abs=1e-6)
    assert [match.score for match in matches] == sorted(
        (match.score for match in matches), reverse=True
    )


@pytest.mark.usefixtures("postgres_only")
async def test_depth_three_blast_radius_over_ten_thousand_services_stays_bounded(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-003."""
    async with gateway.begin(scope) as uow:
        # A three-way branching tree: every service depends on its parent, so
        # ``svc-0`` is what everything transitively rests on.
        for index in range(1, SERVICE_COUNT):
            await uow.topology.upsert_edge(
                TopologyEdge(from_node_id=f"svc-{index}", to_node_id=f"svc-{index // 3}")
            )

    async with gateway.begin(scope) as uow:
        await uow.topology.blast_radius("svc-0", depth=1)

        started = time.perf_counter()
        radius = await uow.topology.blast_radius("svc-0", depth=DEFAULT_GRAPH_DEPTH)
        elapsed = (time.perf_counter() - started) * 1000.0

    assert elapsed <= GRAPH_TRAVERSAL_LATENCY_BUDGET_MS, (
        f"depth-{DEFAULT_GRAPH_DEPTH} blast radius over {SERVICE_COUNT} services took "
        f"{elapsed:.1f}ms, above the {GRAPH_TRAVERSAL_LATENCY_BUDGET_MS}ms budget"
    )
    # Three hops of three-way branching reach 3 + 9 + 27 nodes. The exact count
    # matters less than that it is bounded *and* non-trivial: a traversal that
    # returned nothing would also have been fast.
    assert 10 <= len(radius.reaches) <= 60
    assert max(entry.depth for entry in radius.reaches) == DEFAULT_GRAPH_DEPTH
    assert radius.truncated is False
