"""The catalogue: Cypher for the writes, indexed SQL for the reads.

FR-016 says LLM-generated Cypher must not be executed, and the port makes that
true of its signatures: nothing there takes a query. This module is where the
claim has to survive contact with Apache AGE, which constrains it in several
awkward ways.

**Neither a Cypher bound nor a SQL one can be parameterised.**
``[:DEPENDS_ON*1..$depth]`` is rejected by AGE, and a recursive term's depth
test is query text either way. That is the one place where a value reaches a
query as syntax rather than as a parameter.

The answer is not to format the depth in at call time. It is to render every
legal depth *once, here, at import*: there is one traversal per legal depth per
shape, and a caller's depth selects one from a frozen tuple after being
validated as an integer in range. A depth that is not an integer in
``1..MAX_GRAPH_DEPTH`` never reaches a string at all, and there is no code path
from caller text to query text.

Everything else — node ids, properties, labels — is a genuine parameter.

**Why the reads are SQL.** AGE's variable-length match is the wrong shape for a
blast radius. Its plan materialises every path and then joins the result against
the *whole* node table, so a traversal costs O(nodes in the graph) no matter how
small the answer is. Measured on a forty-thousand-node topology, a depth-5 blast
radius returning 242 nodes took a second; the same answer as a recursive walk
over the label tables, which follows edges by endpoint and touches only the
subgraph it reaches, takes six milliseconds and does not move when the graph
grows. AGE's label tables are ordinary PostgreSQL tables, so the walk is a
``WITH RECURSIVE`` over them, anchored by the GIN index and stepped by the
endpoint indexes that ``bootstrap`` creates.

That is a bounded, pre-rendered statement per depth exactly as the Cypher was.
Nothing about FR-016 changes: no caller text reaches a query here either.

**Why the writes stay Cypher.** ``MERGE`` gives create-or-match in one statement
with semantics worth having, and with the endpoint indexes in place it is fast
— an edge upsert is an index scan. Rewriting it as SQL would mean generating
graphids by hand for no gain.

Two more AGE limitations shape what is below:

- ``shortestPath()`` does not exist in AGE 1.6. A bounded shortest path is
  instead the shortest of the paths a bounded variable-length match returns,
  ordered by length and limited to one. It stays on Cypher because it is
  anchored at *both* ends, which is the case the VLE plan handles well — the
  join that ruins the blast radius is against one known node here, not against
  every node in the graph.
- ``SET n += $map`` is refused ("SET clause expects a map"). Arbitrary node
  properties are therefore stored as one JSON-encoded string property, and the
  merge that FR's "merge rather than replace" asks for happens in the
  repository, where the fake does it too.
"""

from __future__ import annotations

from collections.abc import Sequence
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

#: The other edge a dependency walk never crosses: a resource to a document
#: somebody wrote about it. A document cannot fail, so a blast radius that
#: reached one would answer "what does this outage take with it" with a runbook.
DOCUMENTED_BY_KIND: Final = "documented_by"

#: Every kind a dependency traversal excludes, named once. Two exclusions
#: spelled separately in five statements is how one of them comes to be missing
#: from the sixth.
UNTRAVERSED_KINDS: Final[tuple[str, ...]] = (INVOLVED_KIND, DOCUMENTED_BY_KIND)


#: The label tables, as SQL identifiers. AGE stores a label in an ordinary
#: table, which is what makes an indexed walk over one possible at all.
NODE_TABLE: Final = f'"{GRAPH}"."{NODE_LABEL}"'
EDGE_TABLE: Final = f'"{GRAPH}"."{EDGE_LABEL}"'

#: The single parameter every read takes: the anchor's properties, as agtype.
#: ``@>`` is containment, which is the predicate the GIN index serves and the
#: same one AGE compiles ``{node_id: $id}`` into.
ANCHOR: Final = f"SELECT id FROM {NODE_TABLE} WHERE properties @> $1::ag_catalog.agtype LIMIT 1"


def kind_of(alias: str) -> str:
    """Return the SQL that reads an edge's ``kind`` as agtype.

    Spelled out rather than written ``->``: the access operator is the form AGE
    itself generates, and it is the one guaranteed to stay valid across the
    extension's own versions.
    """
    return (
        f"ag_catalog.agtype_access_operator("
        f"VARIADIC ARRAY[{alias}.properties, '\"kind\"'::ag_catalog.agtype])"
    )


def property_of(alias: str, name: str) -> str:
    """Return the SQL that reads one property of a node or edge as agtype."""
    return (
        f"ag_catalog.agtype_access_operator("
        f"VARIADIC ARRAY[{alias}.properties, '\"{name}\"'::ag_catalog.agtype])"
    )


#: A dependency edge is any edge that is neither an involvement nor a document
#: link. An episode touching two services does not make either one depend on the
#: other, and a runbook about a container is not something the container needs.
NOT_INVOLVED: Final = " AND ".join(
    f"{kind_of('e')} <> '\"{kind}\"'::ag_catalog.agtype" for kind in UNTRAVERSED_KINDS
)

IS_INVOLVED: Final = f"{kind_of('e')} = '\"{INVOLVED_KIND}\"'::ag_catalog.agtype"


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
def edges_from(kinds: Sequence[str] = ()) -> str:
    """Return the edge read, for the dependency edges or for named kinds.

    No kinds means the dependency edges, which is what reconciliation asks for.
    Naming kinds returns exactly those, including the ones a dependency walk
    never crosses — which is how a resource's documents are read without them
    also appearing in its blast radius.

    The kinds are interpolated rather than bound, and they are safe to
    interpolate because they are ``EdgeKind`` values by the time they arrive:
    the repository takes the enumeration and passes ``.value``, so nothing a
    caller typed reaches here.
    """
    predicate = (
        " OR ".join(f"{kind_of('e')} = '\"{kind}\"'::ag_catalog.agtype" for kind in kinds)
        if kinds
        else NOT_INVOLVED
    )
    return f"""
SELECT {property_of("b", "node_id")}, {kind_of("e")}, {property_of("e", "properties")}
FROM {EDGE_TABLE} e
JOIN ({ANCHOR}) a ON e.start_id = a.id
JOIN {NODE_TABLE} b ON b.id = e.end_id
WHERE ({predicate})
ORDER BY 1, 2
LIMIT {MAX_GRAPH_RESULTS}
"""


#: The dependency-edge read, kept as a constant because it is the default and
#: because the catalogue is closed by what is named here.
EDGES_FROM = edges_from()


# --- One-hop reads --------------------------------------------------------------


def _one_hop(*, outward: bool, involved: bool) -> str:
    """Return the one-hop read in one direction, for one class of edge.

    Four shapes differing only in which endpoint anchors and whether the edge is
    an involvement, so they are one function rather than four near-identical
    blocks. Each is still a distinct constant below: the catalogue is closed by
    what is named here, not by what a caller could ask for.

    ``LIMIT MAX_GRAPH_RESULTS + 1`` is deliberate — one row past the bound is how
    the repository tells "exactly at the limit" from "cut short".

    Ordered by node id, and the order is what makes the *bound* meaningful: a
    hub with more neighbours than the bound returns a page, and a page chosen by
    whichever rows the join produced first is a different answer on a different
    day. ``GROUP BY`` rather than ``DISTINCT`` because ordering by an expression
    outside the select list is only legal over a grouped column, and adding the
    id to the select list would change the shape the repository reads.
    """
    near, far = ("start_id", "end_id") if outward else ("end_id", "start_id")
    return f"""
SELECT d.properties
FROM {EDGE_TABLE} e
JOIN ({ANCHOR}) a ON e.{near} = a.id
JOIN {NODE_TABLE} d ON d.id = e.{far}
WHERE {IS_INVOLVED if involved else NOT_INVOLVED}
GROUP BY d.id, d.properties
ORDER BY {property_of("d", "node_id")}
LIMIT {MAX_GRAPH_RESULTS + 1}
"""


DIRECT_DEPENDENCIES = _one_hop(outward=True, involved=False)

DIRECT_DEPENDENTS = _one_hop(outward=False, involved=False)

COMPONENTS_FOR_EPISODE = _one_hop(outward=True, involved=True)

EPISODES_FOR_COMPONENT = _one_hop(outward=False, involved=True)


# --- Bounded traversals ---------------------------------------------------------


def _blast_radius_at(depth: int) -> str:
    """Return the blast-radius traversal for one literal depth.

    A breadth-first walk *backwards* along dependency edges: an edge runs from
    the thing that would break to the thing whose failure would break it, so
    stepping from ``end_id`` to ``start_id`` is stepping from a service to the
    things it would take down with it.

    The depth column is what turns "which services" into "which services, and
    how close" — the question an operator under pressure is actually asking.
    A node reachable by two routes appears once, at its *nearest* hop count,
    which is how soon the failure arrives.

    Three details carry the correctness:

    - ``UNION`` rather than ``UNION ALL`` collapses the routes that reach the
      same node at the same depth. Without it a diamond multiplies rows at every
      further hop, which is the path explosion the old plan paid for.
    - The origin is excluded. It is not in its own blast radius, and the fake
      says so too by seeding its ``seen`` set with the node it started from.
    - The depth test lives in the recursive term, so the walk stops rather than
      being filtered afterwards. Combined with the exclusion above, a cycle
      terminates: there are only so many hops to take.
    """
    return f"""
WITH RECURSIVE anchor AS ({ANCHOR}),
walk AS (
    SELECT e.start_id AS id, 1 AS depth
    FROM {EDGE_TABLE} e
    JOIN anchor a ON e.end_id = a.id
    WHERE {NOT_INVOLVED}
  UNION
    SELECT e.start_id, w.depth + 1
    FROM walk w
    JOIN {EDGE_TABLE} e ON e.end_id = w.id
    WHERE w.depth < {depth} AND {NOT_INVOLVED}
)
SELECT d.properties, MIN(w.depth) AS hops
FROM walk w
JOIN {NODE_TABLE} d ON d.id = w.id
WHERE w.id <> (SELECT id FROM anchor)
GROUP BY d.id, d.properties
ORDER BY hops, {property_of("d", "node_id")}
LIMIT {MAX_GRAPH_RESULTS + 1}
"""


def _dependencies_at(depth: int) -> str:
    """Return the transitive-dependency walk for one literal depth.

    The same walk as the blast radius with the arrows the other way round:
    stepping from ``start_id`` to ``end_id`` moves from a service to what it
    rests on. Distances are not carried, because the caller of this one wants
    the set — ``blast_radius`` is the shape that answers "and how close".

    Ordered by node id so a page cut short by ``MAX_GRAPH_RESULTS`` is the same
    page on every run, rather than whichever rows the walk happened to reach
    first.
    """
    return f"""
WITH RECURSIVE anchor AS ({ANCHOR}),
walk AS (
    SELECT e.end_id AS id, 1 AS depth
    FROM {EDGE_TABLE} e
    JOIN anchor a ON e.start_id = a.id
    WHERE {NOT_INVOLVED}
  UNION
    SELECT e.end_id, w.depth + 1
    FROM walk w
    JOIN {EDGE_TABLE} e ON e.start_id = w.id
    WHERE w.depth < {depth} AND {NOT_INVOLVED}
)
SELECT d.properties
FROM walk w
JOIN {NODE_TABLE} d ON d.id = w.id
WHERE w.id <> (SELECT id FROM anchor)
GROUP BY d.id, d.properties
ORDER BY {property_of("d", "node_id")}
LIMIT {MAX_GRAPH_RESULTS + 1}
"""


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

DEPENDENCIES_BY_DEPTH: Final[tuple[str, ...]] = ("",) + tuple(
    _dependencies_at(depth) for depth in range(1, MAX_GRAPH_DEPTH + 1)
)

SHORTEST_PATH_BY_DEPTH: Final[tuple[str, ...]] = ("",) + tuple(
    _shortest_path_at(depth) for depth in range(1, MAX_GRAPH_DEPTH + 1)
)


def blast_radius(depth: int) -> str:
    """Return the pre-rendered blast-radius traversal for a validated depth."""
    return BLAST_RADIUS_BY_DEPTH[check_depth(depth)]


def transitive_dependencies(depth: int) -> str:
    """Return the pre-rendered dependency walk for a validated depth."""
    return DEPENDENCIES_BY_DEPTH[check_depth(depth)]


def shortest_path(depth: int = MAX_GRAPH_DEPTH) -> str:
    """Return the pre-rendered shortest-path traversal for a validated depth."""
    return SHORTEST_PATH_BY_DEPTH[check_depth(depth)]


#: Everything this module will ever run.
#: ``tests/unit/platform/persistence/test_graph_catalogue.py`` asserts that every
#: runnable statement defined here is named below, so a further query shape
#: cannot arrive without the line that reviews it.
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
        *DEPENDENCIES_BY_DEPTH[1:],
        *SHORTEST_PATH_BY_DEPTH[1:],
    }
)


__all__ = [
    "BLAST_RADIUS_BY_DEPTH",
    "COMPONENTS_FOR_EPISODE",
    "DELETE_EDGE",
    "DEPENDENCIES_BY_DEPTH",
    "DIRECT_DEPENDENCIES",
    "DIRECT_DEPENDENTS",
    "DOCUMENTED_BY_KIND",
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
    "UNTRAVERSED_KINDS",
    "UPSERT_NODE",
    "blast_radius",
    "edges_from",
    "check_depth",
    "shortest_path",
    "statement",
    "transitive_dependencies",
]
