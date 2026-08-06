"""Get-or-generate: the reason synthesis is affordable on an incident's critical path.

Synthesis is a structured call over a dozen episodes. Doing it per recall would
put a second model round-trip in front of every memory search, on the one code
path where latency is measured in an engineer's patience. The inputs move slowly
— a key's episode set changes when an investigation of that failure finishes, and
that is weekly at most — so the answer is cached and the cost is paid once per
change rather than once per read.

Three things make the cache correct rather than merely fast.

**Invalidation is a write-side fact, not a read-side guess.** ``invalidation.py``
marks a key stale when an episode lands on it. This module never tries to infer
whether the inputs moved by comparing them, because the comparison would need to
load the episodes — which is most of the work the cache exists to avoid.

**Age forces regeneration on its own.** Infrastructure is retired without
producing an episode, so a playbook nobody contradicted is not a playbook anybody
confirmed. ``STRATEGY_MAX_AGE_DAYS`` is the ceiling.

**Concurrent requests for one key produce one generation.** An alert storm is N
simultaneous investigations of the same component, and without a lock that is N
synthesis calls producing N slightly different playbooks, of which one survives at
random. The lock is per key and the losers wait and read the winner's row rather
than generating their own.

That lock is in-process, and it is worth being precise about what that buys. In
one process it is the whole guarantee. Across processes the guarantee is weaker
and comes from the storage key instead: the row is keyed on
``(org, team, issue_type, component_key)`` and the write is an upsert, so two
workers that both generated converge on one row rather than two — they spend a
duplicate call, they do not produce a duplicate playbook, and the re-read under
the lock means the second one usually finds the first one's work and spends
nothing. A cross-process lease would need a lock the persistence layer does not
expose today; the cost of not having one is bounded and is a wasted model call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from config.constants.memory import STRATEGY_LOCK_WAIT_SECONDS
from config.prompts.strategy import STRATEGY_DISABLED
from platform.memory.models import ScoredEpisode
from platform.memory.models import now as _utc_now
from platform.memory.strategy.generator import StrategyGenerator, SynthesisOutcome
from platform.memory.strategy.models import Strategy, StrategyKey
from platform.memory.strategy.policy import StrategyPolicy
from platform.observability.logging import get_logger
from platform.persistence.errors import PersistenceError
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StrategyLookup:
    """What one get-or-generate produced, and how it got there.

    ``generated`` and ``cached`` are separate flags rather than one enum because
    the trace and the ablation ask different questions of them: the first wants
    to know whether a model call happened, the second wants to know whether the
    agent saw a playbook at all.
    """

    key: StrategyKey
    strategy: Strategy | None = None
    generated: bool = False
    cached: bool = False
    reason: str = ""

    @property
    def found(self) -> bool:
        """Return whether a playbook came back."""
        return self.strategy is not None


@dataclass(slots=True)
class KeyedLock:
    """One lock per strategy key, created on demand and never unbounded.

    Entries are dropped when the last waiter leaves, so a deployment that has
    synthesised ten thousand keys over a month holds locks for the ones being
    generated right now and nothing else.
    """

    _locks: dict[str, asyncio.Lock] = field(default_factory=dict, repr=False)
    _waiters: dict[str, int] = field(default_factory=dict, repr=False)

    def acquire(self, name: str) -> asyncio.Lock:
        """Return the lock for ``name``, registering this caller as a waiter."""
        self._waiters[name] = self._waiters.get(name, 0) + 1
        return self._locks.setdefault(name, asyncio.Lock())

    def release(self, name: str) -> None:
        """Note that one caller has finished with ``name``'s lock."""
        remaining = self._waiters.get(name, 1) - 1
        if remaining > 0:
            self._waiters[name] = remaining
            return
        self._waiters.pop(name, None)
        self._locks.pop(name, None)

    def contended(self, name: str) -> bool:
        """Return whether anyone else is currently holding or awaiting ``name``."""
        lock = self._locks.get(name)
        return lock is not None and lock.locked()


@dataclass(slots=True)
class StrategyCache:
    """The read path for playbooks: cached, invalidated, age-checked, and serialised."""

    gateway: PersistenceGateway
    scope: TenantScope
    generator: StrategyGenerator
    policy: StrategyPolicy = field(default_factory=StrategyPolicy)
    clock: Callable[[], datetime] = _utc_now
    locks: KeyedLock = field(default_factory=KeyedLock)
    lock_wait_seconds: float = STRATEGY_LOCK_WAIT_SECONDS

    def __post_init__(self) -> None:
        if not self.scope.team_node_id:
            raise ValueError(
                f"{self.scope.org_id}: a strategy must be read under a team — an "
                "unscoped playbook is one every team can read"
            )

    def key_for(self, *, issue_type: str, component_key: str) -> StrategyKey:
        """Return a key in this cache's own scope.

        The only sanctioned way to build one for this cache. A ``StrategyKey``
        carries its organisation and team, and a caller that assembled one from
        somewhere else would be one typo away from reading another team's
        playbook — so ``_scoped`` refuses a foreign key and this is how a caller
        avoids constructing one.
        """
        return StrategyKey(
            org_id=self.scope.org_id,
            team_node_id=self.scope.team_node_id or "",
            issue_type=issue_type,
            component_key=component_key,
        )

    def _scoped(self, key: StrategyKey) -> StrategyKey:
        """Return ``key``, or raise when it belongs to another tenant.

        Raises rather than narrows. A key naming a team this cache is not scoped
        to is a caller bug, and silently rewriting it to the current team would
        answer a question nobody asked with data they were not entitled to.
        """
        if key.org_id != self.scope.org_id or key.team_node_id != self.scope.team_node_id:
            raise ValueError(
                f"{key.label} belongs to {key.org_id}/{key.team_node_id}, but this cache "
                f"is scoped to {self.scope.org_id}/{self.scope.team_node_id}"
            )
        return key

    # -- reading ---------------------------------------------------------------

    async def get(self, key: StrategyKey) -> StrategyLookup:
        """Return the cached playbook for ``key`` without ever generating one.

        The retrieval half of the ablation switch, and the path the console
        reads: an operator listing playbooks must not cause a model call.
        """
        self._scoped(key)
        if not self.policy.enabled:
            return StrategyLookup(key=key, reason=STRATEGY_DISABLED)

        strategy = await self._load(key)
        if strategy is None:
            return StrategyLookup(key=key)
        return StrategyLookup(key=key, strategy=strategy, cached=True)

    async def get_or_generate(
        self,
        key: StrategyKey,
        episodes: Sequence[ScoredEpisode],
    ) -> StrategyLookup:
        """Return the playbook for ``key``, generating it only when it must.

        Never raises. A store that is down or a synthesis that failed leaves the
        caller with no playbook and a reason, which is exactly what a recall that
        already has its episodes should do with either.
        """
        self._scoped(key)
        if not self.policy.enabled:
            return StrategyLookup(key=key, reason=STRATEGY_DISABLED)

        try:
            existing = await self._load(key)
        except PersistenceError as error:
            logger.warning("strategy.unavailable", error=str(error))
            return StrategyLookup(key=key, reason=str(error))

        now = self.clock()
        if existing is not None and existing.fresh(now):
            return StrategyLookup(key=key, strategy=existing, cached=True)

        return await self._locked_generate(key, episodes, existing=existing)

    # -- generating ------------------------------------------------------------

    async def _locked_generate(
        self,
        key: StrategyKey,
        episodes: Sequence[ScoredEpisode],
        *,
        existing: Strategy | None,
    ) -> StrategyLookup:
        """Generate for ``key`` under its lock, or read what the winner wrote.

        The re-read after acquiring is the whole mechanism. A caller that waited
        finds the row the winner just wrote and returns it; a caller that did not
        wait finds what it already read and proceeds. Checking freshness before
        the lock as well is not redundant — it keeps the uncontended case off the
        lock entirely, which is the case that happens on every recall.
        """
        name = key.label
        contended = self.locks.contended(name)
        lock = self.locks.acquire(name)
        try:
            async with asyncio.timeout(self.lock_wait_seconds):
                await lock.acquire()
        except TimeoutError:
            self.locks.release(name)
            logger.warning("strategy.lock_timeout", key=name, seconds=self.lock_wait_seconds)
            return self._degraded(
                key, existing, reason=f"waited {self.lock_wait_seconds}s for {name}"
            )

        try:
            if contended:
                winner = await self._load(key)
                if winner is not None and winner.fresh(self.clock()):
                    logger.info("strategy.served_winner", key=name)
                    return StrategyLookup(key=key, strategy=winner, cached=True)

            outcome = await self.generator.generate(key, episodes)
            return await self._persisted(key, outcome, existing=existing)
        finally:
            lock.release()
            self.locks.release(name)

    async def _persisted(
        self,
        key: StrategyKey,
        outcome: SynthesisOutcome,
        *,
        existing: Strategy | None,
    ) -> StrategyLookup:
        """Store what synthesis produced, preserving the operator's amendments."""
        strategy = outcome.strategy
        if strategy is None:
            return self._degraded(key, existing, reason=outcome.reason)

        carried = strategy.carrying_edits_from(existing)
        try:
            async with self.gateway.begin(self.scope) as uow:
                await uow.episodes.save_strategy(carried.to_stored())
        except PersistenceError as error:
            # The playbook is good; only writing it failed. Serving it once is
            # better than discarding the call that produced it, and the next
            # request regenerates because nothing was cached.
            logger.warning("strategy.write_failed", key=key.label, error=str(error))
            return StrategyLookup(key=key, strategy=carried, generated=True, reason=str(error))

        return StrategyLookup(key=key, strategy=carried, generated=True)

    def _degraded(
        self,
        key: StrategyKey,
        existing: Strategy | None,
        *,
        reason: str,
    ) -> StrategyLookup:
        """Return the stale playbook when there is one, and the reason either way.

        A stale playbook is a worse answer than a fresh one and a much better
        answer than none: it was true of the episodes it was drawn from, and the
        agent is told its date range and its episode count and can discount it.
        Discarding it because regeneration failed would punish the reader for a
        provider outage.
        """
        if existing is not None:
            logger.info("strategy.served_stale", key=key.label, reason=reason)
            return StrategyLookup(key=key, strategy=existing, cached=True, reason=reason)
        return StrategyLookup(key=key, reason=reason)

    # -- storage ---------------------------------------------------------------

    async def _load(self, key: StrategyKey) -> Strategy | None:
        """Return the stored playbook for ``key``, stale or not, or ``None``.

        Scoped twice, as recall is. The organisation boundary is structural — the
        unit of work is opened for one — and the team is a column of the key, so
        a playbook belonging to another team cannot be named by this call.
        """
        async with self.gateway.begin(self.scope) as uow:
            stored = await uow.episodes.get_strategy(
                team_node_id=key.team_node_id,
                issue_type=key.issue_type,
                component_key=key.component_key,
            )
        if stored is None:
            return None
        return Strategy.from_stored(stored, org_id=self.scope.org_id)


__all__ = [
    "KeyedLock",
    "StrategyCache",
    "StrategyLookup",
]
