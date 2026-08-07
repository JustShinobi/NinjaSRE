"""Configuration: read the effective value at a node, write a patch to it.

``node_id`` is a path parameter, and that makes team scoping here different
from the run-shaped routes. The permission guard resolves against the
*token's own* node when the token is narrower than the organisation
(``platform/identity/authorisation.py``) — which proves the caller may read
or write *somewhere*, not that ``node_id`` is where. ``_check_scope`` is the
second half: it is what actually refuses a team-scoped token naming a node
outside its own subtree (SC-006).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.routes.tenancy import within_scope
from gateway.http.state import GatewayState
from platform.config_service.service import ConfigService
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.audit_repository import ActorKind

router = APIRouter(prefix="/v1/config", tags=["config"])


async def _check_scope(node_id: str, state: GatewayState, auth: AuthenticatedRequest) -> None:
    """Raise 404 unless ``node_id`` is the caller's own team or beneath it (SC-006).

    The permission guard alone does not catch this: a team-scoped token's own
    node always wins over whatever the path names
    (``platform/identity/authorisation.py``), so a route addressing an
    arbitrary node has to check the requested node is actually reachable
    itself.
    """
    if not auth.team_node_id:
        return
    async with state.gateway.begin(auth.scope) as uow:
        try:
            ancestors = await uow.config.ancestors(node_id)
        except RecordNotFound:
            ancestors = ()
    if not within_scope(node_id, auth, ancestors):
        raise not_found(f"no configuration node {node_id!r}")


class EffectiveConfigView(BaseModel):
    node_id: str
    values: dict[str, Any]
    provenance: dict[str, str]


class ConfigPatchRequest(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)


@router.get("/{node_id}", response_model=EffectiveConfigView)
async def get_config(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> EffectiveConfigView:
    """Return ``node_id``'s effective configuration, every value attributed."""
    await _check_scope(node_id, state, auth)
    service = ConfigService(gateway=state.gateway, scope=auth.scope, guardrails=state.guardrails)
    effective = await service.resolve(node_id)
    return EffectiveConfigView(
        node_id=node_id, values=dict(effective.values), provenance=dict(effective.provenance)
    )


@router.put("/{node_id}", response_model=EffectiveConfigView)
async def write_config(
    node_id: str,
    body: ConfigPatchRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> EffectiveConfigView:
    """Apply a patch to ``node_id``'s own settings and return the new effective view."""
    await _check_scope(node_id, state, auth)
    service = ConfigService(gateway=state.gateway, scope=auth.scope, guardrails=state.guardrails)
    await service.set_settings(
        node_id, body.patch, actor_id=auth.principal_id, actor_kind=ActorKind.USER
    )
    effective = await service.resolve(node_id)
    return EffectiveConfigView(
        node_id=node_id, values=dict(effective.values), provenance=dict(effective.provenance)
    )


__all__ = ["router"]
