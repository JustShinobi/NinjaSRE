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

from gateway.http.catalogue_readers import installed_catalogue, installed_integrations
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.routes.tenancy import within_scope
from gateway.http.state import GatewayState
from platform.config_service.errors import UnknownNode
from platform.config_service.service import ConfigService
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode

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


class ConfigNodeView(BaseModel):
    node_id: str
    kind: str
    name: str
    parent_id: str | None = None


class ConfigTreeView(BaseModel):
    nodes: list[ConfigNodeView]


class PreviewChangeView(BaseModel):
    path: str
    before: Any = None
    after: Any = None


class ConfigPreviewView(BaseModel):
    node_id: str
    values: dict[str, Any]
    provenance: dict[str, str]
    changes: list[PreviewChangeView]
    #: Patch paths an ancestor locked, mapped to the node holding the lock. Those
    #: paths keep their inherited value in ``values``.
    locked: dict[str, str]
    approval_gated: list[str]
    requires_approval: bool


class CatalogueEntryView(BaseModel):
    name: str
    kind: str
    summary: str
    tags: list[str]
    side_effect_level: str
    required_integrations: list[str]
    available: bool
    reason: str | None = None


class CatalogueEntriesView(BaseModel):
    entries: list[CatalogueEntryView]
    #: Which capabilities each unconnected integration would unlock — the one
    #: part of the picture a client cannot assemble from the entries alone.
    blocked_by_integration: dict[str, list[str]]


class CredentialFieldView(BaseModel):
    name: str
    label: str
    secret: bool
    required: bool
    help: str


class IntegrationSchemaView(BaseModel):
    name: str
    display_name: str
    credential_fields: list[CredentialFieldView]
    settings_fields: list[CredentialFieldView]
    hosts: list[str]


class IntegrationSchemasView(BaseModel):
    schemas: list[IntegrationSchemaView]


def _service(state: GatewayState, auth: AuthenticatedRequest) -> ConfigService:
    """Return a configuration service for this request, with the live registries.

    The catalogue and integration readers are the deployment's real ones —
    discovery, not a stored list — so a client rendering "what can this team
    run" can never be shown a catalogue the runtime disagrees with.
    """
    return ConfigService(
        gateway=state.gateway,
        scope=auth.scope,
        guardrails=state.guardrails,
        catalogue=installed_catalogue(),
        integrations=installed_integrations(),
    )


def _node_view(node: ConfigNode) -> ConfigNodeView:
    return ConfigNodeView(
        node_id=node.node_id,
        kind=node.kind.value,
        name=node.name,
        parent_id=node.parent_id,
    )


def _field_view(field_spec: Any) -> CredentialFieldView:
    return CredentialFieldView(
        name=field_spec.name,
        label=field_spec.label or field_spec.name,
        secret=field_spec.secret,
        required=field_spec.required,
        help=field_spec.help,
    )


@router.get("", response_model=ConfigTreeView)
async def config_tree(
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ConfigTreeView:
    """Return the nodes this caller may navigate, as one document (FR-016).

    One response rather than a walk. A client rendering an organisation tree
    needs the shape before it can render anything at all, and a node-by-node
    expansion would make a tree of several hundred nodes a request storm during
    the one hour anybody is looking at it.

    A team-scoped caller gets its own subtree and nothing else — the same
    asymmetry ``platform/identity/authorisation.py`` applies to grants, so a
    token narrower than the organisation cannot map the rest of it.
    """
    tree = await _service(state, auth).hierarchy()
    if not auth.team_node_id:
        return ConfigTreeView(nodes=[_node_view(node) for node in tree.nodes.values()])

    try:
        own = tree.node(auth.team_node_id)
    except UnknownNode as absent:
        raise not_found(f"no configuration node {auth.team_node_id!r}") from absent
    visible_nodes = (own, *tree.descendants(auth.team_node_id))
    return ConfigTreeView(nodes=[_node_view(node) for node in visible_nodes])


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


@router.post("/{node_id}/preview", response_model=ConfigPreviewView)
async def preview_config(
    node_id: str,
    body: ConfigPatchRequest,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ConfigPreviewView:
    """Return what saving ``patch`` would resolve to, storing nothing (FR-017).

    The server computes it, through the same merge a write would take. A client
    that merged the patch itself would be a second implementation of
    inheritance, locking, and gating — and the day it drifted, somebody would
    save a change that did something other than what they were shown.
    """
    await _check_scope(node_id, state, auth)
    preview = await _service(state, auth).preview_settings(node_id, body.patch)
    return ConfigPreviewView(
        node_id=preview.node_id,
        values=dict(preview.values),
        provenance=dict(preview.provenance),
        changes=[
            PreviewChangeView(path=change.path, before=change.before, after=change.after)
            for change in preview.changes
        ],
        locked=dict(preview.locked),
        approval_gated=list(preview.approval_gated),
        requires_approval=preview.requires_approval,
    )


@router.get("/{node_id}/catalogue", response_model=CatalogueEntriesView)
async def node_catalogue(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> CatalogueEntriesView:
    """Return what ``node_id`` can run, and why anything else it cannot (FR-021).

    Every installed capability appears, available or not. A capability missing
    from a list looks identical whether it was never written, is switched off
    for this team, or needs an integration nobody has connected — and only two
    of those are something an operator can fix in a minute.
    """
    await _check_scope(node_id, state, auth)
    view = await _service(state, auth).catalogue_view(node_id)
    return CatalogueEntriesView(
        entries=[
            CatalogueEntryView(
                name=entry.capability.name,
                kind=entry.capability.kind,
                summary=entry.capability.summary,
                tags=list(entry.capability.tags),
                side_effect_level=entry.capability.side_effect_level,
                required_integrations=list(entry.capability.required_integrations),
                available=entry.available,
                reason=entry.reason,
            )
            for entry in view.entries
        ],
        blocked_by_integration={
            name: list(names) for name, names in view.blocked_by_integration().items()
        },
    )


@router.get("/{node_id}/integration-schemas", response_model=IntegrationSchemasView)
async def node_integration_schemas(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> IntegrationSchemasView:
    """Return the schemas a client renders credential forms from (FR-020).

    Schemas, never values. What comes back says which fields a vendor's
    credential has and which of them are secret; no stored credential is
    readable through this route or any other, because no code path reveals one
    outside the proxy.
    """
    await _check_scope(node_id, state, auth)
    schemas = await _service(state, auth).integration_schemas(node_id)
    return IntegrationSchemasView(
        schemas=[
            IntegrationSchemaView(
                name=schema.name,
                display_name=schema.display_name or schema.name,
                credential_fields=[_field_view(each) for each in schema.credential_fields],
                settings_fields=[_field_view(each) for each in schema.settings_fields],
                hosts=list(schema.hosts),
            )
            for schema in schemas
        ]
    )


__all__ = ["router"]
