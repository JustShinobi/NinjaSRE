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

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config.constants.agents import OPERATING_CONTEXT_ROLES, OPERATING_CONTEXT_TOKEN_BUDGET
from core.capability.tokens import estimate_tokens
from gateway.http.catalogue_readers import installed_catalogue, installed_integrations
from gateway.http.deps import AuthenticatedRequest, authorized, get_state
from gateway.http.errors import not_found
from gateway.http.routes.tenancy import within_scope
from gateway.http.state import GatewayState
from platform.config_service.effective import EffectiveConfig
from platform.config_service.errors import UnknownNode
from platform.config_service.fields import ConfigField, fields_at
from platform.config_service.schema.agents import render_sections
from platform.config_service.schema.policies import GuardianSettings
from platform.config_service.schema.root import RootConfig
from platform.config_service.service import ConfigService
from platform.estate.operating_context import discovered_estate, template_for
from platform.guardian.resolution import resolve as resolve_guardian
from platform.guardian.topology import ClusterShape
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode

router = APIRouter(prefix="/v1/config", tags=["config"])

#: Where a section's provenance is looked up, and the role whose assembled
#: prompt the screen previews. The investigator rather than a specialist:
#: a specialist's prompt is built by the runtime from its own definition, and
#: the investigator's is the one an operator recognises.
_SECTIONS_PATH = "agents.operating_context.sections"
INVESTIGATOR_ROLE = "investigator"


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


class ContextSectionView(BaseModel):
    """One named section: what it says, and which level said it."""

    name: str
    body: str
    #: The node that supplied this section's body. Empty on a template section,
    #: which no node has supplied and which is not configuration until saved.
    provenance: str = ""


class OperatingContextView(BaseModel):
    """A node's operating context, its cost, and the prompt it becomes."""

    node_id: str
    enabled: bool
    sections: list[ContextSectionView] = Field(default_factory=list)
    #: The rendered block alone — heading and sections, nothing else.
    context: str = ""
    #: The whole system prompt the investigator's next run will be sent. The
    #: deployment's own assembly, so nothing downstream has to repeat it.
    prompt: str = ""
    tokens_used: int = 0
    token_budget: int = 0
    #: The roles the context is appended to. Served rather than assumed: which
    #: roles investigate is the deployment's answer, and a client holding its own
    #: copy would explain the wrong thing the day it changed.
    roles: list[str] = Field(default_factory=list)
    #: The starting document, derived from the estate. Empty once anything is
    #: written, because a suggestion that kept reappearing over an operator's own
    #: text is one they stop reading.
    template: list[ContextSectionView] = Field(default_factory=list)


class OperatingContextPatch(BaseModel):
    """A pending context, as a client holds it before deciding to save it."""

    sections: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    #: Section paths whose node-local value goes, so the section is inherited
    #: again. Beside the document for the reason every removal here is: no key in
    #: a configuration document is ever a directive.
    remove: list[str] = Field(default_factory=list)


class FieldErrorView(BaseModel):
    """One reason a document would be refused, at the path it is about."""

    path: str
    message: str


class OperatingContextPreviewView(BaseModel):
    """The prompt a pending context would produce, and everything wrong with it."""

    node_id: str
    prompt: str = ""
    context: str = ""
    tokens_used: int = 0
    token_budget: int = 0
    #: Measured against the *merged* result. A node whose own text fits can still
    #: inherit its way past the ceiling.
    over_budget: bool = False
    accepted: bool = True
    errors: list[FieldErrorView] = Field(default_factory=list)


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
    #: Every reason the write would be refused, from the validator the write
    #: runs. Empty is the ordinary answer. Reported rather than raised, because
    #: this is a preview and a refusal somebody can still act on is worth more
    #: than a 4xx: the values beside it are what the document *would* resolve to,
    #: which is the useful thing to look at while fixing the field that is wrong.
    errors: list[FieldErrorView] = Field(default_factory=list)
    #: Whether the write this preview describes would be accepted at all. Note
    #: that a gated change is accepted and queued rather than refused, so this is
    #: not the same question as ``requires_approval``.
    accepted: bool = True


class ItemFieldView(BaseModel):
    """One field inside an entry of an ordered list of objects.

    A separate model from ``ConfigFieldView`` because half of that one is about
    a node — provenance, whether this node sets it, which node locks it — and
    none of it is true of a field *inside* a list entry. A list replaces
    entirely, so the entry inherits the list's answer to all of those and has
    none of its own.
    """

    path: str
    label: str
    type: str
    description: str = ""
    #: The short, operator-facing text a form puts under the control.
    help: str = ""
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    max_length: int | None = None
    allowed_values: list[Any] | None = None


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
    #: The schema's own text, written for whoever reads the schema. ``help`` and
    #: ``section_help`` are the short forms of the same two things, written for
    #: whoever fills the form in, and they are the ones a form renders.
    description: str = ""
    help: str = ""
    section: str = ""
    section_summary: str = ""
    section_help: str = ""
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    max_items: int | None = None
    max_length: int | None = None
    allowed_values: list[Any] | None = None
    #: For an array of objects, what one entry is made of — each item's ``path``
    #: relative to the entry, because an entry nobody has added yet has no
    #: index. Empty for everything else, including an array of strings.
    item_fields: list[ItemFieldView] = Field(default_factory=list)
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
    min_scope: str = ""
    guide_url: str = ""


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


def _item_view(item: ConfigField) -> ItemFieldView:
    """Return one entry field as a client draws a control from it."""
    return ItemFieldView(
        path=item.path,
        label=item.label,
        type=item.type,
        description=item.description,
        help=item.help,
        default=item.default,
        minimum=item.minimum,
        maximum=item.maximum,
        max_length=item.max_length,
        allowed_values=(None if item.allowed_values is None else list(item.allowed_values)),
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
        min_scope=field_spec.min_scope,
        guide_url=field_spec.guide_url,
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

    Given both live registries, which is what makes validation here the same
    validation the read routes report. The integration directory is what lets a
    field a vendor's own schema calls secret be refused, which is the way round
    ``PUT /v1/integrations/{name}/credential`` and has to be shut. The capability
    catalogue is what lets a name no capability answers to be refused, which is
    otherwise a setting that stores happily and never does anything.

    Withholding the catalogue was once argued for on the grounds that a write
    would then refuse what ``POST /{node_id}/preview`` accepts. The preview runs
    no validation at all — it answers what a document would *resolve* to — so
    every refusal this route makes is already one the preview does not predict,
    and the argument protected a property that does not exist. Predicting them is
    worth doing, and it is a change to what the preview returns rather than a
    reason to check less here.
    """
    await _check_scope(node_id, state, auth)
    service = _service(state, auth)
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

    ``errors`` is the fourth thing the write decides and the last one this route
    learned to predict. The merge, the locks and the gates were always here;
    validation was not, so a document the write would refuse previewed clean and
    the refusal arrived as a 400 after somebody pressed save. It is reported
    rather than raised for the reason the whole surface exists: somebody who can
    still edit the field is better served by being told than by a status code.
    """
    await _check_scope(node_id, state, auth)
    service = _service(state, auth)
    preview = await service.preview_settings(node_id, body.patch, tuple(body.remove))
    outcome = await service.validation_of_write(node_id, body.patch, tuple(body.remove))
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
        errors=[FieldErrorView(path=error.path, message=error.message) for error in outcome.errors],
        accepted=outcome.ok,
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
                help=each.field.help,
                section=each.field.section,
                section_summary=each.field.section_summary,
                section_help=each.field.section_help,
                default=each.field.default,
                minimum=each.field.minimum,
                maximum=each.maximum,
                max_items=each.field.max_items,
                max_length=each.field.max_length,
                allowed_values=(None if each.allowed_values is None else list(each.allowed_values)),
                item_fields=[_item_view(item) for item in each.field.item_fields],
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


@router.get("/{node_id}/operating-context", response_model=OperatingContextView)
async def node_operating_context(
    node_id: str,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> OperatingContextView:
    """Return this node's operating context, what it costs, and the text it becomes.

    Three things a client cannot assemble for itself, and one it should not try.

    ``prompt`` is the *exact* string the investigator's next run will be sent —
    the shipped-or-overridden prompt with the rendered sections appended, by the
    same function the runtime hook uses. A console that concatenated the pieces
    itself would be a second implementation of the assembly, and the day it
    drifted somebody would approve a prompt nobody sends.

    ``provenance`` per section is the ancestors' documents, which nothing
    outside this deployment holds.

    ``template`` is served only where the node resolves to no sections at all.
    It is derived from what the estate has discovered — kinds, zones and their
    networks, the source answering each signal question — plus the facts that
    are true of any deployment of this kind and the questions only a person can
    answer. It is a suggestion: nothing here stores it, and it disappears the
    moment anything is written, because a field that kept re-offering its own
    starting text over somebody's edits is a field they stop editing.
    """
    await _check_scope(node_id, state, auth)
    effective = await _service(state, auth).resolve(node_id)
    agents = effective.config.agents
    context = agents.operating_context

    return OperatingContextView(
        node_id=node_id,
        enabled=context.enabled,
        sections=[
            ContextSectionView(
                name=name,
                body=body,
                provenance=effective.source_of(f"{_SECTIONS_PATH}.{name}") or "",
            )
            for name, body in context.sections.items()
        ],
        context=context.render(),
        prompt=agents.system_prompt_for(INVESTIGATOR_ROLE),
        tokens_used=context.tokens(),
        token_budget=OPERATING_CONTEXT_TOKEN_BUDGET,
        roles=list(OPERATING_CONTEXT_ROLES),
        template=[
            ContextSectionView(name=name, body=body)
            for name, body in await _template_for(node_id, state, auth, effective)
        ],
    )


@router.post("/{node_id}/operating-context/preview", response_model=OperatingContextPreviewView)
async def preview_operating_context(
    node_id: str,
    request: OperatingContextPatch,
    state: GatewayState = Depends(get_state),
    auth: AuthenticatedRequest = Depends(authorized),
) -> OperatingContextPreviewView:
    """Return the prompt this context would produce, and everything wrong with it.

    The 058 discipline, where the "effect" happens to be the most literal one on
    the platform: what a person is shown before saving is the *text the model
    will read*. Assembled by the deployment from the same merge and the same
    function a run uses, so there is no arrangement of the pieces a client could
    get differently.

    Two refusals are reported rather than raised, because this is a preview and
    a refusal an operator can still act on is worth more than a 4xx: a document
    past the token budget, and a section body carrying something
    credential-shaped. The second never quotes what it found — a refusal that
    echoed the secret would be the first place it was written down.

    ``over_budget`` is computed against the **merged** result rather than
    against this node's own document. A node whose own text fits can still
    inherit its way past the ceiling, and the resolution's answer to that is to
    send no context at all — which is safe and silent, and this is where it
    stops being silent.
    """
    await _check_scope(node_id, state, auth)
    service = _service(state, auth)
    patch = {
        "agents": {
            "operating_context": {
                "sections": dict(request.sections),
                "enabled": request.enabled,
            }
        }
    }

    outcome = service.validation_of(patch)
    preview = await service.preview_settings(node_id, patch, tuple(request.remove))
    resolved, _ = RootConfig.read(preview.values)
    context = resolved.agents.operating_context

    # A refused document renders no prompt. There is nothing to preview — this
    # text is never going to be sent — and the one case where it would matter is
    # the one where rendering is worst: a section carrying something
    # credential-shaped would come back inside a block labelled as what the model
    # will read, which is the opposite of what the refusal is for.
    return OperatingContextPreviewView(
        node_id=node_id,
        prompt=resolved.agents.system_prompt_for(INVESTIGATOR_ROLE) if outcome.ok else "",
        context=context.render() if outcome.ok else "",
        tokens_used=_merged_tokens(preview.values),
        token_budget=OPERATING_CONTEXT_TOKEN_BUDGET,
        over_budget=_merged_tokens(preview.values) > OPERATING_CONTEXT_TOKEN_BUDGET,
        accepted=outcome.ok,
        errors=[FieldErrorView(path=error.path, message=error.message) for error in outcome.errors],
    )


def _merged_tokens(values: Mapping[str, Any]) -> int:
    """Return what the merged sections cost, whether or not they build.

    Read off the merged document rather than off the typed section, because the
    typed section is exactly what disappears when the document is over budget —
    measuring the thing that survived would report zero for the case this number
    exists to name.
    """
    section = values.get("agents", {})
    written = section.get("operating_context", {}) if isinstance(section, Mapping) else {}
    sections = written.get("sections", {}) if isinstance(written, Mapping) else {}
    if not isinstance(sections, Mapping):
        return 0
    rendered = render_sections({str(name): str(body) for name, body in sections.items()})
    return estimate_tokens(rendered)


async def _template_for(
    node_id: str,
    state: GatewayState,
    auth: AuthenticatedRequest,
    effective: EffectiveConfig,
) -> tuple[tuple[str, str], ...]:
    """Return the starting document for ``node_id``, empty once anything is written."""
    del node_id
    if effective.config.agents.operating_context.sections:
        return ()
    discovered = await discovered_estate(
        state.gateway,
        auth.scope,
        configured_integrations=effective.config.integrations.enabled_names(),
    )
    return template_for(discovered)


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
