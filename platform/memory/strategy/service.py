"""Where a playbook meets a recall, and where an operator reaches one.

Two consumers, one object, because they read the same rows under the same scope
and splitting them would be two places to get the tenant wrong.

**The agent's path** is ``StrategyRecall``. It wraps the retriever, so the
capability keeps calling one thing and the playbooks arrive attached to the
episodes rather than through a second tool. That matters more than it looks: a
separate `get_playbook` capability would be one the agent has to decide to call,
and the decision would be made before it knows whether a playbook exists.

The candidate keys come from what recall returned — the issue type and the
normalised component of the best-ranked episodes — and are capped, because a
recall touching six components must not become six synthesis calls on an
incident's critical path.

**The episode set is widened before generating, and only then.** Recall returns
five episodes because five is what an agent can read; a playbook wants every
episode on the key, up to its own bound. So on a cache hit nothing extra happens
at all, and on a miss one further search runs — unrecorded, because the agent did
not ask for it — before the model call that was going to happen anyway.

**The operator's path** is ``StrategyDirectory``: list, read, amend, regenerate.
It never generates as a side effect of reading, because an operator browsing
playbooks in a console must not be able to spend model calls by scrolling.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from config.constants.memory import MAX_STRATEGY_KEYS_PER_RECALL, STRATEGY_MAX_INPUT_EPISODES
from platform.memory.models import MemoryEpisode, RecallQuery, ScoredEpisode
from platform.memory.models import now as _utc_now
from platform.memory.retrieval import MemoryRetriever, RecallLedger, RecallResult
from platform.memory.strategy.cache import StrategyCache, StrategyLookup
from platform.memory.strategy.models import OperatorEdit, Strategy, StrategyKey
from platform.memory.strategy.normalisation import DEFAULT_NORMALISER, ComponentNormaliser
from platform.memory.strategy.policy import StrategyPolicy
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)


def candidate_keys(
    result: RecallResult,
    *,
    org_id: str,
    team_node_id: str,
    normaliser: ComponentNormaliser = DEFAULT_NORMALISER,
    limit: int = MAX_STRATEGY_KEYS_PER_RECALL,
) -> tuple[StrategyKey, ...]:
    """Return the playbook keys ``result`` suggests, best-ranked first.

    Derived from what came back rather than from what was asked, because the
    query may name no component at all — the agent is told to search on evidence,
    and "connection pool exhausted, exit code 137" names none. The episodes that
    matched do name components, and those are the subjects a playbook would be
    about.

    Deliberately *not* thresholded here. Whether three episodes exist on a key is
    a question about the corpus, not about this recall's five results, and the
    generator answers it against the widened set. Deciding it here would refuse
    to synthesise a playbook from a corpus of eight episodes because only two of
    them happened to rank into one search.
    """
    seen: dict[tuple[str, str], None] = {}
    for found in result.episodes:
        issue_type = found.episode.issue_type.strip().lower()
        if not issue_type:
            continue
        for component_key in normaliser.keys_for(found.episode.components):
            seen.setdefault((issue_type, component_key), None)

    return tuple(
        StrategyKey(
            org_id=org_id,
            team_node_id=team_node_id,
            issue_type=issue_type,
            component_key=component_key,
        )
        for issue_type, component_key in tuple(seen)[:limit]
    )


def episodes_on_key(
    episodes: Sequence[ScoredEpisode],
    key: StrategyKey,
    *,
    normaliser: ComponentNormaliser = DEFAULT_NORMALISER,
) -> tuple[ScoredEpisode, ...]:
    """Return the episodes that belong to ``key``, in rank order.

    Both halves of the key are required. An episode of a different failure on the
    same service says nothing about this playbook, and an episode of this failure
    on a different service says something about a different one.
    """
    return tuple(
        found
        for found in episodes
        if found.episode.issue_type.strip().lower() == key.issue_type
        and key.component_key in normaliser.keys_for(found.episode.components)
    )


@dataclass(slots=True)
class StrategyRecall:
    """Recall, with the playbooks its results imply attached.

    Structurally a ``RecallSource``: it has ``search`` and returns a
    ``RecallResult``, so the capability binds this instead of the retriever and
    nothing else changes.
    """

    retriever: MemoryRetriever
    cache: StrategyCache
    normaliser: ComponentNormaliser = field(default=DEFAULT_NORMALISER)
    policy: StrategyPolicy = field(default_factory=StrategyPolicy)
    ledger: RecallLedger | None = None
    clock: Callable[[], datetime] = _utc_now

    async def search(self, query: RecallQuery, *, record: bool = True) -> RecallResult:
        """Return the episodes resembling ``query``, and any playbook they imply.

        Never raises anything the retriever would not have raised on its own.
        Synthesis is an enrichment of a recall that has already succeeded, and
        The suite asserts that it stays one: whatever goes wrong from here down,
        the episodes still come back.
        """
        result = await self.retriever.search(query, record=record)
        if not self.policy.enabled or not result.searched or result.empty:
            return result

        try:
            strategies = await self._for(result)
        except Exception as error:  # noqa: BLE001 — synthesis must never fail a recall
            logger.warning("strategy.recall_enrichment_failed", error=str(error))
            return result

        if strategies and record and self.ledger is not None and self.ledger.records:
            self.ledger.attach_strategies(
                self.ledger.records[-1], [strategy.key.label for strategy in strategies]
            )
        return replace(result, strategies=strategies)

    async def _for(self, result: RecallResult) -> tuple[Strategy, ...]:
        """Return the playbooks this recall's episodes point at."""
        found: list[Strategy] = []
        for key in candidate_keys(
            result,
            org_id=self.cache.scope.org_id,
            team_node_id=self.cache.scope.team_node_id or "",
            normaliser=self.normaliser,
        ):
            lookup = await self._lookup(key, result)
            if lookup.strategy is not None:
                found.append(lookup.strategy)
        return tuple(found)

    async def _lookup(self, key: StrategyKey, result: RecallResult) -> StrategyLookup:
        """Return the playbook for ``key``, widening the episode set only if it must."""
        cached = await self.cache.get(key)
        if cached.strategy is not None and cached.strategy.fresh(self.clock()):
            return cached
        return await self.cache.get_or_generate(key, await self._widened(key, result))

    async def _widened(self, key: StrategyKey, result: RecallResult) -> tuple[ScoredEpisode, ...]:
        """Return every episode on ``key`` the corpus will give up, bounded.

        Filtered on the issue type inside the index and on the normalised
        component key here — the index filters by equality and a component key is
        a derived value, so it cannot be pushed down. The recall's own episodes
        are the fallback when the widening search finds nothing, which happens
        when the corpus is unavailable rather than empty.
        """
        widened = await self.retriever.search(
            RecallQuery(
                text=result.query.text,
                issue_type=key.issue_type,
                limit=STRATEGY_MAX_INPUT_EPISODES,
            ),
            record=False,
        )
        on_key = episodes_on_key(widened.episodes, key, normaliser=self.normaliser)
        return on_key or episodes_on_key(result.episodes, key, normaliser=self.normaliser)


@dataclass(slots=True)
class StrategyDirectory:
    """Read and write access to a team's playbooks, for the console.

    Reading never generates. An operator opening a list of playbooks must not be
    able to spend a model call per row by scrolling, and a console that could
    would make its own latency unpredictable for reasons nobody looking at it
    could see.
    """

    gateway: PersistenceGateway
    scope: TenantScope
    cache: StrategyCache
    clock: Callable[[], datetime] = _utc_now

    async def list(self, *, limit: int = 50) -> tuple[Strategy, ...]:
        """Return this team's playbooks, most recently generated first."""
        async with self.gateway.begin(self.scope) as uow:
            stored = await uow.episodes.list_strategies(
                team_node_id=self.scope.team_node_id or "", limit=limit
            )
        return tuple(Strategy.from_stored(row, org_id=self.scope.org_id) for row in stored)

    async def get(self, key: StrategyKey) -> Strategy | None:
        """Return one playbook, stale or not, without generating anything."""
        return (await self.cache.get(key)).strategy

    async def amend(self, key: StrategyKey, edit: OperatorEdit) -> Strategy | None:
        """Attach an operator's amendment to a playbook and return it.

        Returns ``None`` when there is no playbook to amend rather than creating
        one. An edit is a correction of something, and a note attached to a
        playbook that does not exist would be a playbook with one human sentence
        and three empty generated sections.
        """
        existing = await self.get(key)
        if existing is None:
            return None

        amended = existing.with_edit(
            edit if edit.edited_at is not None else replace(edit, edited_at=self.clock())
        )
        async with self.gateway.begin(self.scope) as uow:
            await uow.episodes.save_strategy(amended.to_stored())
        logger.info("strategy.amended", key=key.label, author=edit.author)
        return amended

    async def invalidate(self, key: StrategyKey) -> bool:
        """Mark a playbook stale so the next request regenerates it.

        The operator's version of what an episode write does automatically: the
        answer to "this playbook is wrong" that does not require waiting for the
        next investigation of that failure to prove it.
        """
        async with self.gateway.begin(self.scope) as uow:
            changed = await uow.episodes.mark_strategies_stale(
                team_node_id=key.team_node_id,
                issue_type=key.issue_type,
                component_key=key.component_key,
            )
        return changed > 0

    async def delete(self, key: StrategyKey) -> bool:
        """Delete a playbook and return whether it existed.

        Operator edits go with it. That is the point of offering delete beside
        invalidate: invalidate keeps the amendments and regenerates around them,
        delete is for a playbook whose subject no longer exists.
        """
        async with self.gateway.begin(self.scope) as uow:
            return await uow.episodes.delete_strategy(
                team_node_id=key.team_node_id,
                issue_type=key.issue_type,
                component_key=key.component_key,
            )


def keys_for_episode(
    episode: MemoryEpisode,
    *,
    org_id: str,
    normaliser: ComponentNormaliser = DEFAULT_NORMALISER,
) -> tuple[StrategyKey, ...]:
    """Return the playbook keys one episode is evidence about.

    The read-side twin of ``invalidation.invalidation_keys``, and it exists so a
    caller holding an episode — a backfill, a console preview, a test — can name
    the same keys the write path names without reimplementing the pairing.
    """
    if not episode.issue_type.strip() or not episode.team_node_id:
        return ()
    return tuple(
        StrategyKey(
            org_id=org_id,
            team_node_id=episode.team_node_id,
            issue_type=episode.issue_type,
            component_key=component_key,
        )
        for component_key in normaliser.keys_for(episode.components)
    )


__all__ = [
    "StrategyDirectory",
    "StrategyRecall",
    "candidate_keys",
    "episodes_on_key",
    "keys_for_episode",
]
