"""In-memory episodic memory."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from platform.persistence.fakes.state import TenantState, check_limit, check_payload
from platform.persistence.ports.episode_store import Episode, EpisodeOutcome

#: Sorts before any real timestamp, so an episode with no recorded time falls
#: to the end of a "most recent first" listing rather than the front of it.
_UNDATED = datetime.min.replace(tzinfo=UTC)


@dataclass(slots=True)
class FakeEpisodeStore:
    """Episodes for one organisation."""

    org_id: str
    state: TenantState

    async def save(self, episode: Episode) -> Episode:
        """Store ``episode``, replacing any earlier version, and return it."""
        check_payload(episode.metadata, kind="episode metadata")
        self.state.episodes[episode.episode_id] = episode
        return episode

    async def get(self, episode_id: str) -> Episode | None:
        """Return the episode with ``episode_id``, or ``None``."""
        return self.state.episodes.get(episode_id)

    async def get_by_run(self, run_id: str) -> Episode | None:
        """Return the episode written for ``run_id``, or ``None``."""
        return next((e for e in self.state.episodes.values() if e.run_id == run_id), None)

    async def by_signature(self, signature: str, *, limit: int = 20) -> tuple[Episode, ...]:
        """Return episodes sharing a fingerprint, most recent first."""
        check_limit(limit)
        return self._recent_first(
            (e for e in self.state.episodes.values() if e.signature == signature),
            limit,
        )

    async def by_component(self, component: str, *, limit: int = 20) -> tuple[Episode, ...]:
        """Return episodes involving ``component``, most recent first."""
        check_limit(limit)
        return self._recent_first(
            (e for e in self.state.episodes.values() if component in e.components),
            limit,
        )

    async def list_recent(
        self,
        *,
        outcome: EpisodeOutcome | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> tuple[Episode, ...]:
        """Return matching episodes, most recent first."""
        check_limit(limit)
        return self._recent_first(
            (
                e
                for e in self.state.episodes.values()
                if (outcome is None or e.outcome is outcome)
                and _within(e.occurred_at, since, until)
            ),
            limit,
        )

    async def count(self) -> int:
        """Return how many episodes this tenant holds."""
        return len(self.state.episodes)

    async def delete(self, episode_id: str) -> bool:
        """Delete ``episode_id`` and return whether it existed."""
        return self.state.episodes.pop(episode_id, None) is not None

    @staticmethod
    def _recent_first(episodes: Iterable[Episode], limit: int) -> tuple[Episode, ...]:
        found = sorted(
            episodes,
            key=lambda e: (e.occurred_at or _UNDATED, e.episode_id),
            reverse=True,
        )
        return tuple(found[:limit])


def _within(
    moment: datetime | None,
    since: datetime | None,
    until: datetime | None,
) -> bool:
    """Return whether ``moment`` falls in a half-open window."""
    if moment is None:
        return since is None and until is None
    if since is not None and moment < since:
        return False
    return not (until is not None and moment >= until)


__all__ = ["FakeEpisodeStore"]
