"""Deep merge, root to leaf, with per-value provenance and lock enforcement.

This is the whole configuration service in one function, and the semantics are
deliberately boring:

- a key absent from the base is taken from the override
- two mappings merge recursively
- everything else — list, scalar, explicit null, type mismatch — replaces

**Lists replace.** Merging them requires identity semantics per list, which
means a control key saying which, which means a configuration language. An
operator can always restate a list; nobody can restate a merge rule they cannot
see.

**No key is a directive** (FR-003). ``_append`` is a field name. The merge
interprets nothing, so what a document says is what it does, and a document
reviewed in a pull request behaves the way the reviewer read it.

**Provenance is recorded during the merge, not reconstructed after it.** SC-005
asks that every effective value name the node that supplied it, and the only
place that is known for free is the moment the value is written. Reconstructing
it later means walking the tree again and getting the type-mismatch cases wrong.

**Locks are enforced here as well as at write time.** The write check is what an
operator meets; this one is what makes SC-002 true regardless of how a value
reached storage — a lock added after the fact, a restored backup, a direct
database write. A skipped override is not an error here: the write path already
refused it, and refusing again at read time would mean an incident's
configuration failing to resolve because of a lock somebody added last week.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.config_service import MAX_CONFIG_DEPTH
from platform.config_service import paths
from platform.config_service.errors import ConfigTooDeep


@dataclass(frozen=True, slots=True)
class Layer:
    """One node's contribution to a merge: its settings and the paths it locks.

    ``locked`` sits beside ``values`` rather than inside it because a lock is
    not configuration — it is a statement about who may change configuration —
    and putting it in the payload would make it a control key.
    """

    node_id: str
    values: Mapping[str, Any] = field(default_factory=dict)
    locked: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MergeResult:
    """The merged configuration, where each value came from, and what is locked.

    ``provenance`` maps a leaf path to the node that supplied its final value.
    ``locks`` maps a locked path to the node that locked it — the answer to
    "why can I not change this", which is the question a lock generates.
    """

    values: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, str] = field(default_factory=dict)
    locks: Mapping[str, str] = field(default_factory=dict)

    def source_of(self, path: str) -> str | None:
        """Return the node that supplied the value at ``path``, or ``None``."""
        return self.provenance.get(path)

    def locked_by(self, path: str) -> str | None:
        """Return the node locking ``path`` or an ancestor of it, or ``None``."""
        return locking_node(self.locks, path)

    def value_at(self, path: str) -> Any:
        """Return the merged value at ``path``, or ``None`` if it is unset."""
        return paths.value_at(self.values, path)


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``base`` with ``override`` applied, leaving both untouched.

    The two-argument form, for callers that want the values and not the
    bookkeeping — a template diff, a defaults overlay. ``merge_layers`` is what
    a hierarchy uses.
    """
    merged: dict[str, Any] = {key: _copy(value, key) for key, value in base.items()}
    _apply(merged, {}, {}, override, "", "")
    return merged


def merge_layers(layers: Sequence[Layer]) -> MergeResult:
    """Return the effective configuration for ``layers``, applied root-first.

    Each layer overrides its predecessors except where one of them locked the
    path. A lock declared at a layer takes effect for every layer *after* it,
    never for the layer that declared it — a node that could not set the field
    it locks could not pin a value at all.
    """
    values: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    locks: dict[str, str] = {}

    for layer in layers:
        _apply(values, provenance, locks, layer.values, layer.node_id, "")
        for path in layer.locked:
            locks.setdefault(path, layer.node_id)

    return MergeResult(values=values, provenance=provenance, locks=locks)


def locking_node(locks: Mapping[str, str], path: str) -> str | None:
    """Return the node locking ``path`` or any ancestor path of it.

    Outermost first: a lock on ``policies`` is reported in preference to one on
    ``policies.masking``, because the outer one is the constraint that would
    still apply if the inner one were lifted.
    """
    for candidate in paths.prefixes(path):
        node_id = locks.get(candidate)
        if node_id is not None:
            return node_id
    return None


def locked_paths_in(
    values: Mapping[str, Any], locks: Mapping[str, str]
) -> tuple[tuple[str, str], ...]:
    """Return the ``(path, locking node)`` pairs ``values`` would try to override.

    The write-time half of lock enforcement. Only leaves are reported: a
    document that sets ``policies.masking.level`` beneath a lock on
    ``policies.masking`` should be told about the field it wrote, not about the
    subtree it happened to touch.
    """
    found: list[tuple[str, str]] = []
    for path, _ in paths.leaves(values):
        node_id = locking_node(locks, path)
        if node_id is not None:
            found.append((path, node_id))
    return tuple(found)


def _apply(
    target: dict[str, Any],
    provenance: dict[str, str],
    locks: Mapping[str, str],
    source: Mapping[str, Any],
    node_id: str,
    prefix: str,
    depth: int = 0,
) -> None:
    """Apply ``source`` onto ``target`` in place, recording where values came from."""
    if depth > MAX_CONFIG_DEPTH:
        raise ConfigTooDeep(prefix, MAX_CONFIG_DEPTH)

    for key, value in source.items():
        path = f"{prefix}.{key}" if prefix else key
        if locking_node(locks, path) is not None:
            continue

        if not isinstance(value, Mapping):
            _forget(provenance, path)
            target[key] = _copy(value, path, depth + 1)
            if node_id:
                provenance[path] = node_id
            continue

        existing = target.get(key)
        if isinstance(existing, dict):
            _apply(existing, provenance, locks, value, node_id, path, depth + 1)
            continue

        # The mapping is replacing a scalar, or arriving where nothing was. It is
        # built aside and committed only if anything survived the locks, because
        # a subtree whose every leaf was locked must leave no empty husk behind —
        # an operator would see a section they never got to set.
        branch: dict[str, Any] = {}
        branch_provenance: dict[str, str] = {}
        _apply(branch, branch_provenance, locks, value, node_id, path, depth + 1)
        if not branch and value:
            continue

        _forget(provenance, path)
        target[key] = branch
        provenance.update(branch_provenance)
        if not branch and node_id:
            provenance[path] = node_id


def _forget(provenance: dict[str, str], path: str) -> None:
    """Drop the provenance of ``path`` and everything beneath it.

    A scalar replacing a subtree takes that subtree's provenance with it.
    Leaving the old entries behind would let ``source_of`` name a node for a
    path that no longer exists — the failure mode where the provenance table is
    confidently wrong rather than merely incomplete.
    """
    if path in provenance:
        del provenance[path]
    stale = [known for known in provenance if paths.covers(path, known)]
    for known in stale:
        del provenance[known]


def _copy(value: Any, path: str, depth: int = 0) -> Any:
    """Return a deep copy of ``value``, so no merge aliases its inputs.

    Aliasing here would let one node's stored settings be mutated by a merge
    that happened to reach it, and the symptom would be a cached document that
    disagrees with the database.
    """
    if depth > MAX_CONFIG_DEPTH:
        raise ConfigTooDeep(path, MAX_CONFIG_DEPTH)
    if isinstance(value, Mapping):
        return {key: _copy(item, path, depth + 1) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_copy(item, path, depth + 1) for item in value]
    return value


def layers_from(
    documents: Iterable[tuple[str, Mapping[str, Any], tuple[str, ...]]],
) -> tuple[Layer, ...]:
    """Return layers for ``(node id, settings, locked paths)`` triples, in order."""
    return tuple(Layer(node_id, values, locked) for node_id, values, locked in documents)


__all__ = [
    "Layer",
    "MergeResult",
    "deep_merge",
    "layers_from",
    "locked_paths_in",
    "locking_node",
    "merge_layers",
]
