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

``ensure`` never raises for a missing AGE. It reports, and the topology
repository turns that report into ``TopologyUnavailable`` at the point a caller
asks a question it cannot answer. Everything else in the platform carries on,
which is what FR-002's "degrades rather than crashes" has to mean.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from platform.persistence.postgres.graph.queries import GRAPH

#: Reason reported when the extension is not installed or cannot be loaded.
AGE_UNAVAILABLE = "The Apache AGE extension is not available in this database."


@dataclass(frozen=True, slots=True)
class GraphReadiness:
    """Whether Cypher can run, and why not when it cannot."""

    available: bool
    reason: str | None = None


async def load(conn: AsyncConnection) -> bool:
    """Load AGE onto this connection, and report whether it took.

    Idempotent and cheap on a connection that already has it, which is what
    makes calling it per unit of work acceptable rather than something to cache
    and get wrong after the pool recycles a connection.
    """
    try:
        await conn.execute(text("LOAD 'age'"))
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
    except DBAPIError as error:
        return GraphReadiness(available=False, reason=f"{AGE_UNAVAILABLE} ({error.orig})")

    return GraphReadiness(available=True)


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
