"""SC-002, SC-003 and SC-006: the claims that are only true at size.

Every other test in this directory would pass against a store that scanned. A
sequential scan over ten episodes is instant, and so is a breadth-first walk of
a twelve-node graph — which is why "top-k returns quickly" and "blast radius is
bounded" have to be checked against a corpus large enough for the wrong
implementation to be slow.

These run only against PostgreSQL, and only when the suite was asked for it. The
fakes search exhaustively on purpose — it makes their answers a stable
specification — so timing them would measure Python rather than the design.

The estate summary is here for a different reason, and it is the one that made it
worth adding. ``tests/benchmarks/test_estate_scale.py`` holds the same budget
over the fakes on every commit, and calls itself a floor rather than a ceiling.
What it cannot see is that ``PostgresEstateRepository.summarise`` selects every
row and hydrates each one into a ``Resource`` in Python — deliberately, so the
freshness overlay is spelled once, in ``Resource.reported_health``, rather than a
second time in SQL. That is work which scales with the estate and does not exist
in a dictionary walk: ten thousand ORM instances and ten thousand JSONB payloads,
over a connection. Whether the budget survives it is a question only the database
answers.

The budgets are the constants, not numbers invented here. If
``VECTOR_SEARCH_LATENCY_BUDGET_MS`` moves, the promise moves with it, and this
is what notices.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import POSTGRES, PRIMARY_ORG
from sqlalchemy import insert, text

from config.constants.estate import (
    ESTATE_SUMMARY_BUDGET_RESOURCES,
    ESTATE_SUMMARY_BUDGET_SECONDS,
)
from config.constants.persistence import (
    DEFAULT_GRAPH_DEPTH,
    EPISODE_VECTOR_NAMESPACE,
    GRAPH_TRAVERSAL_LATENCY_BUDGET_MS,
    MIGRATION_BACKFILL_BATCH_SIZE,
    VECTOR_SEARCH_LATENCY_BUDGET_MS,
)
from platform.estate.kinds import (
    KIND_CONTAINER,
    KIND_DATASTORE,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
)
from platform.persistence.ports import (
    EstateQuery,
    PersistenceGateway,
    ResourceHealth,
    TenantScope,
    TopologyEdge,
    VectorRecord,
)
from platform.persistence.postgres import models
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

#: SC-006's estate.
RESOURCE_COUNT = ESTATE_SUMMARY_BUDGET_RESOURCES

#: Fixed, so a slow run is a regression rather than an unlucky corpus.
ESTATE_EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

#: Recent enough at ``ESTATE_EPOCH`` that the freshness overlay leaves the stored
#: state alone. A corpus reporting ``stale`` throughout would count one branch.
OBSERVED_AT = ESTATE_EPOCH - timedelta(seconds=30)

#: Cycled, so the summary counts something in every bucket rather than walking
#: ten thousand rows down one branch of the precedence rule.
KINDS = (KIND_VIRTUAL_MACHINE, KIND_CONTAINER, KIND_DATASTORE, KIND_NODE)
ESTATE_STATES = (
    ResourceHealth.HEALTHY,
    ResourceHealth.HEALTHY,
    ResourceHealth.DEGRADED,
    ResourceHealth.UNHEALTHY,
    ResourceHealth.UNKNOWN,
)

#: Shaped like a provider's. An empty payload is a JSONB column the hydration
#: never has to parse, which is the cost this test exists to measure.
ESTATE_ATTRIBUTES = {
    "cpu_count": 4,
    "memory_bytes": 8_589_934_592,
    "power_state": "running",
    "node": "pve-01",
}

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


def _estate_row(index: int) -> dict[str, Any]:
    """Return one seeded estate row, in the model's own column names."""
    kind = KINDS[index % len(KINDS)]
    state = ESTATE_STATES[index % len(ESTATE_STATES)]
    return {
        "org_id": PRIMARY_ORG,
        "resource_id": f"res-{index:06d}",
        "kind": kind,
        "source": "proxmox" if index % 2 else "docker",
        "native_id": f"native-{index:06d}",
        "display_name": f"resource {index:06d}",
        "correlation_key": f"corr-{index:06d}",
        "parent_id": None,
        "team_node_id": None,
        "attributes": ESTATE_ATTRIBUTES,
        "labels": ["environment:production", f"kind:{kind}"],
        "sources": [],
        "health": state.value,
        # The shape ``_derivation_to_json`` writes. Present rather than null
        # because a null derivation reports stale, which would measure the one
        # branch that never reaches the stored state.
        "derivation": {
            "state": state.value,
            "rule": "provider_status",
            "derived_at": OBSERVED_AT.isoformat(),
            "signals": [],
            "raw_status": "running",
            "explanation": "",
        },
        "first_seen_at": OBSERVED_AT,
        "last_seen_at": OBSERVED_AT,
        "absent_since": None,
        "maintenance_until": None,
        "maintenance_reason": "",
    }


async def _seed_estate(gateway: PersistenceGateway, scope: TenantScope) -> None:
    """Write ``RESOURCE_COUNT`` resources, in bulk.

    Not through ``upsert``: ten thousand round trips, each of them a read
    followed by a flush, would make this a measurement of insert throughput,
    which ``test_estate_repository.py`` is what covers.
    """
    for first in range(0, RESOURCE_COUNT, MIGRATION_BACKFILL_BATCH_SIZE):
        last = min(first + MIGRATION_BACKFILL_BATCH_SIZE, RESOURCE_COUNT)
        async with gateway.begin(scope) as uow:
            assert isinstance(uow, PostgresUnitOfWork)
            await uow.session.execute(
                insert(models.EstateResource),
                [_estate_row(index) for index in range(first, last)],
            )


@pytest.mark.usefixtures("postgres_only")
async def test_a_ten_thousand_resource_summary_answers_within_budget(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-006, measured where the hydration and the round trip are real."""
    await _seed_estate(gateway, scope)

    async with gateway.begin(scope) as uow:
        started = time.perf_counter()
        summary = await uow.estate.summarise(now=ESTATE_EPOCH)
        spent = time.perf_counter() - started

    # Fast and wrong is not a passing SC-006. An empty estate meets any budget,
    # and so does one whose rows all fell down the absent branch.
    assert summary.total == RESOURCE_COUNT
    assert sum(summary.by_kind.values()) == RESOURCE_COUNT
    assert set(summary.by_kind) == set(KINDS)
    assert summary.absent == 0

    assert spent < ESTATE_SUMMARY_BUDGET_SECONDS, (
        f"summarising {RESOURCE_COUNT} resources took {spent:.3f}s, "
        f"above the {ESTATE_SUMMARY_BUDGET_SECONDS}s budget"
    )


@pytest.mark.usefixtures("postgres_only")
async def test_a_filtered_estate_query_does_not_pay_for_the_whole_estate(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Asking for one kind costs what one kind costs, not what the estate costs."""
    await _seed_estate(gateway, scope)

    async with gateway.begin(scope) as uow:
        started = time.perf_counter()
        found = await uow.estate.query(EstateQuery(kinds=(KIND_DATASTORE,), limit=50))
        spent = time.perf_counter() - started

    assert len(found) == 50
    assert {resource.kind for resource in found} == {KIND_DATASTORE}

    assert spent < ESTATE_SUMMARY_BUDGET_SECONDS, (
        f"a filtered query over {RESOURCE_COUNT} resources took {spent:.3f}s, "
        f"above the {ESTATE_SUMMARY_BUDGET_SECONDS}s budget"
    )


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
