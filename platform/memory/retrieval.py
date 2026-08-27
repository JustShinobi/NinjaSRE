"""Similarity search, team-scoped, with every recall written into the trace.

Three things happen here and each one is a requirement rather than a step.

**The search is scoped twice.** The organisation boundary is structural — no
repository port takes an ``org_id``, so a cross-organisation read cannot be
phrased — and the team boundary is a metadata filter applied inside the index
plus a check on every row that comes back. Belt and braces on purpose: the
filter is what makes it fast and the check is what makes it true, and a filter
that silently stopped being applied would leak without either failing.

**An empty result is a result.** No relevant memory is the common case for the
first few weeks of any deployment, and it must come back as an empty tuple with
``searched=True`` rather than as an error or an unavailability. The distinction
the agent needs is between "there is nothing like this" and "there was nowhere to
look", and only the second is a reason to change strategy.

**Recall has two halves and both always run.** A similarity search over the
episode vectors answers "what does this incident resemble". An exact lookup by
fingerprint answers "has this alert fired before", and it depends on no
embedding and on nobody having chosen the same words twice, which is what makes
it the half that cannot be defeated by vocabulary. A caller that carries filters
still gets both; skipping the exact half whenever the agent said something
specific would switch off the robust one exactly when the agent knew most.

Neither the component nor the issue type excludes anything. They are ranking
signals, and the reason is a measured one: an investigation that named the
failing exporter searched a corpus whose episode had named the failing
container, and every filter it carried excluded the one episode that would have
explained the incident.

**Every recall is recorded.** Query, filters, what came back, and — filled in
later, at run end — whether the agent actually used any of it. That last field is
what turns "the agent has memory" into a number: a deployment where recall runs
constantly and is never acted on is one where ranking is wrong, and nothing else
in the system would say so.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from config.constants.memory import (
    DEFAULT_MEMORY_RECALL_RESULTS,
    MAX_MEMORY_RECALL_RESULTS,
    MEMORY_RECALL_CANDIDATE_FACTOR,
)
from config.constants.persistence import EPISODE_VECTOR_NAMESPACE, MAX_VECTOR_TOP_K
from config.prompts.memory import MEMORY_RECALL_DISABLED
from platform.memory.embeddings.port import Embedder, embed_one
from platform.memory.models import MemoryEpisode, RecallQuery, ScoredEpisode
from platform.memory.models import now as _utc_now
from platform.memory.policy import MemoryPolicy
from platform.memory.ranking import rank, score_episode
from platform.observability.logging import get_logger
from platform.persistence.errors import PersistenceError, VectorNamespaceUnknown
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import SimilarityMatch

if TYPE_CHECKING:  # The strategy package imports this module, so this is a name only.
    from platform.memory.strategy.models import Strategy

logger = get_logger(__name__)

#: The metadata key the team filter is applied on. One name, used by the writer
#: and the reader, so a rename cannot leave the filter matching nothing — which
#: would return no results rather than the wrong ones, and therefore look like a
#: quiet corpus rather than a broken filter.
TEAM_METADATA_KEY = "team_node_id"


@dataclass(frozen=True, slots=True)
class RecallResult:
    """What one search returned, and whether it ran at all.

    ``strategies`` is filled in by the synthesis layer *after* the search, never
    by this module. Keeping the field here rather than in a second result type is
    what lets one capability return both without every implementer of the recall
    protocol learning about playbooks; ``empty`` and ``correlation_ids`` stay
    about episodes for the same reason, because they answer "did this failure
    happen before", which a generalisation cannot.
    """

    query: RecallQuery
    episodes: tuple[ScoredEpisode, ...] = ()
    searched: bool = True
    reason: str = ""
    strategies: tuple[Strategy, ...] = ()

    @property
    def empty(self) -> bool:
        """Return whether the search matched nothing."""
        return not self.episodes

    @property
    def correlation_ids(self) -> tuple[str, ...]:
        """Return the episodes this result points at, in rank order."""
        return tuple(found.correlation_id for found in self.episodes)


@dataclass(slots=True)
class RecallRecord:
    """One recall as the run trace records it (FR-022)."""

    query: str
    component: str = ""
    issue_type: str = ""
    #: The bucket ``issue_type`` was classified into before it was compared. Both
    #: are recorded because they answer different questions: the agent's words
    #: say what it was looking for, and the bucket says why an episode filed
    #: under other words came back anyway.
    canonical_issue_type: str = ""
    returned: tuple[str, ...] = ()
    searched: bool = True
    reason: str = ""
    acted_on: bool = False
    #: The playbooks this recall also surfaced, by label, and whether the run
    #: went on to use one. Separate from ``acted_on`` because the ablation asks
    #: whether *synthesis* changed the answer, and an agent that cited three
    #: episodes and ignored the playbook has answered that question with a no.
    strategies: tuple[str, ...] = ()
    strategy_acted_on: bool = False

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this recall."""
        return {
            "query": self.query,
            "component": self.component,
            "issue_type": self.issue_type,
            "canonical_issue_type": self.canonical_issue_type,
            "returned": list(self.returned),
            "searched": self.searched,
            "reason": self.reason,
            "acted_on": self.acted_on,
            "strategies": list(self.strategies),
            "strategy_acted_on": self.strategy_acted_on,
        }


@dataclass(slots=True)
class RecallLedger:
    """Every recall one run made, and which of them the run went on to use.

    Run-scoped and mutable. It is handed to the retriever at construction and
    read at run end, which is the only moment at which "did the agent act on
    this" is answerable — the answer depends on what the run said afterwards.
    """

    records: list[RecallRecord] = field(default_factory=list)

    def record(self, result: RecallResult) -> RecallRecord:
        """Store ``result`` and return the record it produced."""
        entry = RecallRecord(
            query=result.query.text,
            component=result.query.component,
            issue_type=result.query.issue_type,
            canonical_issue_type=result.query.canonical_issue_type().value,
            returned=result.correlation_ids,
            searched=result.searched,
            reason=result.reason,
            strategies=tuple(strategy.key.label for strategy in result.strategies),
        )
        self.records.append(entry)
        return entry

    def attach_strategies(self, entry: RecallRecord, labels: Sequence[str]) -> RecallRecord:
        """Note that ``entry``'s recall also surfaced these playbooks.

        Separate from ``record`` because synthesis happens after the search: the
        recall is already in the ledger by the time anybody knows whether a
        playbook came with it, and rewriting history from the search path would
        mean the search knew about strategies, which is the coupling this
        arrangement exists to avoid.
        """
        entry.strategies = tuple(labels)
        return entry

    def mark_acted_on(self, text: str) -> int:
        """Mark every recall whose results ``text`` mentions, and return how many.

        Substring matching on the correlation id. Crude, and correct for what it
        is asked: a correlation id is a generated identifier that does not occur
        by accident, so a run whose answer contains one either cited it or was
        shown it by the shaped result and repeated it. Either way the recall
        reached the conclusion, which is what the number is about.

        Playbook labels are matched the same way and counted separately. "The
        agent had a playbook" and "the agent used it" are different facts, and
        the ablation is about the second one.
        """
        marked = 0
        for entry in self.records:
            if not entry.acted_on and entry.returned and _mentions(text, entry.returned):
                entry.acted_on = True
                marked += 1
            if not entry.strategy_acted_on and entry.strategies:
                entry.strategy_acted_on = _mentions(text, entry.strategies)
        return marked

    def trace_summary(self) -> dict[str, Any]:
        """Return what the run trace records about recall."""
        return {
            "recalls": len(self.records),
            "recalls_with_results": sum(1 for entry in self.records if entry.returned),
            "recalls_acted_on": sum(1 for entry in self.records if entry.acted_on),
            "strategies_returned": sum(len(entry.strategies) for entry in self.records),
            "strategies_acted_on": sum(1 for entry in self.records if entry.strategy_acted_on),
            "records": [entry.to_record() for entry in self.records],
        }


def _mentions(text: str, identifiers: Sequence[str]) -> bool:
    """Return whether ``text`` names any of ``identifiers``."""
    return any(identifier in text for identifier in identifiers)


def bounded_limit(requested: int) -> int:
    """Return the number of results a request may have, within the ceilings."""
    if requested <= 0:
        return DEFAULT_MEMORY_RECALL_RESULTS
    return min(requested, MAX_MEMORY_RECALL_RESULTS)


def candidate_count(limit: int) -> int:
    """Return how many neighbours to fetch before ranking cuts them down.

    More than the answer needs, because ranking demotes unresolved, stale, and
    low-effectiveness episodes and has to have something to promote in their
    place. Capped at the index's own ceiling so the multiplier can never turn a
    large request into a refused one.
    """
    return min(limit * MEMORY_RECALL_CANDIDATE_FACTOR, MAX_VECTOR_TOP_K)


@dataclass(slots=True)
class MemoryRetriever:
    """Team-scoped recall over the episode corpus."""

    gateway: PersistenceGateway
    scope: TenantScope
    embedder: Embedder
    policy: MemoryPolicy = field(default_factory=MemoryPolicy)
    ledger: RecallLedger = field(default_factory=RecallLedger)
    clock: Callable[[], datetime] = _utc_now

    def __post_init__(self) -> None:
        if not self.scope.team_node_id:
            raise ValueError(
                f"{self.scope.org_id}: recall must be scoped to a team — an unscoped "
                "search is one that can return another team's incidents"
            )

    async def search(self, query: RecallQuery, *, record: bool = True) -> RecallResult:
        """Return the episodes resembling ``query``, ranked, scoped to this team.

        Every outcome is a ``RecallResult``, and the line between the two kinds
        of "nothing" is drawn here. A team that has never written an episode has
        no vector namespace, and that is an *empty corpus* — the honest answer is
        "this failure is new to the team", which is exactly what every
        deployment's first weeks look like. Anything else the store does wrong is
        an unavailability, because then there really was nowhere to look and the
        agent should not conclude anything from it.

        Both halves run, and the exact one runs first so that a store failure in
        the similarity half cannot cost a fingerprint match. An episode found by
        both is one episode: the halves are unioned on the correlation id, and
        the exact flag survives the union.

        ``record=False`` is for the searches the *system* makes on the agent's
        behalf — widening an episode set before synthesising a playbook over it.
        Those did not happen because the agent decided to look something up, and
        counting them would make "how often does the agent consult memory, and
        how often does it act on what comes back" a ratio between two different
        populations.
        """
        if not self.policy.read_enabled:
            return self._recorded(
                RecallResult(query=query, searched=False, reason=MEMORY_RECALL_DISABLED),
                record=record,
            )

        limit = bounded_limit(query.limit)
        try:
            exact = await self._by_signature(query, limit=limit)
            try:
                matches = await self._neighbours(query, limit=limit)
            except VectorNamespaceUnknown:
                # An empty corpus for the similarity half. The exact half reads
                # rows rather than vectors, so whatever it found still stands —
                # returning nothing here would discard a fingerprint match
                # because a *different* index had never been declared.
                logger.info("memory.corpus_empty", team=self.scope.team_node_id)
                matches = ()
            episodes = await self._load(matches, query, limit=limit, exact=exact)
        except PersistenceError as error:
            logger.warning("memory.recall_unavailable", error=str(error))
            return self._recorded(
                RecallResult(query=query, searched=False, reason=str(error)), record=record
            )

        result = RecallResult(query=query, episodes=episodes)
        logger.info(
            "memory.recalled",
            query=query.text,
            component=query.component,
            issue_type=query.issue_type,
            canonical_issue_type=query.canonical_issue_type().value,
            returned=len(episodes),
            exact_matches=sum(1 for found in episodes if found.exact_match),
        )
        return self._recorded(result, record=record)

    async def _by_signature(self, query: RecallQuery, *, limit: int) -> dict[str, MemoryEpisode]:
        """Return the episodes carrying this query's exact fingerprint, by id.

        The half that owes nothing to an embedding or to two runs having picked
        the same words. It is keyed on the canonical issue type and the
        components the caller named, so it answers the narrow question "has this
        alert, on these things, fired before" — and it answers it whether or not
        the similarity half has anything to say.

        ``VectorNamespaceUnknown`` cannot arise here and is not caught: this
        reads episode rows. A team with a populated corpus and no vector index
        still gets its exact matches.
        """
        signature = query.signature()
        if not signature:
            return {}

        async with self.gateway.begin(self.scope) as uow:
            stored = await uow.episodes.by_signature(signature, limit=limit)

        found: dict[str, MemoryEpisode] = {}
        for row in stored:
            episode = MemoryEpisode.from_stored(row, org_id=self.scope.org_id)
            if self._visible(episode, {}):
                found[episode.correlation_id] = episode
        return found

    async def _neighbours(self, query: RecallQuery, *, limit: int) -> tuple[SimilarityMatch, ...]:
        """Return the raw similarity matches for ``query``, filtered in the index."""
        embedding = await embed_one(self.embedder, query.text)
        async with self.gateway.begin(self.scope) as uow:
            return await uow.vectors.search(
                EPISODE_VECTOR_NAMESPACE,
                embedding,
                k=candidate_count(limit),
                filters=self._filters(query),
            )

    def _filters(self, query: RecallQuery) -> dict[str, Any]:
        """Return the metadata filter this search runs under: the team, and nothing else.

        The team is a boundary — an episode belonging to another team is one this
        caller may not see under any ranking. Everything the *agent* said is a
        preference and is applied by the ranker instead. The issue type used to
        be filtered here, and it cost a live investigation the only episode that
        described its own incident, because the run that wrote that episode had
        called the same failure something else.

        ``query`` is still taken. Reducing this to a constant would move the
        decision about what may narrow an index read out of the one method whose
        name says that is what it decides.
        """
        del query
        return {TEAM_METADATA_KEY: self.scope.team_node_id}

    async def _load(
        self,
        matches: Sequence[SimilarityMatch],
        query: RecallQuery,
        *,
        limit: int,
        exact: Mapping[str, MemoryEpisode],
    ) -> tuple[ScoredEpisode, ...]:
        """Return both halves' episodes, scored and ranked, or an empty tuple.

        Unioned on the correlation id, so an episode the fingerprint and the
        index both found is scored once — with the similarity the index measured
        *and* the exact flag, because the two halves agreeing is not a reason to
        lose either fact.

        An episode only the fingerprint found is scored with a similarity of
        zero. That is the truthful number: no embedding was consulted for it. It
        still leads the results, because ``rank`` gives an exact match precedence
        over the weighted sum rather than a weight inside it.
        """
        if not matches and not exact:
            return ()

        moment = self.clock()
        wanted = query.components()
        classification = query.canonical_issue_type()
        scored: list[ScoredEpisode] = []
        seen: set[str] = set()

        def score(episode: MemoryEpisode, *, similarity: float) -> ScoredEpisode:
            return score_episode(
                episode,
                similarity=similarity,
                query_components=wanted,
                query_issue_type=classification,
                now=moment,
                exact_match=episode.correlation_id in exact,
            )

        async with self.gateway.begin(self.scope) as uow:
            for match in matches:
                stored = await uow.episodes.get(match.vector_id)
                if stored is None:
                    # A vector whose episode is gone. Retention deletes both in
                    # one unit of work, so this is a corpus mid-sweep rather than
                    # an error — skip it and say so.
                    logger.info("memory.dangling_vector", episode=match.vector_id)
                    continue

                episode = MemoryEpisode.from_stored(stored, org_id=self.scope.org_id)
                if not self._visible(episode, match.metadata):
                    continue
                seen.add(episode.correlation_id)
                scored.append(score(episode, similarity=match.score))

        scored.extend(
            score(episode, similarity=0.0)
            for correlation_id, episode in exact.items()
            if correlation_id not in seen
        )

        return rank(scored, limit=limit)

    def _visible(self, episode: MemoryEpisode, metadata: Mapping[str, Any]) -> bool:
        """Return whether this team is allowed to see ``episode``.

        Checked against the row, not only against the metadata the filter used.
        A metadata value is a copy written at index time; the row is the fact,
        and the two disagreeing is exactly the case a filter alone would miss.
        """
        team = self.scope.team_node_id
        if episode.team_node_id == team and metadata.get(TEAM_METADATA_KEY, team) == team:
            return True
        logger.warning(
            "memory.cross_team_match_refused",
            episode=episode.correlation_id,
            requesting_team=team,
        )
        return False

    def _recorded(self, result: RecallResult, *, record: bool = True) -> RecallResult:
        """Store ``result`` in the run's ledger and return it unchanged."""
        if record:
            self.ledger.record(result)
        return result


__all__ = [
    "TEAM_METADATA_KEY",
    "MemoryRetriever",
    "RecallLedger",
    "RecallRecord",
    "RecallResult",
    "bounded_limit",
    "candidate_count",
]
