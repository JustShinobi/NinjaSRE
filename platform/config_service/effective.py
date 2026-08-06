"""What one node resolves to, where every value came from, and when to recompute.

An investigation resolves configuration once, at the start, and everything it
does afterwards reads that one object (FR-014). Resolving per stage would mean
six chances for a mid-run change to make the first half of an investigation
disagree with the second, and nothing downstream could tell that had happened.

**The cache key is the chain's own versions.** ``ConfigNode.version`` already
moves on every write — it is the optimistic-concurrency control the repository
enforces — so the fingerprint of a resolution is the ``(node, version)`` pairs
of its ancestor chain. A write anywhere in that chain changes the fingerprint of
every descendant, automatically and without a registry to keep in step.

That is a deliberate departure from a hand-maintained hierarchy counter, and the
reason is processes. A counter held in memory is correct only while one process
does all the writing; a fingerprint read from the row is correct when the
console, the scheduler, and three API replicas are all writing. The read it
costs is one indexed query, and what the cache is actually saving is the merge,
the schema construction, and the validation on top of it.

**Nothing is served across tenants.** The resolver holds one scope and every
read goes through a unit of work opened for it, so a cache hit for another
organisation's node is not a bug that was avoided — it is a question that cannot
be phrased.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.config_service import MAX_EFFECTIVE_CONFIG_CACHE_ENTRIES
from platform.config_service import paths
from platform.config_service.document import NodeDocument
from platform.config_service.errors import UnknownNode
from platform.config_service.field_policy import PolicySet, merged_along
from platform.config_service.merge import MergeResult, locking_node, merge_layers
from platform.config_service.schema.root import RootConfig
from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import ConfigNode, PersistenceGateway, TenantScope


@dataclass(frozen=True, slots=True)
class HierarchyVersion:
    """The identity of one resolution's inputs: its chain, and each node's version.

    Two resolutions with the same fingerprint consumed the same rows, so one may
    stand in for the other. A single integer would have said less: it could not
    distinguish "an ancestor of this node changed" from "some node somewhere
    changed", and the second invalidates every team's cache for one team's edit.
    """

    entries: tuple[tuple[str, int], ...] = ()

    @classmethod
    def of(cls, chain: Sequence[ConfigNode]) -> HierarchyVersion:
        """Return the fingerprint of ``chain``, root-first."""
        return cls(entries=tuple((node.node_id, node.version) for node in chain))


@dataclass(frozen=True, slots=True)
class EffectiveConfig:
    """One node's merged configuration, typed, with per-value provenance."""

    node_id: str
    values: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, str] = field(default_factory=dict)
    locks: Mapping[str, str] = field(default_factory=dict)
    policies: PolicySet = field(default_factory=PolicySet)
    config: RootConfig = field(default_factory=RootConfig)
    version: HierarchyVersion = field(default_factory=HierarchyVersion)

    def value_at(self, path: str) -> Any:
        """Return the merged value at ``path``, or ``None`` if it is unset."""
        return paths.value_at(self.values, path)

    def source_of(self, path: str) -> str | None:
        """Return the node that supplied the value at ``path``, or ``None`` (FR-016)."""
        return self.provenance.get(path)

    def locked_by(self, path: str) -> str | None:
        """Return the node locking ``path`` or an ancestor of it, or ``None``."""
        return locking_node(self.locks, path)

    def chain(self) -> tuple[str, ...]:
        """Return the node ids this resolution merged, root-first."""
        return tuple(node_id for node_id, _ in self.version.entries)

    def explain(self) -> tuple[tuple[str, Any, str], ...]:
        """Return ``(path, value, source node)`` for every value, in path order.

        What the console shows beside a team's configuration. "Why is this team
        using that model" is asked constantly on a four-level tree, and
        answering it by walking the tree by hand is how nobody ends up asking.
        """
        return tuple(
            (path, self.value_at(path), self.provenance[path]) for path in sorted(self.provenance)
        )


def resolve_layers(
    chain: Sequence[ConfigNode],
) -> tuple[MergeResult, PolicySet, tuple[NodeDocument, ...]]:
    """Return the merge, the accumulated policies, and the documents, for ``chain``.

    The pure half of resolution, taking rows and returning values. Kept separate
    from the resolver so a merge can be reasoned about, tested, and benchmarked
    without a database.
    """
    documents = tuple(NodeDocument.of_node(node) for node in chain)
    layers = tuple(
        document.as_layer(node.node_id) for document, node in zip(documents, chain, strict=True)
    )
    policies = merged_along(document.policies for document in documents)
    return merge_layers(layers), policies, documents


class EffectiveConfigCache:
    """Least-recently-used resolutions, bounded, keyed on node and fingerprint.

    Bounded because the key is a node and a deployment has as many nodes as it
    has teams. An unbounded cache here would grow with the organisation and
    never shrink, which Article II calls a defect rather than a trade-off.
    """

    __slots__ = ("_entries", "_limit")

    def __init__(self, limit: int = MAX_EFFECTIVE_CONFIG_CACHE_ENTRIES) -> None:
        if limit < 1:
            raise ValueError(f"An effective-config cache holds at least one entry; got {limit}.")
        self._limit = limit
        self._entries: OrderedDict[str, EffectiveConfig] = OrderedDict()

    def get(self, node_id: str, version: HierarchyVersion) -> EffectiveConfig | None:
        """Return the cached resolution for ``node_id``, if it is still current."""
        found = self._entries.get(node_id)
        if found is None or found.version != version:
            return None
        self._entries.move_to_end(node_id)
        return found

    def put(self, resolved: EffectiveConfig) -> EffectiveConfig:
        """Store ``resolved`` and return it, evicting the least recently used."""
        self._entries[resolved.node_id] = resolved
        self._entries.move_to_end(resolved.node_id)
        while len(self._entries) > self._limit:
            self._entries.popitem(last=False)
        return resolved

    def discard(self, node_id: str) -> None:
        """Drop ``node_id``'s entry, if it has one.

        Not how invalidation works — the fingerprint handles that — but a
        deleted node should not keep occupying an entry until eviction reaches
        it.
        """
        self._entries.pop(node_id, None)

    def clear(self) -> None:
        """Drop everything."""
        self._entries.clear()

    def __len__(self) -> int:
        """Return how many resolutions are held."""
        return len(self._entries)


class EffectiveConfigResolver:
    """Resolution for one tenant: read the chain, merge it, cache the answer."""

    __slots__ = ("_cache", "_gateway", "_scope")

    def __init__(
        self,
        *,
        gateway: PersistenceGateway,
        scope: TenantScope,
        cache: EffectiveConfigCache | None = None,
        cache_size: int = MAX_EFFECTIVE_CONFIG_CACHE_ENTRIES,
    ) -> None:
        self._gateway = gateway
        self._scope = scope
        self._cache = cache if cache is not None else EffectiveConfigCache(cache_size)

    @property
    def scope(self) -> TenantScope:
        """Return the tenant this resolver answers for."""
        return self._scope

    @property
    def cached_entries(self) -> int:
        """Return how many resolutions are currently held."""
        return len(self._cache)

    async def resolve(self, node_id: str) -> EffectiveConfig:
        """Return ``node_id``'s effective configuration, cached on its chain.

        Raises ``UnknownNode`` when this tenant has no such node. A resolution
        that quietly returned defaults for a mistyped node id would be a team
        investigating on somebody else's configuration and no way to notice.
        """
        chain = await self._chain(node_id)
        version = HierarchyVersion.of(chain)

        cached = self._cache.get(node_id, version)
        if cached is not None:
            return cached

        return self._cache.put(build(node_id, chain, version))

    async def resolve_for_run(self, node_id: str) -> EffectiveConfig:
        """Return the configuration one investigation runs under (FR-014).

        A named alias rather than a second implementation, so the once-per-run
        contract is stated where a caller looks for it and there is no second
        path that could drift from this one.
        """
        return await self.resolve(node_id)

    def invalidate(self, node_id: str) -> None:
        """Forget ``node_id``'s cached resolution.

        For a deleted node. A *changed* node needs no call: its version moved,
        so the fingerprint no longer matches and the next resolution recomputes.
        """
        self._cache.discard(node_id)

    async def _chain(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return ``node_id``'s ancestors, root-first and inclusive."""
        async with self._gateway.begin(self._scope) as uow:
            try:
                chain = await uow.config.ancestors(node_id)
            except RecordNotFound as absent:
                raise UnknownNode(node_id) from absent
        if not chain:
            raise UnknownNode(node_id)
        return chain


def build(
    node_id: str, chain: Sequence[ConfigNode], version: HierarchyVersion | None = None
) -> EffectiveConfig:
    """Return the effective configuration ``chain`` produces for ``node_id``.

    The schema is built from the merged values and its errors are *not* raised
    here. Everything reaching this point was validated at write, and a
    resolution that refused to produce a configuration would be an incident that
    cannot be investigated because of a document somebody stored last month.
    Whatever could not be read falls back to its shipped default, which is a
    working system.
    """
    merged, policies, _ = resolve_layers(chain)
    config, _ = RootConfig.read(merged.values)
    return EffectiveConfig(
        node_id=node_id,
        values=merged.values,
        provenance=merged.provenance,
        locks=merged.locks,
        policies=policies,
        config=config,
        version=version if version is not None else HierarchyVersion.of(chain),
    )


__all__ = [
    "EffectiveConfig",
    "EffectiveConfigCache",
    "EffectiveConfigResolver",
    "HierarchyVersion",
    "build",
    "resolve_layers",
]
