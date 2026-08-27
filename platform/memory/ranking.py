"""Which precedent the agent reads first, as six weighted terms and no model call.

    score = w_similarity   * similarity
          + w_resolved     * resolved
          + w_components   * component_overlap
          + w_issue_type   * issue_type_match
          + w_effectiveness* effectiveness
          + w_recency      * recency

No LLM anywhere in this path, and that is a requirement rather than an
optimisation. Ranking runs inside a tool call the agent is waiting on, and it
has to produce the same order twice for a trajectory comparison to mean
anything — a ranker that consulted a model would be neither fast nor repeatable.

Similarity carries the largest weight because an episode that is not about this
failure helps nobody however well it went. The other five decide between things
that are all plausibly about this failure, which is the case that actually
occurs: a service with three previous OOMKills, one of which was diagnosed.

Component overlap and issue-type agreement are terms here rather than filters
upstream, and that is the correction this module exists to carry. Both are
things an agent *says* about the incident in front of it, in words a previous
run had no way to agree with in advance; excluding on either meant an
investigation that named the failing exporter never saw the episode written by
the run that had named the failing container. A weight promotes what agrees and
declines to promote what does not, which is the whole of what a claim about
vocabulary is worth.

Neither term fires on an unclassifiable query. A caller whose issue type lands
in the ``other`` bucket has expressed no preference — matching it against every
other unclassifiable episode would make "nobody could name this failure" a
similarity between two failures.

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
    RANK_COMPONENT_NAME_ONLY_CREDIT,
    RANK_WEIGHT_COMPONENT_OVERLAP,
    RANK_WEIGHT_EFFECTIVENESS,
    RANK_WEIGHT_ISSUE_TYPE_MATCH,
    RANK_WEIGHT_RECENCY,
    RANK_WEIGHT_RESOLVED,
    RANK_WEIGHT_SIMILARITY,
    RANKING_FORMULA_VERSION,
    RANKING_RECENCY_HALF_LIFE_DAYS,
)
from platform.memory.models import (
    Component,
    IssueType,
    MemoryEpisode,
    ScoredEpisode,
    component_set,
)

SECONDS_PER_DAY = 86_400.0


def component_overlap(query: Sequence[Component], episode: Sequence[Component]) -> float:
    """Return how much of what the agent named this episode touches, in ``[0, 1]``.

    Asymmetric on purpose: the denominator is what the *query* named, not the
    union. An episode that touched nine services including the one asked about
    is a full match for that question, and a Jaccard index would score it 0.1
    for the crime of having been a large incident.

    A name that matches under a different type scores partial credit rather than
    nothing. Component types are free-form because no vendor's vocabulary can be
    anticipated, and the price of that is two runs recording one container as
    ``container:lxc/122`` and ``guest:lxc/122``. They are the same box, they are
    not the same claim, and the score says both.
    """
    wanted = {component.label: component for component in query}
    if not wanted:
        return 0.0

    labels = component_set(episode)
    names = frozenset(component.name for component in episode)

    credit = 0.0
    for component in wanted.values():
        if component.label in labels:
            credit += 1.0
        elif component.name in names:
            credit += RANK_COMPONENT_NAME_ONLY_CREDIT if component.type else 1.0
    return credit / len(wanted)


def issue_type_match(wanted: IssueType, episode: IssueType) -> float:
    """Return whether the episode is filed under the class the query named.

    Zero when the query named nothing, and zero when what it named could not be
    placed in the vocabulary. Both are the same statement — the caller has told
    ranking nothing it can act on — and returning 1.0 for two unclassified
    things would rank on a shared failure to classify.
    """
    if not wanted.classified:
        return 0.0
    return 1.0 if episode is wanted else 0.0


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
    query_issue_type: IssueType = IssueType.OTHER,
    now: datetime,
    exact_match: bool = False,
) -> ScoredEpisode:
    """Return ``episode`` with every ranking term computed and the total attached.

    ``exact_match`` is carried through rather than scored. An episode found by
    its fingerprint did not come from the index and has no similarity to report;
    what it has is a fact, and ``rank`` gives a fact precedence over a weighted
    sum instead of paying it a weight it could be outvoted on.
    """
    resolved = 1.0 if episode.resolved else 0.0
    overlap = component_overlap(query_components, episode.components)
    classification = issue_type_match(query_issue_type, episode.canonical_issue_type)
    effectiveness = min(max(episode.effectiveness_score, 0.0), 1.0)
    freshness = recency(episode.occurred_at, now=now)

    return ScoredEpisode(
        episode=episode,
        similarity=similarity,
        resolved=resolved,
        component_overlap=overlap,
        issue_type_match=classification,
        effectiveness=effectiveness,
        recency=freshness,
        score=(
            RANK_WEIGHT_SIMILARITY * similarity
            + RANK_WEIGHT_RESOLVED * resolved
            + RANK_WEIGHT_COMPONENT_OVERLAP * overlap
            + RANK_WEIGHT_ISSUE_TYPE_MATCH * classification
            + RANK_WEIGHT_EFFECTIVENESS * effectiveness
            + RANK_WEIGHT_RECENCY * freshness
        ),
        formula_version=RANKING_FORMULA_VERSION,
        exact_match=exact_match,
    )


def rank(
    candidates: Sequence[ScoredEpisode],
    *,
    limit: int | None = None,
) -> tuple[ScoredEpisode, ...]:
    """Return ``candidates`` best first, deterministically, cut to ``limit``.

    Exact fingerprint matches lead, whatever the weighted sum says. The two
    halves of recall answer different questions — "what does this incident
    resemble" and "has this exact alert fired before" — and when they disagree
    the second one is the one that was measured rather than estimated. Within
    each block the score orders as usual, and ties still break on the
    correlation id so the order is the same on every machine.
    """
    ordered = sorted(
        candidates,
        key=lambda found: (not found.exact_match, -found.score, found.correlation_id),
    )
    return tuple(ordered if limit is None else ordered[:limit])


__all__ = [
    "SECONDS_PER_DAY",
    "component_overlap",
    "issue_type_match",
    "rank",
    "recency",
    "score_episode",
]
