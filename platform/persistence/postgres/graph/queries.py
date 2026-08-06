"""The catalogue, as openCypher that no caller ever contributes text to.

FR-016 says LLM-generated Cypher must not be executed, and the port makes that
true of its signatures: nothing there takes a query. This module is where the
claim has to survive contact with Apache AGE, which constrains it in one
awkward way.

**AGE will not parameterise a variable-length bound.** ``[:DEPENDS_ON*1..$depth]``
is rejected — the bound has to be a literal in the query text. That is the one
place where a value reaches the query as syntax rather than as a parameter.

The answer is not to format the depth in at call time. It is to render every
legal depth *once, here, at import*: ``MAX_GRAPH_DEPTH`` is 5, so there are five
possible traversals per shape, and a caller's depth selects one from a frozen
tuple after being validated as an integer in range. A depth that is not an
integer in ``1..MAX_GRAPH_DEPTH`` never reaches a string at all, and there is no
code path from caller text to query text.

Everything else — node ids, properties, labels — is a genuine parameter, passed
as agtype in ``cypher()``'s third argument.

Two more AGE limitations shape what is below, and both are worked around here
rather than by weakening the port:

- ``shortestPath()`` does not exist in AGE 1.6. A bounded shortest path is
  instead the shortest of the paths a bounded variable-length match returns,
  ordered by length and limited to one — which is the same answer, computed the
  same way, and bounded by construction.
- ``SET n += $map`` is refused ("SET clause expects a map"). Arbitrary node
  properties are therefore stored as one JSON-encoded string property, and the
  merge that FR's "merge rather than replace" asks for happens in the
  repository, where the fake does it too.
"""

from __future__ import annotations

from typing import Final

from config.constants.persistence import (
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_RESULTS,
    TOPOLOGY_GRAPH_NAME,
)
from platform.persistence.errors import BoundExceeded
from platform.persistence.postgres.identifiers import safe_identifier

#: The graph name, validated once at import. It comes from a constant, and
#: validating it anyway is what makes ``cypher()``'s literal-name requirement
#: safe to rely on rather than merely true today.
GRAPH: Final = safe_identifier(TOPOLOGY_GRAPH_NAME)

#: Node label. One label for every node kind, with the kind as a property:
#: AGE creates a table per label, and a label per kind would turn "everything
#: that depends on this" into a union over as many tables as there are kinds.
NODE_LABEL: Final = "Node"

#: Edge label, likewise singular. The relationship's kind is a property, so a
#: traversal that must exclude ``involved`` edges filters rather than unions.
EDGE_LABEL: Final = "Edge"

#: The property recording what an edge means. Traversals that walk dependencies
#: exclude ``involved``, because an episode touching two services does not make
#: either depend on the other.
INVOLVED_KIND: Final = "involved"


def statement(cypher: str, columns: str, *, parameterised: bool = True) -> str:
    """Return the SQL that runs one Cypher body and names its result columns.

    AGE returns ``agtype`` and requires the caller to declare the shape it
    expects, which is why every query here carries its column list.
    """
    params = ", $1" if parameterised else ""
    return f"SELECT * FROM ag_catalog.cypher('{GRAPH}', $${cypher}$${params}) AS ({columns})"


def check_depth(depth: int) -> int:
    """Return ``depth``, or raise if it is outside the traversal bound (FR-017)."""
    if depth > MAX_GRAPH_DEPTH:
        raise BoundExceeded(
            parameter="depth",
            requested=depth,
            limit=MAX_GRAPH_DEPTH,
            constant="MAX_GRAPH_DEPTH",
        )
    if depth < 1:
        raise ValueError(f"A traversal must cross at least one hop, got {depth}.")
    return depth


# --- Writes -------------------------------------------------------------------

UPSERT_NODE = statement(
    f"""
    MERGE (n:{NODE_LABEL} {{node_id: $node_id}})
    SET n.kind = $kind, n.name = $name,
        n.owner_node_id = $owner_node_id, n.properties = $properties
    RETURN n.node_id
    """,
    "node_id ag_catalog.agtype",
)

READ_NODE = statement(
    f"MATCH (n:{NODE_LABEL} {{node_id: $node_id}}) RETURN properties(n)",
    "node ag_catalog.agtype",
)

UPSERT_EDGE = statement(
    f"""
    MERGE (a:{NODE_LABEL} {{node_id: $from_node_id}})
    MERGE (b:{NODE_LABEL} {{node_id: $to_node_id}})
    MERGE (a)-[e:{EDGE_LABEL} {{kind: $kind}}]->(b)
    SET e.properties = $properties
    RETURN e.kind
    """,
    "kind ag_catalog.agtype",
)

READ_EDGE = statement(
    f"""
    MATCH (a:{NODE_LABEL} {{node_id: $from_node_id}})
          -[e:{EDGE_LABEL} {{kind: $kind}}]->
          (b:{NODE_LABEL} {{node_id: $to_node_id}})
    RETURN e.properties
    """,
    "properties ag_catalog.agtype",
)

DELETE_EDGE = statement(
    f"""
    MATCH (a:{NODE_LABEL} {{node_id: $from_node_id}})
          -[e:{EDGE_LABEL} {{kind: $kind}}]->
          (b:{NODE_LABEL} {{node_id: $to_node_id}})
    DELETE e
    RETURN $kind
    """,
    "kind ag_catalog.agtype",
)

#: The one shape that returns edges rather than nodes. Reconciliation needs the
#: properties on an edge — the operator's annotation, and whether a human drew it
#: — and no traversal above can carry them, because they all return nodes.
EDGES_FROM = statement(
    f"""
    MATCH (a:{NODE_LABEL} {{node_id: $node_id}})-[e:{EDGE_LABEL}]->(b:{NODE_LABEL})
    WHERE e.kind <> '{INVOLVED_KIND}'
    RETURN b.node_id, e.kind, e.properties
    ORDER BY b.node_id, e.kind
    LIMIT {MAX_GRAPH_RESULTS}
    """,
    "to_node_id ag_catalog.agtype, kind ag_catalog.agtype, properties ag_catalog.agtype",
)


# --- One-hop reads --------------------------------------------------------------

DIRECT_DEPENDENCIES = statement(
    f"""
    MATCH (a:{NODE_LABEL} {{node_id: $node_id}})-[e:{EDGE_LABEL}]->(d:{NODE_LABEL})
    WHERE e.kind <> '{INVOLVED_KIND}'
    RETURN DISTINCT properties(d)
    LIMIT {MAX_GRAPH_RESULTS + 1}
    """,
    "node ag_catalog.agtype",
)

DIRECT_DEPENDENTS = statement(
    f"""
    MATCH (a:{NODE_LABEL} {{node_id: $node_id}})<-[e:{EDGE_LABEL}]-(d:{NODE_LABEL})
    WHERE e.kind <> '{INVOLVED_KIND}'
    RETURN DISTINCT properties(d)
    LIMIT {MAX_GRAPH_RESULTS + 1}
    """,
    "node ag_catalog.agtype",
)

COMPONENTS_FOR_EPISODE = statement(
    f"""
    MATCH (a:{NODE_LABEL} {{node_id: $node_id}})
          -[e:{EDGE_LABEL} {{kind: '{INVOLVED_KIND}'}}]->
          (d:{NODE_LABEL})
    RETURN DISTINCT properties(d)
    LIMIT {MAX_GRAPH_RESULTS + 1}
    """,
    "node ag_catalog.agtype",
)

EPISODES_FOR_COMPONENT = statement(
    f"""
    MATCH (a:{NODE_LABEL} {{node_id: $node_id}})
          <-[e:{EDGE_LABEL} {{kind: '{INVOLVED_KIND}'}}]-
          (d:{NODE_LABEL})
    RETURN DISTINCT properties(d)
    LIMIT {MAX_GRAPH_RESULTS + 1}
    """,
    "node ag_catalog.agtype",
)


# --- Bounded traversals ---------------------------------------------------------


def _blast_radius_at(depth: int) -> str:
    """Return the blast-radius traversal for one literal depth.

    ``length(p)`` gives the hop distance, which is what turns "which services"
    into "which services, and how close" — the question an operator under
    pressure is actually asking.
    """
    return statement(
        f"""
        MATCH p = (a:{NODE_LABEL} {{node_id: $node_id}})
                  <-[:{EDGE_LABEL}*1..{depth}]-
                  (d:{NODE_LABEL})
        RETURN properties(d), length(p)
        LIMIT {MAX_GRAPH_RESULTS * (depth + 1)}
        """,
        "node ag_catalog.agtype, hops ag_catalog.agtype",
    )


def _shortest_path_at(depth: int) -> str:
    """Return the bounded shortest-path traversal for one literal depth.

    AGE has no ``shortestPath()``. Ordering the bounded matches by length and
    taking one is the same answer — and it is bounded by construction, which
    ``shortestPath()`` over a strongly-connected topology would not be.
    """
    return statement(
        f"""
        MATCH p = (a:{NODE_LABEL} {{node_id: $from_node_id}})
                  -[:{EDGE_LABEL}*1..{depth}]->
                  (b:{NODE_LABEL} {{node_id: $to_node_id}})
        RETURN nodes(p), length(p)
        ORDER BY length(p) ASC
        LIMIT 1
        """,
        "path ag_catalog.agtype, hops ag_catalog.agtype",
    )


#: One rendered statement per legal depth, indexed from 1. Built at import, so a
#: caller's depth chooses a statement rather than building one.
BLAST_RADIUS_BY_DEPTH: Final[tuple[str, ...]] = ("",) + tuple(
    _blast_radius_at(depth) for depth in range(1, MAX_GRAPH_DEPTH + 1)
)

SHORTEST_PATH_BY_DEPTH: Final[tuple[str, ...]] = ("",) + tuple(
    _shortest_path_at(depth) for depth in range(1, MAX_GRAPH_DEPTH + 1)
)


def blast_radius(depth: int) -> str:
    """Return the pre-rendered blast-radius traversal for a validated depth."""
    return BLAST_RADIUS_BY_DEPTH[check_depth(depth)]


def shortest_path(depth: int = MAX_GRAPH_DEPTH) -> str:
    """Return the pre-rendered shortest-path traversal for a validated depth."""
    return SHORTEST_PATH_BY_DEPTH[check_depth(depth)]


#: Everything this module will ever run. ``tests/contract/persistence`` asserts
#: that the set matches the port's catalogue, so a tenth query shape cannot
#: arrive without the test that reviews it.
STATEMENTS: Final[frozenset[str]] = frozenset(
    {
        UPSERT_NODE,
        READ_NODE,
        UPSERT_EDGE,
        READ_EDGE,
        DELETE_EDGE,
        EDGES_FROM,
        DIRECT_DEPENDENCIES,
        DIRECT_DEPENDENTS,
        COMPONENTS_FOR_EPISODE,
        EPISODES_FOR_COMPONENT,
        *BLAST_RADIUS_BY_DEPTH[1:],
        *SHORTEST_PATH_BY_DEPTH[1:],
    }
)


__all__ = [
    "BLAST_RADIUS_BY_DEPTH",
    "COMPONENTS_FOR_EPISODE",
    "DELETE_EDGE",
    "DIRECT_DEPENDENCIES",
    "DIRECT_DEPENDENTS",
    "EDGES_FROM",
    "EDGE_LABEL",
    "EPISODES_FOR_COMPONENT",
    "GRAPH",
    "INVOLVED_KIND",
    "NODE_LABEL",
    "READ_EDGE",
    "READ_NODE",
    "SHORTEST_PATH_BY_DEPTH",
    "STATEMENTS",
    "UPSERT_EDGE",
    "UPSERT_NODE",
    "blast_radius",
    "check_depth",
    "shortest_path",
    "statement",
]
