"""What one service depends on, what depends on it, and what an outage reaches.

Three traversals in one response. A client exploring topology asks all three
about whichever node it is looking at, and answering them separately would be
three round trips to draw one picture.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.state import GatewayState
from platform.persistence.ports.topology_graph import TopologyNode

router = APIRouter(prefix="/v1/topology", tags=["topology"])

#: How far a blast radius reaches by default. Deep enough to include the
#: services an operator would page, bounded because a transitive closure over a
#: real estate is most of it.
DEFAULT_BLAST_RADIUS_DEPTH = 3


class TopologyNodeView(BaseModel):
    node_id: str
    kind: str
    name: str
    owner_node_id: str | None = None
    properties: dict[str, Any]


class BlastRadiusEntryView(BaseModel):
    node: TopologyNodeView
    depth: int


class TopologyView(BaseModel):
    node_id: str
    available: bool
    #: Why topology cannot answer, when it cannot. A deployment with no graph
    #: adapter says so rather than reporting an empty graph, which would read as
    #: "this service depends on nothing".
    reason: str | None = None
    dependencies: list[TopologyNodeView]
    dependents: list[TopologyNodeView]
    blast_radius: list[BlastRadiusEntryView]
    truncated: bool = False


def _view(node: TopologyNode) -> TopologyNodeView:
    return TopologyNodeView(
        node_id=node.node_id,
        kind=node.kind.value,
        name=node.name,
        owner_node_id=node.owner_node_id,
        properties=dict(node.properties),
    )


@router.get("/{node_id}", response_model=TopologyView)
async def get_topology(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
    depth: int = DEFAULT_BLAST_RADIUS_DEPTH,
) -> TopologyView:
    """Return ``node_id``'s dependencies, dependents, and blast radius (FR-014)."""
    async with state.gateway.begin(auth.scope) as uow:
        availability = await uow.topology.availability()
        if not availability.available:
            return TopologyView(
                node_id=node_id,
                available=False,
                reason=availability.reason,
                dependencies=[],
                dependents=[],
                blast_radius=[],
            )
        dependencies = await uow.topology.direct_dependencies(node_id)
        dependents = await uow.topology.direct_dependents(node_id)
        radius = await uow.topology.blast_radius(node_id, depth=depth)

    return TopologyView(
        node_id=node_id,
        available=True,
        dependencies=[_view(node) for node in dependencies.nodes],
        dependents=[_view(node) for node in dependents.nodes],
        blast_radius=[
            BlastRadiusEntryView(node=_view(entry.node), depth=entry.depth)
            for entry in radius.reaches
        ],
        truncated=dependencies.truncated or dependents.truncated or radius.truncated,
    )


__all__ = ["router"]
