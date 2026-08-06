"""Marking a playbook stale the moment the episodes under it change.

Without this, the cache is a cache of nothing in particular. A team investigates
the same failure a sixth time, discovers the cause is not what the playbook says,
the episode is written — and the next investigation reads a playbook synthesised
before anybody knew that. Caching learning without invalidating it is worse than
not caching it, because it converts a corpus that is getting better into a
recommendation that is getting older.

Invalidation runs on the episode write, in the same unit of work, and it is keyed
the same way synthesis is: the episode's issue type, and each of its components
put through the same normaliser. That symmetry is the requirement. Two different
normalisations — one on the write side and one on the read side — would produce a
cache nothing ever invalidates and nobody would notice, because the failure mode
is a playbook that is merely out of date.

An episode that names three components invalidates three keys. That is not
over-eager: an investigation into a failure that spanned a service and its
database has something to say about the playbook for either.

**Marked, never deleted.** The next investigation into that failure would
otherwise arrive at an empty shelf and pay a synthesis call before it could read
anything. Stale means "regenerate when someone asks", and until someone does, the
old playbook is still the best available answer and is served with its date range
attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from platform.memory.models import MemoryEpisode
from platform.memory.strategy.normalisation import DEFAULT_NORMALISER, ComponentNormaliser
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import UnitOfWork

logger = get_logger(__name__)


def invalidation_keys(
    episode: MemoryEpisode,
    *,
    normaliser: ComponentNormaliser = DEFAULT_NORMALISER,
) -> tuple[str, ...]:
    """Return the component keys ``episode`` is evidence about.

    Empty when the episode has no issue type. Synthesis keys on the pair, so an
    episode nobody could classify belongs to no playbook — and invalidating every
    playbook for its components would throw away work on the strength of a
    failed extraction.
    """
    if not episode.issue_type.strip():
        return ()
    return normaliser.keys_for(episode.components)


@dataclass(slots=True)
class StrategyInvalidator:
    """Marks the playbooks one episode write contradicts."""

    normaliser: ComponentNormaliser = field(default=DEFAULT_NORMALISER)

    async def on_episode_written(self, uow: UnitOfWork, episode: MemoryEpisode) -> int:
        """Mark every playbook ``episode`` bears on, and return how many changed.

        Takes the unit of work rather than the gateway, so invalidation commits
        with the episode that caused it. Separating them would leave a window in
        which the episode exists and the playbook that contradicts it is still
        being served as current — small, and exactly as long as the next
        investigation needs to read it.
        """
        keys = invalidation_keys(episode, normaliser=self.normaliser)
        if not keys:
            return 0

        invalidated = 0
        for component_key in keys:
            invalidated += await uow.episodes.mark_strategies_stale(
                team_node_id=episode.team_node_id,
                issue_type=episode.issue_type.strip().lower(),
                component_key=component_key,
            )

        if invalidated:
            logger.info(
                "strategy.invalidated",
                episode=episode.correlation_id,
                team=episode.team_node_id,
                issue_type=episode.issue_type,
                keys=list(keys),
                invalidated=invalidated,
            )
        return invalidated


__all__ = [
    "StrategyInvalidator",
    "invalidation_keys",
]
