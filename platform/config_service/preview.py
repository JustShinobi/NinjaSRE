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
from platform.config_service.effective import build
from platform.config_service.field_policy import (
    PolicySet,
    changed_paths,
    gated_paths,
    merged_along,
)
from platform.config_service.merge import locked_paths_in
from platform.persistence.ports import ConfigNode


@dataclass(frozen=True, slots=True)
class PreviewChange:
    """One leaf the patch would move, and what it would move between."""

    path: str
    before: Any = None
    after: Any = None


@dataclass(frozen=True, slots=True)
class ConfigPreview:
    """What saving a patch would produce, and what would stop it.

    ``values`` and ``provenance`` are the effective result — what the node would
    resolve to afterwards, every value attributed to the node that supplied it.
    ``locked`` and ``approval_gated`` are the two reasons the result may not be
    what the patch asked for, reported separately because they need different
    actions: a lock is somebody else's decision to change, and a gate is a
    review to wait for.
    """

    node_id: str
    values: Mapping[str, Any]
    provenance: Mapping[str, str]
    changes: tuple[PreviewChange, ...] = ()
    #: Patch paths an ancestor has locked, mapped to the node holding the lock.
    #: The lock wins: those paths keep their inherited value in ``values``.
    locked: Mapping[str, str] = None  # type: ignore[assignment]
    approval_gated: tuple[str, ...] = ()

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
    node_id: str, chain: Sequence[ConfigNode], patch: Mapping[str, Any]
) -> ConfigPreview:
    """Return what applying ``patch`` at the end of ``chain`` would resolve to.

    ``chain`` is root-first and inclusive, exactly as a write reads it. The last
    entry is the node being changed; everything before it is what it inherits
    from and what may have locked a field against it.
    """
    node = chain[-1]
    document = NodeDocument.of_node(node)
    proposed = dict(settings_after(document.settings, patch))

    proposed_chain = (*chain[:-1], _with_settings(node, document, proposed))
    effective = build(node_id, proposed_chain)

    changed = changed_paths(document.settings, proposed)
    before = dict(paths.leaves(document.settings))
    after = dict(paths.leaves(proposed))

    return ConfigPreview(
        node_id=node_id,
        values=effective.values,
        provenance=dict(effective.provenance),
        changes=tuple(
            PreviewChange(path=path, before=before.get(path), after=after.get(path))
            for path in changed
        ),
        locked=dict(locked_paths_in(patch, _inherited_locks(chain[:-1]))),
        approval_gated=gated_paths(changed, merged_along(_node_policies(chain))),
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


__all__ = ["ConfigPreview", "PreviewChange", "preview_of"]
