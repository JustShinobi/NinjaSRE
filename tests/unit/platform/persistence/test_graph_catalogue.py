"""The graph catalogue is closed, and closed at import rather than at call time.

``platform/persistence/ports/topology_graph.py`` makes FR-016 true of the port's
*signatures* — nothing there takes a query, so nothing a model writes can reach
one. ``tests/contract/persistence/test_topology_graph.py`` asserts that.

This asserts the other half, one layer down, and it is the half that was
claimed in a docstring and never checked: that the statements the repository can
actually issue are a named, reviewable set, and that every one of them is
finished before any caller exists. A query shape added without a line in
``STATEMENTS`` is a shape nobody reviewed, and it is exactly the change this
file exists to fail on.
"""

from __future__ import annotations

import pytest

from config.constants.persistence import MAX_GRAPH_DEPTH
from platform.persistence.errors import BoundExceeded
from platform.persistence.postgres.graph import queries

pytestmark = pytest.mark.unit

#: A module-level string is a statement if it reads like one. Both languages are
#: in play — Cypher for the writes, SQL for the reads — so both openers count.
_OPENERS = ("SELECT", "WITH RECURSIVE", "MATCH", "MERGE")

#: Shared sub-expressions rather than shapes. A fragment cannot be run and
#: cannot be reached by a caller; it is spelled once so that the statements
#: built from it cannot disagree about what, say, a dependency edge is.
_FRAGMENTS = frozenset({"ANCHOR"})


def _statement_constants() -> dict[str, str]:
    """Return every public string constant in the module that reads as a statement."""
    return {
        name: value
        for name, value in vars(queries).items()
        if not name.startswith("_")
        and name not in _FRAGMENTS
        and isinstance(value, str)
        and any(opener in value.upper() for opener in _OPENERS)
    }


def test_every_statement_the_module_defines_is_registered_in_the_catalogue() -> None:
    """A shape that is not in ``STATEMENTS`` is a shape nobody reviewed."""
    unregistered = {
        name for name, value in _statement_constants().items() if value not in queries.STATEMENTS
    }
    assert not unregistered, (
        f"{sorted(unregistered)} are runnable statements that no line of STATEMENTS names. "
        "Add them there — that line is the review."
    )


def test_the_depth_parameterised_shapes_are_rendered_once_per_legal_depth() -> None:
    """Every legal depth has a finished statement waiting, and no other depth does.

    This is what keeps a caller's depth a *selector* rather than an input to
    string formatting. Index 0 is deliberately unusable: depth counts hops, and
    a traversal of zero hops is not a traversal.
    """
    for rendered in (queries.BLAST_RADIUS_BY_DEPTH, queries.SHORTEST_PATH_BY_DEPTH):
        assert len(rendered) == MAX_GRAPH_DEPTH + 1
        assert rendered[0] == ""
        assert all(rendered[depth] for depth in range(1, MAX_GRAPH_DEPTH + 1))


def test_every_value_a_statement_takes_arrives_as_a_bind_parameter() -> None:
    """The only hole in a finished statement is one PostgreSQL fills itself.

    Braces are not the tell here — Cypher writes a map as ``{node_id: $node_id}``
    and always will. What would matter is a statement carrying a hole that
    *Python* fills, because that is the one a caller's text could reach. Every
    statement below takes its values through ``$1``, and the only literals in a
    traversal are the ones this module rendered from a validated integer.
    """
    for name, value in _statement_constants().items():
        assert "%s" not in value, f"{name} carries a printf placeholder"
        assert "$1" in value, f"{name} takes no bind parameter, so its values are inlined"


@pytest.mark.parametrize("depth", [MAX_GRAPH_DEPTH + 1, MAX_GRAPH_DEPTH + 100])
def test_a_depth_past_the_bound_never_reaches_a_statement(depth: int) -> None:
    """The bound is refused rather than clamped, and refused before any lookup.

    Clamping would answer a depth-40 question with a depth-4 answer and look
    complete while being wrong.
    """
    with pytest.raises(BoundExceeded) as failure:
        queries.blast_radius(depth)
    assert failure.value.constant == "MAX_GRAPH_DEPTH"

    with pytest.raises(BoundExceeded):
        queries.shortest_path(depth)


def test_a_traversal_of_no_hops_is_refused() -> None:
    """Zero and negative depths are a caller error, not an empty answer."""
    for depth in (0, -1):
        with pytest.raises(ValueError, match="at least one hop"):
            queries.blast_radius(depth)


def test_the_reads_are_anchored_by_containment_so_the_index_is_the_one_that_serves_them() -> None:
    """The GIN index answers ``@>`` and nothing else.

    A read rewritten to compare an extracted key would still return the right
    rows and would silently stop using the index — a correctness-preserving
    change that costs a sequential scan per traversal. Naming the predicate here
    is what makes that regression visible.
    """
    anchored = [
        queries.DIRECT_DEPENDENCIES,
        queries.DIRECT_DEPENDENTS,
        queries.COMPONENTS_FOR_EPISODE,
        queries.EPISODES_FOR_COMPONENT,
        queries.EDGES_FROM,
        *queries.BLAST_RADIUS_BY_DEPTH[1:],
    ]
    for statement in anchored:
        assert "properties @> $1::ag_catalog.agtype" in statement


def test_a_dependency_traversal_never_crosses_an_involvement_edge() -> None:
    """An episode touching two services does not make either depend on the other."""
    for statement in (
        queries.DIRECT_DEPENDENCIES,
        queries.DIRECT_DEPENDENTS,
        queries.EDGES_FROM,
        *queries.BLAST_RADIUS_BY_DEPTH[1:],
    ):
        assert queries.NOT_INVOLVED in statement

    for statement in (queries.COMPONENTS_FOR_EPISODE, queries.EPISODES_FOR_COMPONENT):
        assert queries.IS_INVOLVED in statement
