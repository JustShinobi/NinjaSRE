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
from platform.config_service.fields import fields_at
from platform.config_service.schema.policies import GuardianSettings
from platform.config_service.service import ConfigService
from platform.guardian.resolution import resolve as resolve_guardian
from platform.guardian.topology import ClusterShape
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
    #: Paths whose node-local value goes, so the field is inherited again.
    #:
    #: Beside the patch rather than inside it, because no key in a configuration
    #: document is ever a directive — a field called ``_delete`` is a field
    #: called ``_delete``. Clearing an override is also not the same operation as
    #: setting it to the parent's current value: one keeps following the parent,
    #: the other freezes today's answer into this node.
    remove: list[str] = Field(default_factory=list)


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


class InheritedValueView(BaseModel):
    """One path, a value, and the node that supplies it from above."""

    path: str
    value: Any = None
    #: Empty when nothing above supplies the field at all.
    inherited_from: str


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
    #: Paths the patch would set to exactly what this node already inherits. The
    #: write is real — the field becomes locally set — and resolves to the same
    #: value it resolved to before, which is why "I changed it and nothing
    #: happened" is the most common configuration complaint there is.
    redundant: list[InheritedValueView] = Field(default_factory=list)
    #: Paths ``remove`` would clear, and what each falls back to once it is gone.
    reverts: list[InheritedValueView] = Field(default_factory=list)


class ConfigFieldView(BaseModel):
    """One editable field, as the schema declares it and this node stands on it.

    Everything a client needs to draw a control and to know what pressing save
    would do — and nothing it could have worked out for itself, because there is
    nothing here it could have. The type, range and default come from the
    Pydantic section the write path validates against; the value, provenance,
    lock and gate come from this node's chain.
    """

    path: str
    label: str
    type: str
    description: str = ""
    section: str = ""
    section_summary: str = ""
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    max_items: int | None = None
    max_length: int | None = None
    allowed_values: list[Any] | None = None
    value: Any = None
    #: The node supplying the effective value, or empty when nothing sets it.
    provenance: str = ""
    #: Whether *this* node overrides the field, which is the only case in which
    #: "clear this override" is an operation at all.
    set_here: bool = False
    locked_by: str = ""
    approval_gated: bool = False
    required: bool = False


class ConfigFieldsView(BaseModel):
    fields: list[ConfigFieldView]


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


class ShippedDetectorView(BaseModel):
    """One shipped detector, with the reasoning a client renders beside it.

    The rationale and the remedy travel with the detector rather than being
    fetched separately, because the requirement they satisfy is about *when*
    somebody reads them: at the moment they are deciding whether the threshold
    is wrong for their cluster. A second round trip is a click, and a click is
    the difference between a number understood and a number obeyed.
    """

    detector_id: str
    name: str
    watches: str
    threshold: str
    rationale: str
    remedy: str
    signal: str
    origin: str
    matcher: str = ""
    resource_kinds: list[str] = Field(default_factory=list)
    severity: str = ""
    topology: str = ""
    fire_value: float = 0.0
    clear_value: float = 0.0
    for_seconds: int = 0
    acknowledged_to_clear: bool = False


class GuardianProblemView(BaseModel):
    detector_id: str
    reason: str


class GuardianView(BaseModel):
    """The shipped detector set as one node actually runs it."""

    enabled: bool = False
    cluster_shape: str = ""
    cluster_shape_description: str = ""
    detectors: list[ShippedDetectorView] = Field(default_factory=list)
    not_applicable: list[str] = Field(default_factory=list)
    problems: list[GuardianProblemView] = Field(default_factory=list)


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
    """Apply a patch to ``node_id``'s own settings and return the new effective view.

    Given the integration directory, and deliberately not the capability
    catalogue. The directory is what lets validation refuse a field a vendor's
    own schema calls secret, which is the way round
    ``PUT /v1/integrations/{name}/credential`` and has to be shut. The catalogue
    would additionally make a write reject a capability reference that
    ``POST /{node_id}/preview`` accepts, and a preview that does not predict its
    own write is worse than a reference checked at read time.
    """
    await _check_scope(node_id, state, auth)
    service = ConfigService(
        gateway=state.gateway,
        scope=auth.scope,
        guardrails=state.guardrails,
        integrations=installed_integrations(),
    )
    await service.set_settings(
        node_id,
        body.patch,
        actor_id=auth.principal_id,
        actor_kind=ActorKind.USER,
        remove=tuple(body.remove),
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
    preview = await _service(state, auth).preview_settings(node_id, body.patch, tuple(body.remove))
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
        redundant=[
            InheritedValueView(
                path=entry.path, value=entry.value, inherited_from=entry.inherited_from
            )
            for entry in preview.redundant
        ],
        reverts=[
            InheritedValueView(
                path=entry.path, value=entry.value, inherited_from=entry.inherited_from
            )
            for entry in preview.reverts
        ],
    )


@router.get("/{node_id}/fields", response_model=ConfigFieldsView)
async def node_fields(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> ConfigFieldsView:
    """Return every field this node can be edited by, described by the schema.

    Served rather than shipped in a client, for the reason the whole
    configuration surface is: a client holding its own table of field types and
    ranges agrees with the deployment on the day it is written and drifts from
    then on. The drift arrives as a control offering a value the write path
    refuses, which reads to an operator as the platform being arbitrary.

    The per-node half — the value, which level supplied it, whether this node
    overrides it, what locks it — cannot be assembled by a client at all. It
    needs the ancestors' documents, and nothing outside this deployment has
    them.
    """
    await _check_scope(node_id, state, auth)
    service = _service(state, auth)
    effective = await service.resolve(node_id)
    document = await service.document(node_id)
    return ConfigFieldsView(
        fields=[
            ConfigFieldView(
                path=each.field.path,
                label=each.field.label,
                type=each.field.type,
                description=each.field.description,
                section=each.field.section,
                section_summary=each.field.section_summary,
                default=each.field.default,
                minimum=each.field.minimum,
                maximum=each.maximum,
                max_items=each.field.max_items,
                max_length=each.field.max_length,
                allowed_values=(None if each.allowed_values is None else list(each.allowed_values)),
                value=each.value,
                provenance=each.provenance,
                set_here=each.set_here,
                locked_by=each.locked_by,
                approval_gated=each.approval_gated,
                required=each.required,
            )
            for each in fields_at(effective, document)
        ]
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


@router.get("/{node_id}/guardian", response_model=GuardianView)
async def node_guardian(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> GuardianView:
    """Return the shipped detector set as ``node_id`` runs it (FR-015).

    Resolved here rather than by whatever is rendering it. The shipped
    catalogue, the detected topology and this node's overrides all meet in one
    function, and a client that combined them itself would be a client whose
    idea of what a threshold resolves to could drift from the deployment's —
    which is the failure that makes a reassuring screen wrong.

    Every detector that is *not* active is named too, because a detector missing
    from a list reads as one that does not exist, and an operator on a
    single-node installation deserves to know the quorum detectors are waiting
    for a second node.
    """
    await _check_scope(node_id, state, auth)
    effective = await _service(state, auth).resolve(node_id)
    settings = effective.config.policies.observation.guardian
    return GuardianView.model_validate(
        resolve_guardian(settings, shape=_shape_of(settings)).to_record()
    )


def _shape_of(settings: GuardianSettings) -> ClusterShape:
    """Return the topology recorded for this node, or the conservative default.

    Single-node for anything unrecognised, which is the answer that activates
    the fewest detectors: an unknown value must not make a listing claim that
    cluster detectors are running when nobody established there is a cluster.
    """
    try:
        return ClusterShape(settings.cluster_shape)
    except ValueError:
        return ClusterShape.SINGLE_NODE


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
