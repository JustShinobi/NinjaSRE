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

Synthesised strategies live here too, rather than behind a thirteenth port. A
strategy is a cached derivation of a set of episodes and nothing else reads or
writes one; the write that invalidates it is an episode write, and the two have
to be able to happen in a single unit of work. As with the episode, the *shape*
of a playbook is not this port's business — ``content`` is an opaque payload, and
the sections, the source episode ids, and the prompt version are the vocabulary
of the feature that synthesises them.
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


@dataclass(frozen=True, slots=True)
class StoredStrategy:
    """One cached playbook, keyed on the team, the issue type, and the component.

    ``stale`` rather than a delete. An episode write that contradicts a playbook
    is a reason to regenerate it, not a reason to have nothing: the next
    investigation into that failure would otherwise arrive at an empty shelf and
    pay a synthesis call before it could read anything. Marking lets the reader
    decide — serve the stale one, regenerate, or both — and it keeps the row for
    the operator asking what the playbook said before it changed.

    ``generated_at`` is what an age check reads, so it is a column rather than a
    field of ``content``. A backend that had to parse the payload to answer "is
    this older than thirty days" could not index the question.
    """

    team_node_id: str
    issue_type: str
    component_key: str
    content: Mapping[str, Any] = field(default_factory=dict)
    generated_at: datetime | None = None
    stale: bool = False


@runtime_checkable
class EpisodeStore(Protocol):
    """Episodic memory and the playbooks synthesised from it, within one tenant."""

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

    # -- synthesised strategies ------------------------------------------------

    async def save_strategy(self, strategy: StoredStrategy) -> StoredStrategy:
        """Store ``strategy``, replacing any earlier version, and return it.

        An upsert on ``(team_node_id, issue_type, component_key)``. That is what
        makes concurrent synthesis converge on one row rather than on the last
        writer: two processes that both generated for the same key have both
        produced a playbook over the same episodes, and either is a correct
        answer to the request that started them.
        """

    async def get_strategy(
        self,
        *,
        team_node_id: str,
        issue_type: str,
        component_key: str,
    ) -> StoredStrategy | None:
        """Return the strategy for this key, stale or not, or ``None``.

        Staleness is returned rather than hidden, because the caller is the only
        party that knows whether it can afford to regenerate.
        """

    async def list_strategies(
        self,
        *,
        team_node_id: str,
        limit: int = 50,
    ) -> tuple[StoredStrategy, ...]:
        """Return the team's strategies, most recently generated first.

        ``limit`` is capped by ``MAX_QUERY_PAGE_SIZE``; above it,
        ``BoundExceeded``.
        """

    async def mark_strategies_stale(
        self,
        *,
        team_node_id: str,
        issue_type: str,
        component_key: str,
    ) -> int:
        """Mark the matching strategies stale and return how many changed.

        Returns the number *changed*, not the number matched: an episode write
        that finds an already-stale playbook has invalidated nothing, and a
        caller logging "invalidated 1 strategy" on every write would make the
        signal meaningless.
        """

    async def delete_strategy(
        self,
        *,
        team_node_id: str,
        issue_type: str,
        component_key: str,
    ) -> bool:
        """Delete the strategy for this key and return whether it existed."""


__all__ = [
    "Episode",
    "EpisodeOutcome",
    "EpisodeStore",
    "StoredStrategy",
]
