"""Getting the graph ready, and finding out when it cannot be.

Apache AGE needs three things: the extension installed, its library loaded on
the session, and the graph created. They happen at two very different times, and
keeping them apart is the whole point of this module.

**Creating the graph happens once, on its own connection.** It is DDL, and DDL
inside a caller's unit of work is how a unit of work loses its transaction: the
obvious implementation asks AGE to create the graph, catches "already exists",
and rolls back to clear the failed statement — rolling back the caller's writes
along with it. So the check is a lookup in ``ag_graph`` and the create only runs
when the lookup came back empty. No exception, nothing to recover from.

**Loading happens per connection**, because that is the scope AGE's ``LOAD``
has, and pooled connections are reused across units of work.

**Creating the indexes happens here too**, and it is not an optimisation. Apache
AGE builds no index on a label's properties or on an edge's endpoints, so a
deployment that never runs the DDL below pays a sequential scan on every write
and every traversal anchor. Measured on a ten-thousand-service topology, that is
the difference between a graph that loads in a minute and one that takes twenty:
an unindexed edge write costs O(edges), which makes populating the graph cost
O(edges²), and discovery reconciles continuously rather than importing once.

The three are one per access path the catalogue actually uses, and each is the
shape its predicate requires rather than the shape that looks right:

- ``Node.properties`` is GIN, because AGE compiles ``{node_id: $id}`` into a
  containment test over the whole map. A btree over the extracted key matches
  nothing the planner is looking for and is silently never used.
- ``Edge.start_id`` and ``Edge.end_id``, because every hop of a traversal and
  every ``MERGE`` of an edge finds edges by endpoint.

``ensure`` never raises for a missing AGE. It reports, and the topology
repository turns that report into ``TopologyUnavailable`` at the point a caller
asks a question it cannot answer. Everything else in the platform carries on,
which is what FR-002's "degrades rather than crashes" has to mean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from platform.persistence.postgres.graph.queries import EDGE_LABEL, GRAPH, NODE_LABEL

#: Reason reported when the extension is not installed or cannot be loaded.
AGE_UNAVAILABLE = "The Apache AGE extension is not available in this database."

#: The indexes AGE does not build, one per access path the catalogue uses.
#: Names are explicit so ``IF NOT EXISTS`` makes re-running this free.
INDEXES: Final[tuple[tuple[str, str], ...]] = (
    (
        "ninjasre_topology_node_properties",
        f"CREATE INDEX IF NOT EXISTS ninjasre_topology_node_properties "
        f'ON "{GRAPH}"."{NODE_LABEL}" USING gin (properties)',
    ),
    (
        "ninjasre_topology_edge_start",
        f"CREATE INDEX IF NOT EXISTS ninjasre_topology_edge_start "
        f'ON "{GRAPH}"."{EDGE_LABEL}" (start_id)',
    ),
    (
        "ninjasre_topology_edge_end",
        f"CREATE INDEX IF NOT EXISTS ninjasre_topology_edge_end "
        f'ON "{GRAPH}"."{EDGE_LABEL}" (end_id)',
    ),
)


@dataclass(frozen=True, slots=True)
class GraphReadiness:
    """Whether Cypher can run, and why not when it cannot."""

    available: bool
    reason: str | None = None


async def load(conn: AsyncConnection) -> bool:
    """Make AGE usable on this connection, and report whether it is.

    Idempotent and cheap on a connection that already has it, which is what
    makes calling it per unit of work acceptable rather than something to cache
    and get wrong after the pool recycles a connection.

    **A refused ``LOAD`` is not the same fact as AGE being unavailable.**
    ``LOAD`` is superuser-only unless the library sits in ``$libdir/plugins``,
    and a PostgreSQL that carries AGE commonly puts it in
    ``shared_preload_libraries`` instead — precisely so no session has to load
    it and no application needs a superuser to run one. That deployment is the
    good shape, and reading its refusal as "this database has no graph" reports
    it as broken. So a refusal is followed by asking whether AGE answers
    anyway; only a database where it does not answer has none.
    """
    try:
        async with conn.begin_nested():
            await conn.execute(text("LOAD 'age'"))
    except DBAPIError:
        # The refused statement poisons the transaction, and the question after
        # it needs one that can still be asked. A savepoint is the only undo
        # available here: ``ensure`` runs this inside ``engine.begin()``, so the
        # transaction belongs to that block. Rolling it back from in here closes
        # it, and the probe below would then raise ``InvalidRequestError``
        # rather than the database error this catches — killing the deployment
        # on precisely the refusal this function exists to survive.
        return await _answers(conn)
    return True


async def _answers(conn: AsyncConnection) -> bool:
    """Return whether AGE is usable on ``conn`` without having been loaded here.

    Reads the catalogue every Cypher statement goes through. It resolves only
    when the library is in the backend, which is exactly the question a refused
    ``LOAD`` leaves open.
    """
    try:
        async with conn.begin_nested():
            await conn.scalar(text("SELECT count(*) FROM ag_catalog.ag_graph"))
    except DBAPIError:
        return False
    return True


async def ensure(engine: AsyncEngine) -> GraphReadiness:
    """Create the graph if the database lacks it, and report whether Cypher will run.

    Called once, on its own connection, before any unit of work exists.
    """
    try:
        async with engine.begin() as conn:
            if not await load(conn):
                return GraphReadiness(available=False, reason=AGE_UNAVAILABLE)

            existing = await conn.scalar(
                text("SELECT 1 FROM ag_catalog.ag_graph WHERE name = :name"),
                {"name": GRAPH},
            )
            if existing is None:
                await conn.execute(text("SELECT ag_catalog.create_graph(:name)"), {"name": GRAPH})
            await _ensure_labels(conn)
            for _, statement in INDEXES:
                await conn.execute(text(statement))
    except DBAPIError as error:
        return GraphReadiness(available=False, reason=f"{AGE_UNAVAILABLE} ({error.orig})")

    return GraphReadiness(available=True)


async def _ensure_labels(conn: AsyncConnection) -> None:
    """Create the two labels, so there is a table for an index to sit on.

    AGE creates a label's table on first write, which is too late: the index
    has to exist before the writes it is there to serve. Creating them here is
    what turns "index the graph" into something that can happen once at startup
    rather than after the first edge arrives.

    Checked rather than attempted-and-caught, for the reason the module docstring
    gives: a failed statement poisons the surrounding transaction, and this one
    runs on the same connection as the ``create_graph`` above.
    """
    for label, create in (
        (NODE_LABEL, "ag_catalog.create_vlabel"),
        (EDGE_LABEL, "ag_catalog.create_elabel"),
    ):
        found = await conn.scalar(
            text(
                "SELECT 1 FROM ag_catalog.ag_label label "
                "JOIN ag_catalog.ag_graph graph ON label.graph = graph.graphid "
                "WHERE graph.name = :graph AND label.name = :label"
            ),
            {"graph": GRAPH, "label": label},
        )
        if found is None:
            await conn.execute(
                text(f"SELECT {create}(:graph, :label)"), {"graph": GRAPH, "label": label}
            )


async def is_available(conn: AsyncConnection) -> GraphReadiness:
    """Return whether Cypher can run on ``conn``, without creating anything.

    Used by the health check, which should have no side effects on a database it
    is only meant to be reporting about.
    """
    try:
        if not await load(conn):
            return GraphReadiness(available=False, reason=AGE_UNAVAILABLE)
        found = await conn.scalar(
            text("SELECT 1 FROM ag_catalog.ag_graph WHERE name = :name"), {"name": GRAPH}
        )
    except DBAPIError as error:
        return GraphReadiness(available=False, reason=f"{AGE_UNAVAILABLE} ({error.orig})")

    if found is None:
        return GraphReadiness(
            available=False,
            reason=f"The graph {GRAPH!r} has not been created in this database.",
        )
    return GraphReadiness(available=True)


__all__ = ["AGE_UNAVAILABLE", "GraphReadiness", "ensure", "is_available", "load"]
