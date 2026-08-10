"""What a proposed change would resolve to, without storing any of it.

A surface that offers "see the effect before saving" has two ways to answer the
question, and only one of them stays right. It can merge the patch itself —
which is a second implementation of inheritance, locks, and gating, and the day
it drifts from the real one is the day somebody saves a change that did
something other than what they were shown. Or it can ask the service that would
perform the write, which is this.

So the preview is deliberately not a separate calculation. It builds the same
chain a write builds, substitutes the node's proposed document into it, and
hands that to the same ``effective.build`` that ``resolve`` uses. The four
answers a reviewer needs — what the values become, where each came from, what
an ancestor locked, and what needs an approval — all fall out of the machinery
that would enforce them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from platform.config_service import paths
from platform.config_service.audit import settings_after
from platform.config_service.document import NodeDocument
from platform.config_service.effective import EffectiveConfig, build
from platform.config_service.field_policy import (
    PolicySet,
    changed_paths,
    gated_paths,
    merged_along,
)
from platform.config_service.merge import locked_paths_in, locking_node
from platform.persistence.ports import ConfigNode


@dataclass(frozen=True, slots=True)
class PreviewChange:
    """One leaf the patch would move, and what it would move between."""

    path: str
    before: Any = None
    after: Any = None


@dataclass(frozen=True, slots=True)
class RedundantValue:
    """One path the patch would set to exactly what the node already inherits.

    The most common configuration mistake there is, and the one a
    before-and-after table cannot show: the field really does change — from
    inherited to locally set — and resolves to the same value it resolved to
    before. An operator who does not see this reported concludes the change had
    no effect, and goes looking for the bug in the deployment.
    """

    path: str
    value: Any
    #: The node the same value already comes from.
    inherited_from: str


@dataclass(frozen=True, slots=True)
class RevertedValue:
    """One node-local value the patch would clear, and what takes over.

    ``inherited_from`` is empty when nothing above supplies the field: clearing
    it leaves the node with no value at all, which is a different outcome from
    falling back to a parent and has to read as one.
    """

    path: str
    value: Any
    inherited_from: str


@dataclass(frozen=True, slots=True)
class ConfigPreview:
    """What saving a patch would produce, and what would stop it.

    ``values`` and ``provenance`` are the effective result — what the node would
    resolve to afterwards, every value attributed to the node that supplied it.
    ``locked`` and ``approval_gated`` are the two reasons the result may not be
    what the patch asked for, reported separately because they need different
    actions: a lock is somebody else's decision to change, and a gate is a
    review to wait for.

    ``redundant`` and ``reverts`` are the two facts about *inheritance* the diff
    cannot carry on its own — a value being set to what is already inherited,
    and a local value being cleared back to it. Both are computed here rather
    than by whatever is rendering the preview, for the reason the whole module
    exists: only the service holds the ancestors' documents.
    """

    node_id: str
    values: Mapping[str, Any]
    provenance: Mapping[str, str]
    changes: tuple[PreviewChange, ...] = ()
    #: Patch paths an ancestor has locked, mapped to the node holding the lock.
    #: The lock wins: those paths keep their inherited value in ``values``.
    locked: Mapping[str, str] = None  # type: ignore[assignment]
    approval_gated: tuple[str, ...] = ()
    redundant: tuple[RedundantValue, ...] = ()
    reverts: tuple[RevertedValue, ...] = ()

    def __post_init__(self) -> None:
        if self.locked is None:
            object.__setattr__(self, "locked", {})

    @property
    def requires_approval(self) -> bool:
        """Return whether saving this patch would queue rather than apply."""
        return bool(self.approval_gated)

    @property
    def is_applicable(self) -> bool:
        """Return whether saving this patch would take effect immediately."""
        return not self.locked and not self.approval_gated


def preview_of(
    node_id: str,
    chain: Sequence[ConfigNode],
    patch: Mapping[str, Any],
    remove: Sequence[str] = (),
) -> ConfigPreview:
    """Return what applying ``patch`` and ``remove`` at the end of ``chain`` resolves to.

    ``chain`` is root-first and inclusive, exactly as a write reads it. The last
    entry is the node being changed; everything before it is what it inherits
    from and what may have locked a field against it.

    ``chain[:-1]`` is resolved a second time, on its own, and that is what makes
    the two inheritance answers possible: what the node would resolve to if it
    said nothing. A patch that lands on a value already coming from there is
    redundant, and a cleared field falls back to it.
    """
    node = chain[-1]
    document = NodeDocument.of_node(node)
    proposed = dict(settings_after(document.settings, patch, remove))

    proposed_chain = (*chain[:-1], _with_settings(node, document, proposed))
    effective = build(node_id, proposed_chain)
    inherited = build(node_id, chain[:-1])

    changed = changed_paths(document.settings, proposed)
    before = dict(paths.leaves(document.settings))
    after = dict(paths.leaves(proposed))
    inherited_locks = _inherited_locks(chain[:-1])

    return ConfigPreview(
        node_id=node_id,
        values=effective.values,
        provenance=dict(effective.provenance),
        changes=tuple(
            PreviewChange(path=path, before=before.get(path), after=_after(path, after, effective))
            for path in changed
        ),
        locked=dict(locked_paths_in(patch, inherited_locks)),
        approval_gated=gated_paths(changed, merged_along(_node_policies(chain))),
        redundant=_redundant(changed, after, inherited, inherited_locks),
        reverts=_reverts(before, after, remove, effective),
    )


def _after(path: str, after: Mapping[str, Any], effective: EffectiveConfig) -> Any:
    """Return what ``path`` reads as once the change is in.

    A path the node still sets afterwards reads as the value it sets — including
    an explicit null, which is why membership decides this rather than a
    ``None`` check. A path the node no longer sets reads as whatever it now
    inherits, which is the whole answer a clear-to-inherit is asking for.
    """
    if path in after:
        return after[path]
    return paths.value_at(effective.values, path)


def _redundant(
    changed: Sequence[str],
    after: Mapping[str, Any],
    inherited: EffectiveConfig,
    inherited_locks: Mapping[str, str],
) -> tuple[RedundantValue, ...]:
    """Return the changed paths whose new value is already what is inherited.

    A locked path is excluded. Its value does not move because an ancestor
    forbade the override, not because the operator restated something they
    already had, and telling them to remove an override the write never made
    would send them looking for one.
    """
    inherited_leaves = dict(paths.leaves(inherited.values))
    return tuple(
        RedundantValue(path=path, value=after[path], inherited_from=inherited.provenance[path])
        for path in changed
        if path in after
        and path in inherited.provenance
        and inherited_leaves.get(path) == after[path]
        and locking_node(inherited_locks, path) is None
    )


def _reverts(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    remove: Sequence[str],
    effective: EffectiveConfig,
) -> tuple[RevertedValue, ...]:
    """Return the node-local leaves ``remove`` clears, and what each falls back to.

    Restricted to leaves the removal actually covers. A patch can drop a leaf
    incidentally — by replacing a section with a scalar — and reporting that as
    a reversion would describe an override the operator is *creating* as one
    they are giving up.
    """
    return tuple(
        RevertedValue(
            path=path,
            value=paths.value_at(effective.values, path),
            inherited_from=effective.provenance.get(path, ""),
        )
        for path in sorted(before)
        if path not in after and any(paths.covers(pattern, path) for pattern in remove)
    )


def _with_settings(
    node: ConfigNode, document: NodeDocument, settings: Mapping[str, Any]
) -> ConfigNode:
    """Return ``node`` carrying ``settings``, for a merge that never persists."""
    return ConfigNode(
        node_id=node.node_id,
        kind=node.kind,
        name=node.name,
        parent_id=node.parent_id,
        values=document.with_settings(settings).to_values(),
        version=node.version,
    )


def _node_policies(chain: Sequence[ConfigNode]) -> tuple[PolicySet, ...]:
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
    "ConfigPreview",
    "PreviewChange",
    "RedundantValue",
    "RevertedValue",
    "preview_of",
]
