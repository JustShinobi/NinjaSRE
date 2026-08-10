"""The composition root: one object a deployment holds, and the order it enforces.

Every write goes through ``set_settings`` and it does the same six things in the
same order, which is the whole reason this class exists rather than a set of
functions a caller composes:

1. read the node and its chain
2. refuse anything an ancestor locked (FR-005)
3. validate shape, references, and secrets (FR-011, FR-012, FR-013)
4. route approval-gated changes to the queue instead of applying them (FR-007)
5. persist, with optimistic concurrency
6. audit each changed field, values filtered (FR-021, FR-022)

The order is load-bearing at two points. **Validation precedes persistence**,
always, on every path — a caller that could store first and validate afterwards
is a caller that will. And **the audit of a refusal is written even though the
write failed**, in a transaction of its own, because an attempt to put a
credential into configuration is exactly the event worth knowing about.

**Approval-gated changes raise rather than return.** ``ChangeRequiresApproval``
carries the queued request's id. Returning the unchanged node would leave the
caller's next line reading as though the change had taken effect, and the caller
is usually a console that has just told somebody "saved".
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from platform.config_service import paths
from platform.config_service.audit import ConfigAuditor, record, settings_after
from platform.config_service.catalogue import (
    CapabilityCatalogueReader,
    CatalogueView,
    IntegrationDirectory,
    IntegrationSchema,
    integration_forms,
)
from platform.config_service.document import NodeDocument
from platform.config_service.effective import (
    EffectiveConfig,
    EffectiveConfigCache,
    EffectiveConfigResolver,
)
from platform.config_service.errors import (
    ChangeRequiresApproval,
    ConfigInvalid,
    FieldLocked,
    UnknownNode,
)
from platform.config_service.field_policy import (
    FieldPolicy,
    PolicySet,
    changed_paths,
    check_lock_addition,
    check_locks,
    gated_paths,
    merged_along,
)
from platform.config_service.hierarchy import Hierarchy
from platform.config_service.merge import deep_prune
from platform.config_service.preview import ConfigPreview, preview_of
from platform.config_service.templates import TemplateDiff, TemplateLibrary
from platform.config_service.validation import ConfigValidator
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import (
    ActorKind,
    ApprovalRequest,
    ConfigNode,
    ConfigNodeKind,
    PersistenceGateway,
    TenantScope,
)

#: What a configuration change is called in the approval queue.
CONFIG_APPROVAL_ACTION = "config.change"

#: How long a queued configuration change stays answerable. Longer than an
#: action approval, because a prompt change is not something anybody should
#: approve during an incident.
CONFIG_APPROVAL_EXPIRY_HOURS = 72.0


@runtime_checkable
class GatedChangeQueue(Protocol):
    """Whatever takes a gated write away and gives back something to quote.

    Declared here and implemented elsewhere, on purpose. A deployment routes
    gated configuration writes through the platform's one approval mechanism —
    conflict detection, decision-time permission re-checking, blast radius,
    cross-surface closure — and this service must not import that layer to say
    so. The approval layer knows about configuration; configuration knows only
    that *something* takes its gated writes.

    Without one, ``set_settings`` still refuses to apply a gated change and
    still queues a request. It just queues the plain one this service can write
    on its own, which is the correct degraded behaviour: less review machinery,
    never less gating.
    """

    async def __call__(
        self,
        *,
        node_id: str,
        settings: Mapping[str, Any],
        gated_paths: tuple[str, ...],
        actor_id: str,
    ) -> str:
        """Queue the change and return the identifier the refusal will name."""


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


class ConfigService:
    """The hierarchy, its configuration, and everything that guards a write."""

    __slots__ = (
        "_approvals",
        "_auditor",
        "_catalogue",
        "_clock",
        "_gateway",
        "_integrations",
        "_resolver",
        "_scope",
        "_templates",
        "_validator",
    )

    def __init__(
        self,
        *,
        gateway: PersistenceGateway,
        scope: TenantScope,
        catalogue: CapabilityCatalogueReader | None = None,
        integrations: IntegrationDirectory | None = None,
        guardrails: GuardrailEngine | None = None,
        templates: TemplateLibrary | None = None,
        cache: EffectiveConfigCache | None = None,
        approvals: GatedChangeQueue | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        engine = guardrails if guardrails is not None else GuardrailEngine()
        self._gateway = gateway
        self._scope = scope
        self._catalogue = catalogue
        self._integrations = integrations
        self._approvals = approvals
        self._clock = clock
        self._templates = templates if templates is not None else TemplateLibrary.golden()
        self._validator = ConfigValidator(
            catalogue=catalogue, integrations=integrations, guardrails=engine
        )
        self._auditor = ConfigAuditor(guardrails=engine, clock=clock)
        self._resolver = EffectiveConfigResolver(gateway=gateway, scope=scope, cache=cache)

    # --- Reading -------------------------------------------------------------

    async def resolve(self, node_id: str) -> EffectiveConfig:
        """Return ``node_id``'s effective configuration, with provenance (FR-014)."""
        return await self._resolver.resolve(node_id)

    async def document(self, node_id: str) -> NodeDocument:
        """Return the node's own stored settings and policies, unmerged."""
        return NodeDocument.of_node(await self._node(node_id))

    async def hierarchy(self) -> Hierarchy:
        """Return this tenant's whole tree.

        One read of every node. Used by the operations that need the shape
        rather than one chain — a deletion check, a reparent, and the
        lock-conflict scan — and deliberately not by resolution, which reads one
        indexed chain instead.
        """
        async with self._gateway.begin(self._scope) as uow:
            root = await uow.config.root()
            found = [root]
            frontier = [root.node_id]
            while frontier:
                for child in await uow.config.children(frontier.pop()):
                    found.append(child)
                    frontier.append(child.node_id)
        return Hierarchy.of(found)

    async def catalogue_view(self, node_id: str) -> CatalogueView:
        """Return what ``node_id`` can run, and why anything else it cannot (FR-017)."""
        if self._catalogue is None:
            return CatalogueView()
        effective = await self.resolve(node_id)
        return CatalogueView.of(self._catalogue, effective.config)

    async def integration_schemas(self, node_id: str) -> tuple[IntegrationSchema, ...]:
        """Return the schemas the console renders credential forms from (FR-018)."""
        if self._integrations is None:
            return ()
        effective = await self.resolve(node_id)
        return integration_forms(self._integrations, effective.config)

    def template_names(self) -> tuple[str, ...]:
        """Return the configuration templates this deployment can apply."""
        return self._templates.names()

    async def preview_template(self, node_id: str, template: str) -> TemplateDiff:
        """Return what applying ``template`` to ``node_id`` would change (FR-019)."""
        document = await self.document(node_id)
        return self._templates.preview(template, document.settings)

    async def preview_settings(
        self, node_id: str, patch: Mapping[str, Any], remove: Sequence[str] = ()
    ) -> ConfigPreview:
        """Return what applying ``patch`` to ``node_id`` would resolve to, storing nothing.

        The same chain, the same merge, and the same lock and gate rules
        ``set_settings`` applies — which is the only thing that makes the answer
        worth showing somebody before they commit to it. ``remove`` is the same
        clear-to-inherit list the write takes, so a preview of a clear and the
        clear itself cannot disagree either.
        """
        return preview_of(node_id, await self._chain(node_id), patch, remove)

    # --- Writing -------------------------------------------------------------

    async def set_settings(
        self,
        node_id: str,
        patch: Mapping[str, Any],
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
        replace: bool = False,
        remove: Sequence[str] = (),
    ) -> ConfigNode:
        """Apply ``patch`` to ``node_id``'s own settings and return the stored node.

        ``patch`` is merged onto what is there unless ``replace`` is set, which
        is what makes "change the masking level" one field rather than a whole
        document a caller had to reconstruct and could get wrong.

        ``remove`` clears node-local values, so the field goes back to being
        inherited. It is a first-class operation rather than "set it to the
        parent's value", because the two diverge the moment the parent changes:
        one follows, and one froze today's answer into this node.
        """
        node = await self._node(node_id)
        document = NodeDocument.of_node(node)
        proposed = (
            dict(deep_prune(patch, remove))
            if replace
            else dict(settings_after(document.settings, patch, remove))
        )

        chain = await self._chain(node_id)
        inherited_locks = _inherited_locks(chain[:-1])
        check_locks(node_id, proposed, inherited_locks, own=document.policies)
        _check_removable(node_id, remove, inherited_locks, own=document.policies)

        await self._validate_or_audit(node_id, proposed, actor_id, actor_kind)

        changed = changed_paths(document.settings, proposed)
        gated = gated_paths(changed, merged_along(_policies(chain)))
        if gated:
            raise ChangeRequiresApproval(
                node_id, gated, await self._queue(node_id, proposed, gated, actor_id)
            )

        stored = await self._store(node, document.with_settings(proposed))
        await record(
            self._gateway,
            self._scope,
            self._auditor.events(
                self._auditor.changes(node_id, document.settings, proposed),
                actor_id=actor_id,
                actor_kind=actor_kind,
            ),
        )
        return stored

    async def apply_template(
        self,
        node_id: str,
        template: str,
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
    ) -> ConfigNode:
        """Apply a template to ``node_id``, auditing each field it changed."""
        node = await self._node(node_id)
        document = NodeDocument.of_node(node)
        diff = self._templates.preview(template, document.settings)

        chain = await self._chain(node_id)
        check_locks(node_id, diff.settings, _inherited_locks(chain[:-1]), own=document.policies)
        await self._validate_or_audit(node_id, diff.settings, actor_id, actor_kind)

        stored = await self._store(node, document.with_settings(diff.settings))
        await record(
            self._gateway,
            self._scope,
            self._auditor.template_events(
                node_id,
                template,
                document.settings,
                diff.settings,
                actor_id=actor_id,
                actor_kind=actor_kind,
            ),
        )
        return stored

    async def set_policy(
        self,
        node_id: str,
        policy: FieldPolicy,
        *,
        actor_id: str,
        actor_kind: ActorKind = ActorKind.USER,
    ) -> ConfigNode:
        """Declare ``policy`` at ``node_id``, refusing a lock over an existing override.

        FR-009: adding a lock where a descendant already sets the field would
        change what those descendants resolve to, and the operator adding it is
        the one person who cannot see that happen.
        """
        node = await self._node(node_id)
        document = NodeDocument.of_node(node)

        if policy.locked:
            tree = await self.hierarchy()
            check_lock_addition(
                policy.path,
                node_id,
                {
                    descendant.node_id: NodeDocument.of_node(descendant).settings
                    for descendant in tree.descendants(node_id)
                },
            )

        stored = await self._store(
            node, document.with_policies(document.policies.with_policy(policy))
        )
        await record(
            self._gateway,
            self._scope,
            [
                self._auditor.policy_event(
                    node_id,
                    policy.path,
                    policy.to_record(),
                    actor_id=actor_id,
                    actor_kind=actor_kind,
                )
            ],
        )
        return stored

    async def create_node(
        self,
        node_id: str,
        *,
        name: str,
        parent_id: str,
        kind: ConfigNodeKind = ConfigNodeKind.TEAM,
    ) -> ConfigNode:
        """Create an empty node beneath ``parent_id``.

        Empty on purpose: a node created with configuration would be a node
        created without a lock check. Configure it with ``set_settings``.
        """
        await self._node(parent_id)
        async with self._gateway.begin(self._scope) as uow:
            return await uow.config.upsert(
                ConfigNode(
                    node_id=node_id,
                    kind=kind,
                    name=name,
                    parent_id=parent_id,
                    values=NodeDocument().to_values(),
                )
            )

    async def delete_node(self, node_id: str) -> bool:
        """Delete ``node_id``, refusing while any descendant inherits from it (FR-004)."""
        tree = await self.hierarchy()
        tree.check_deletable(node_id)
        async with self._gateway.begin(self._scope) as uow:
            deleted = await uow.config.delete(node_id)
        self._resolver.invalidate(node_id)
        return deleted

    async def reparent_node(self, node_id: str, new_parent_id: str) -> ConfigNode:
        """Move ``node_id`` under ``new_parent_id``, refusing a cycle.

        The subtree's effective configuration changes, and nothing needs
        invalidating: every descendant's chain now contains a different set of
        nodes, so every fingerprint differs and the next resolution recomputes.
        """
        tree = await self.hierarchy()
        moved = tree.reparent(node_id, new_parent_id)
        async with self._gateway.begin(self._scope) as uow:
            return await uow.config.upsert(moved.node(node_id))

    # --- Internals -----------------------------------------------------------

    async def _node(self, node_id: str) -> ConfigNode:
        """Return the node, or raise naming it."""
        async with self._gateway.begin(self._scope) as uow:
            found = await uow.config.get(node_id)
        if found is None:
            raise UnknownNode(node_id)
        return found

    async def _chain(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return ``node_id``'s chain, root-first and inclusive."""
        async with self._gateway.begin(self._scope) as uow:
            try:
                chain = await uow.config.ancestors(node_id)
            except RecordNotFound as absent:
                raise UnknownNode(node_id) from absent
        if not chain:
            raise UnknownNode(node_id)
        return chain

    async def _store(self, node: ConfigNode, document: NodeDocument) -> ConfigNode:
        """Persist ``document`` onto ``node``, carrying its version forward.

        The version is the one read at the start of the operation, so a
        concurrent write raises ``ConcurrentModification`` rather than silently
        winning. Two operators editing one node have made a decision the store
        is not entitled to make for them.
        """
        async with self._gateway.begin(self._scope) as uow:
            return await uow.config.upsert(
                ConfigNode(
                    node_id=node.node_id,
                    kind=node.kind,
                    name=node.name,
                    parent_id=node.parent_id,
                    values=document.to_values(),
                    version=node.version,
                )
            )

    async def _validate_or_audit(
        self,
        node_id: str,
        settings: Mapping[str, Any],
        actor_id: str,
        actor_kind: ActorKind,
    ) -> None:
        """Validate ``settings``, auditing the refusal before raising it.

        The audit of a refused write is written even though the write failed,
        and it carries the path and the reason but never the value — an attempt
        to store a credential in configuration is worth knowing about, and the
        record of it must not be where the credential survives.
        """
        outcome = self._validator.validate(settings)
        if outcome.ok:
            return
        await record(
            self._gateway,
            self._scope,
            self._auditor.rejection_events(
                node_id,
                [(error.path, error.message) for error in outcome.errors],
                actor_id=actor_id,
                actor_kind=actor_kind,
            ),
        )
        raise ConfigInvalid(outcome.errors)

    async def _queue(
        self,
        node_id: str,
        settings: Mapping[str, Any],
        gated: Sequence[str],
        actor_id: str,
    ) -> str:
        """Queue an approval-gated change and return its identifier (FR-007).

        Through the platform's approval mechanism when one is wired, so a
        configuration change gets the same conflict detection, decision-time
        permission re-checking, blast radius, and cross-surface closure as every
        other gated change. Without one, the plain request below is written
        instead — the change is still gated, it just carries less review
        machinery with it.

        The proposed settings are stored on the request verbatim, filtered the
        same way an audit value is. An approval granted against different
        settings from the ones applied is not an approval, and keeping the exact
        document is what lets the trail prove they matched.
        """
        if self._approvals is not None:
            return await self._approvals(
                node_id=node_id,
                settings=self._auditor.filtered(dict(settings)),
                gated_paths=tuple(sorted(gated)),
                actor_id=actor_id,
            )

        at = self._clock()
        request = ApprovalRequest(
            approval_id=str(uuid.uuid4()),
            run_id=f"config:{node_id}",
            action=CONFIG_APPROVAL_ACTION,
            side_effect_level="write_reversible",
            summary=f"Configuration change to {node_id}: {', '.join(sorted(gated))}",
            requested_at=at,
            expires_at=at + timedelta(hours=CONFIG_APPROVAL_EXPIRY_HOURS),
            arguments={
                "node_id": node_id,
                "requested_by": actor_id,
                "gated_fields": sorted(gated),
                "settings": self._auditor.filtered(dict(settings)),
            },
        )
        async with self._gateway.begin(self._scope) as uow:
            stored = await uow.approvals.create_request(request)
        return stored.approval_id


def _check_removable(
    node_id: str,
    remove: Sequence[str],
    inherited_locks: Mapping[str, str],
    own: PolicySet,
) -> None:
    """Raise ``FieldLocked`` if a clear names a path an ancestor locked.

    ``check_locks`` cannot see this one: a removal leaves *nothing* at the path,
    so there is no leaf in the proposed document to test. Without this, clearing
    a locked field would report success and change nothing, which tells an
    operator they lifted a constraint they cannot lift.
    """
    exempt = own.locked_paths()
    for path in remove:
        for candidate in paths.prefixes(path):
            if candidate in exempt:
                break
            locking = inherited_locks.get(candidate)
            if locking is not None:
                raise FieldLocked(path=path, locking_node_id=locking, node_id=node_id)


def _policies(chain: Sequence[ConfigNode]) -> tuple[PolicySet, ...]:
    """Return each node's declared policies, root-first."""
    return tuple(NodeDocument.of_node(node).policies for node in chain)


def _inherited_locks(ancestors: Sequence[ConfigNode]) -> dict[str, str]:
    """Return the paths ``ancestors`` lock, mapped to the outermost node locking each."""
    locks: dict[str, str] = {}
    for node in ancestors:
        for path in NodeDocument.of_node(node).policies.locked_paths():
            locks.setdefault(path, node.node_id)
    return locks


__all__ = [
    "CONFIG_APPROVAL_ACTION",
    "CONFIG_APPROVAL_EXPIRY_HOURS",
    "ConfigService",
    "GatedChangeQueue",
]
