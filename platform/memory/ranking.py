"""Which precedent the agent reads first, as five weighted terms and no model call.

    score = w_similarity   * similarity
          + w_resolved     * resolved
          + w_components   * component_overlap
          + w_effectiveness* effectiveness
          + w_recency      * recency

No LLM anywhere in this path, and that is a requirement rather than an
optimisation. Ranking runs inside a tool call the agent is waiting on, and it
has to produce the same order twice for a trajectory comparison to mean
anything — a ranker that consulted a model would be neither fast nor repeatable.

Similarity carries the largest weight because an episode that is not about this
failure helps nobody however well it went. The other four decide between things
that are all plausibly about this failure, which is the case that actually
occurs: a service with three previous OOMKills, one of which was diagnosed.

Recency is an exponential decay with a half-life rather than a window. A cliff
at thirty days would make an episode's rank jump the morning it aged out, and
the thing that changed overnight would be the calendar.

Ties break on the correlation id. Not because the id means anything, but because
two episodes with identical scores have to come back in the same order on every
machine or the golden test is measuring the dictionary's iteration order.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime

from config.constants.memory import (
    RANK_WEIGHT_COMPONENT_OVERLAP,
    RANK_WEIGHT_EFFECTIVENESS,
    RANK_WEIGHT_RECENCY,
    RANK_WEIGHT_RESOLVED,
    RANK_WEIGHT_SIMILARITY,
    RANKING_FORMULA_VERSION,
    RANKING_RECENCY_HALF_LIFE_DAYS,
)
from platform.memory.models import Component, MemoryEpisode, ScoredEpisode, component_set

SECONDS_PER_DAY = 86_400.0


def component_overlap(query: Sequence[Component], episode: Sequence[Component]) -> float:
    """Return how much of what the agent named this episode touches, in ``[0, 1]``.

    Asymmetric on purpose: the denominator is what the *query* named, not the
    union. An episode that touched nine services including the one asked about
    is a full match for that question, and a Jaccard index would score it 0.1
    for the crime of having been a large incident.
    """
    wanted = component_set(query)
    if not wanted:
        return 0.0
    return len(wanted & component_set(episode)) / len(wanted)


def recency(
    occurred_at: datetime | None,
    *,
    now: datetime,
    half_life_days: float = RANKING_RECENCY_HALF_LIFE_DAYS,
) -> float:
    """Return an exponential decay in ``(0, 1]``, halving every ``half_life_days``.

    An episode with no recorded time scores 0.0. Guessing "recent" would promote
    exactly the records whose provenance is weakest.
    """
    if occurred_at is None:
        return 0.0
    if half_life_days <= 0:
        raise ValueError(f"a recency half-life must be positive, got {half_life_days}")

    age_days = (now - occurred_at).total_seconds() / SECONDS_PER_DAY
    if age_days <= 0.0:
        return 1.0
    return math.pow(0.5, age_days / half_life_days)


def score_episode(
    episode: MemoryEpisode,
    *,
    similarity: float,
    query_components: Sequence[Component] = (),
    now: datetime,
) -> ScoredEpisode:
    """Return ``episode`` with every ranking term computed and the total attached."""
    resolved = 1.0 if episode.resolved else 0.0
    overlap = component_overlap(query_components, episode.components)
    effectiveness = min(max(episode.effectiveness_score, 0.0), 1.0)
    freshness = recency(episode.occurred_at, now=now)

    return ScoredEpisode(
        episode=episode,
        similarity=similarity,
        resolved=resolved,
        component_overlap=overlap,
        effectiveness=effectiveness,
        recency=freshness,
        score=(
            RANK_WEIGHT_SIMILARITY * similarity
            + RANK_WEIGHT_RESOLVED * resolved
            + RANK_WEIGHT_COMPONENT_OVERLAP * overlap
            + RANK_WEIGHT_EFFECTIVENESS * effectiveness
            + RANK_WEIGHT_RECENCY * freshness
        ),
        formula_version=RANKING_FORMULA_VERSION,
    )


def rank(
    candidates: Sequence[ScoredEpisode],
    *,
    limit: int | None = None,
) -> tuple[ScoredEpisode, ...]:
    """Return ``candidates`` best first, deterministically, cut to ``limit``."""
    ordered = sorted(candidates, key=lambda found: (-found.score, found.correlation_id))
    return tuple(ordered if limit is None else ordered[:limit])


__all__ = [
    "SECONDS_PER_DAY",
    "component_overlap",
    "rank",
    "recency",
    "score_episode",
]
