"""Deleting episodes, and deleting their vectors in the same breath.

Two stores hold one fact, and the only safe way to remove it is together. An
episode deleted without its vector leaves a neighbour the index will keep
returning and the retriever will keep failing to load — which reads as a corpus
that is quietly shrinking rather than as a deletion that half happened. A vector
deleted without its episode leaves a row nothing can find, which is worse,
because it is invisible.

So both go in one unit of work. That is also what makes a deletion request
answerable: an operator who deletes a team's episodes has deleted them, in every
generation, and does not have to be told which index to sweep afterwards.

The retention *window* is not decided here. ``RETENTION_DAYS_EPISODES`` is the
platform's default and the retention sweeper is the thing that runs on a
schedule; this module is what either of them calls, so there is one expression of
"remove an episode" rather than one per caller.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from config.constants.persistence import (
    EPISODE_VECTOR_NAMESPACE,
    MAX_QUERY_PAGE_SIZE,
    RETENTION_DAYS_EPISODES,
)
from platform.memory.models import now as _utc_now
from platform.observability.logging import get_logger
from platform.persistence.errors import VectorNamespaceUnknown
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PurgeReport:
    """What one purge removed."""

    episodes: int = 0
    vectors: int = 0
    cutoff: datetime | None = None


def retention_cutoff(
    *,
    now: datetime | None = None,
    days: int = RETENTION_DAYS_EPISODES,
) -> datetime:
    """Return the instant before which episodes may be deleted.

    Episodes outlive traces by a wide margin on purpose: the trace is the
    evidence for one investigation, and the episode corpus is what every
    ablation measures learning against. Deleting the corpus deletes the ability
    to prove the system improved.
    """
    if days < 1:
        raise ValueError(f"an episode retention window must be at least a day, got {days}")
    return (now or _utc_now()) - timedelta(days=days)


async def purge_episodes(
    gateway: PersistenceGateway,
    scope: TenantScope,
    correlation_ids: Sequence[str],
) -> PurgeReport:
    """Delete the named episodes and their vectors, atomically."""
    if not correlation_ids:
        return PurgeReport()

    async with gateway.begin(scope) as uow:
        removed = sum(
            [1 for correlation_id in correlation_ids if await uow.episodes.delete(correlation_id)]
        )
        try:
            vectors = await uow.vectors.delete(EPISODE_VECTOR_NAMESPACE, list(correlation_ids))
        except VectorNamespaceUnknown:
            # No index was ever declared for this tenant, so there is nothing to
            # sweep. The episodes are still gone, which is what was asked.
            vectors = 0

    logger.info("memory.purged", episodes=removed, vectors=vectors, org=scope.org_id)
    return PurgeReport(episodes=removed, vectors=vectors)


async def purge_expired(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    now: datetime | None = None,
    days: int = RETENTION_DAYS_EPISODES,
    batch: int = MAX_QUERY_PAGE_SIZE,
) -> PurgeReport:
    """Delete every episode older than the retention window, one page at a time.

    Paged, because a tenant with a large corpus and a long-untouched retention
    setting would otherwise ask for the whole thing in one statement. Each page
    is its own unit of work, so a sweep that is interrupted has removed a whole
    number of pages rather than an unknown fraction of one.
    """
    cutoff = retention_cutoff(now=now, days=days)
    total = PurgeReport(cutoff=cutoff)

    while True:
        async with gateway.begin(scope) as uow:
            expiring = await uow.episodes.list_recent(until=cutoff, limit=batch)
        if not expiring:
            return total

        report = await purge_episodes(gateway, scope, [episode.episode_id for episode in expiring])
        total = PurgeReport(
            episodes=total.episodes + report.episodes,
            vectors=total.vectors + report.vectors,
            cutoff=cutoff,
        )
        if len(expiring) < batch:
            return total


__all__ = [
    "PurgeReport",
    "purge_episodes",
    "purge_expired",
    "retention_cutoff",
]
