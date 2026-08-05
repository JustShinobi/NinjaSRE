"""What an investigation learned, kept as the corpus that learning is measured against.

An episode is the durable summary of one investigation: what was wrong, what
turned out to be causing it, which components were involved, and how it ended.
Feature 010 writes them; features 011 and 028 read them, one to synthesise
strategies and the other to prove the strategies helped.

The embedding is not here. Episodes are relational records and their vectors
live in the ``episodes`` namespace of ``VectorIndex``, keyed by ``episode_id``.
Splitting them looks like an extra join and buys two things worth more than it:
a re-embedding generation can rebuild every vector without rewriting a single
episode row, and the retention windows for the two can differ without either
store knowing about the other's.

``signature`` is the deduplication key — a stable fingerprint of the alert
condition, computed by the caller. Storing it as a column rather than deriving
it here keeps the fingerprinting rule in the feature that owns it, and keeps
this port from becoming the place where "what counts as the same incident" is
quietly decided.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class EpisodeOutcome(StrEnum):
    """How the investigation this episode records ended.

    ``INCONCLUSIVE`` is kept rather than discarded. An investigation that failed
    to reach a root cause is exactly the case a learning mechanism has to
    improve on, and a corpus of successes only measures how well the system does
    on the incidents it already handled.
    """

    RESOLVED = "resolved"
    MITIGATED = "mitigated"
    INCONCLUSIVE = "inconclusive"
    FALSE_POSITIVE = "false_positive"


@dataclass(frozen=True, slots=True)
class Episode:
    """One investigation, reduced to what a later one would want to know."""

    episode_id: str
    title: str
    summary: str
    signature: str
    outcome: EpisodeOutcome = EpisodeOutcome.INCONCLUSIVE
    run_id: str | None = None
    occurred_at: datetime | None = None
    components: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    resolution: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class EpisodeStore(Protocol):
    """Episodic memory, within one tenant."""

    async def save(self, episode: Episode) -> Episode:
        """Store ``episode``, replacing any earlier version, and return it."""

    async def get(self, episode_id: str) -> Episode | None:
        """Return the episode with ``episode_id``, or ``None``."""

    async def get_by_run(self, run_id: str) -> Episode | None:
        """Return the episode written for ``run_id``, or ``None``."""

    async def by_signature(self, signature: str, *, limit: int = 20) -> tuple[Episode, ...]:
        """Return episodes sharing a fingerprint, most recent first.

        This is the exact-match half of recall. The approximate half is a
        similarity search over the ``episodes`` vector namespace, and a caller
        that wants both runs both — an alert that has fired before should be
        recognised as such without depending on an embedding.
        """

    async def by_component(self, component: str, *, limit: int = 20) -> tuple[Episode, ...]:
        """Return episodes involving ``component``, most recent first."""

    async def list_recent(
        self,
        *,
        outcome: EpisodeOutcome | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
    ) -> tuple[Episode, ...]:
        """Return matching episodes, most recent first.

        ``limit`` is capped by ``MAX_QUERY_PAGE_SIZE``; above it,
        ``BoundExceeded``.
        """

    async def count(self) -> int:
        """Return how many episodes this tenant holds."""

    async def delete(self, episode_id: str) -> bool:
        """Delete ``episode_id`` and return whether it existed.

        Deleting the episode does not delete its vector. The retention sweep
        does both, in one unit of work, because doing them separately is how an
        index accumulates neighbours that resolve to nothing.
        """


__all__ = [
    "Episode",
    "EpisodeOutcome",
    "EpisodeStore",
]
