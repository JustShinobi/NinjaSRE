"""Recall: what comes back, in what order, and what can never come back.

**SC-005** is the one that matters most and is asserted twice — once across teams
inside one organisation, once across organisations. Cross-team leakage is the
failure that would be invisible until an audit, because a leaked episode looks
exactly like a relevant one.

**Acceptance scenario 6** is the ranking claim: a resolved episode on the named
component with a high effectiveness score outranks an unresolved one, even when
the unresolved one is a slightly better textual match. That is the whole reason
ranking is five terms rather than a similarity sort.

**FR-015** is the quiet one. No relevant memory is the common case for weeks
after a deployment goes in, and it has to come back as an empty search rather
than as any kind of failure — the agent's next move differs, and only one of the
two is a reason to change strategy.
"""

from __future__ import annotations

import pytest

from config.constants.memory import DEFAULT_MEMORY_RECALL_RESULTS, MAX_MEMORY_RECALL_RESULTS
from config.constants.persistence import EPISODE_VECTOR_NAMESPACE, MAX_VECTOR_TOP_K
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.embeddings.port import embed_one
from platform.memory.models import Component, MemoryEpisode, RecallQuery, ScoredEpisode
from platform.memory.policy import MemoryPolicy
from platform.memory.ranking import component_overlap, rank, recency, score_episode
from platform.memory.retrieval import MemoryRetriever, RecallLedger, bounded_limit, candidate_count
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import VectorRecord
from tests.unit.platform.memory.conftest import at

pytestmark = pytest.mark.unit


def episode(
    correlation_id: str,
    scope: TenantScope,
    *,
    issue_type: str = "oom_kill",
    description: str = "payments-api restarting with exit code 137",
    components: tuple[str, ...] = ("service:payments-api",),
    resolved: bool = True,
    effectiveness: float = 0.8,
    age_days: float = 1.0,
    summary: str = "payments-api OOMKilled after a deploy lowered the memory limit",
    root_cause: str = "the memory limit was lowered",
) -> MemoryEpisode:
    """Return one episode of the corpus under test."""
    return MemoryEpisode(
        correlation_id=correlation_id,
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
        issue_type=issue_type,
        issue_description=description,
        components=tuple(Component.parse(label) for label in components),
        capabilities_used=("describe_workload", "read_logs"),
        resolved=resolved,
        root_cause=root_cause,
        summary=summary,
        effectiveness_score=effectiveness,
        occurred_at=at(-age_days),
    )


async def seed(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    *episodes: MemoryEpisode,
) -> None:
    """Write episodes and their vectors, as finalisation would."""
    async with gateway.begin(scope) as uow:
        await uow.vectors.ensure(
            EPISODE_VECTOR_NAMESPACE, model=embedder.model, dimension=embedder.dimension
        )
        for item in episodes:
            await uow.episodes.save(item.to_stored())
            await uow.vectors.upsert(
                EPISODE_VECTOR_NAMESPACE,
                [
                    VectorRecord(
                        vector_id=item.correlation_id,
                        embedding=await embed_one(embedder, item.embedding_text()),
                        metadata=item.vector_metadata(),
                    )
                ],
            )


def retriever(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    *,
    policy: MemoryPolicy | None = None,
    ledger: RecallLedger | None = None,
) -> MemoryRetriever:
    """Return a retriever with a fixed clock, so recency is a constant."""
    return MemoryRetriever(
        gateway=gateway,
        scope=scope,
        embedder=embedder,
        policy=policy or MemoryPolicy(),
        ledger=ledger or RecallLedger(),
        clock=at,
    )


# -- ranking, on its own ------------------------------------------------------


def test_component_overlap_is_measured_against_what_the_query_named() -> None:
    """A large incident that included the named service is a full match for it.

    A Jaccard index would score it 0.1 for the crime of having been large, and
    the episode most worth reading is often exactly the large one.
    """
    wanted = (Component(type="service", name="payments-api"),)
    broad = tuple(Component(type="service", name=f"svc-{index}") for index in range(9))

    assert component_overlap(wanted, (*broad, *wanted)) == 1.0
    assert component_overlap(wanted, broad) == 0.0
    assert component_overlap((), wanted) == 0.0


def test_recency_halves_at_the_half_life_and_never_reaches_zero() -> None:
    """A decay rather than a window: nothing changes rank because the calendar did."""
    now = at()

    assert recency(now, now=now) == 1.0
    assert recency(at(-30), now=now) == pytest.approx(0.5)
    assert 0.0 < recency(at(-3650), now=now) < 0.01
    assert recency(None, now=now) == 0.0


def test_a_resolved_effective_match_outranks_a_closer_unresolved_one(
    scope: TenantScope,
) -> None:
    """Acceptance scenario 6, in the ranker alone and without a store.

    The unresolved episode is the better textual match. It still loses, because
    "similar and nobody found the cause" is worth less than "slightly less
    similar and here is the cause".
    """
    now = at()
    resolved = score_episode(
        episode("resolved", scope, resolved=True, effectiveness=0.9),
        similarity=0.80,
        query_components=(Component(type="service", name="payments-api"),),
        now=now,
    )
    unresolved = score_episode(
        episode(
            "unresolved",
            scope,
            resolved=False,
            effectiveness=0.2,
            components=("service:other-api",),
        ),
        similarity=0.92,
        query_components=(Component(type="service", name="payments-api"),),
        now=now,
    )

    assert rank((unresolved, resolved))[0].correlation_id == "resolved"


def test_the_ranking_order_is_pinned_for_a_fixed_candidate_set(scope: TenantScope) -> None:
    """A golden test. A weight change that reorders this is a change worth noticing.

    Every candidate differs in exactly one term from the one above it, so a
    failure here names which weight moved rather than reporting that the order
    is different.
    """
    now = at()
    wanted = (Component(type="service", name="payments-api"),)
    candidates = (
        score_episode(
            episode("a-close-resolved-recent", scope, effectiveness=0.9, age_days=1),
            similarity=0.90,
            query_components=wanted,
            now=now,
        ),
        score_episode(
            episode("b-close-resolved-old", scope, effectiveness=0.9, age_days=365),
            similarity=0.90,
            query_components=wanted,
            now=now,
        ),
        score_episode(
            episode("c-close-unresolved-recent", scope, resolved=False, age_days=1),
            similarity=0.90,
            query_components=wanted,
            now=now,
        ),
        score_episode(
            episode(
                "d-far-resolved-recent",
                scope,
                effectiveness=0.9,
                age_days=1,
                components=("service:unrelated",),
            ),
            similarity=0.30,
            query_components=wanted,
            now=now,
        ),
    )

    assert [found.correlation_id for found in rank(candidates)] == [
        "a-close-resolved-recent",
        "b-close-resolved-old",
        "c-close-unresolved-recent",
        "d-far-resolved-recent",
    ]


def test_ties_break_on_the_correlation_id(scope: TenantScope) -> None:
    """Two identical scores have to come back in the same order on every machine."""
    identical = tuple(
        ScoredEpisode(episode=episode(name, scope), score=0.5) for name in ("zed", "alpha")
    )

    assert [found.correlation_id for found in rank(identical)] == ["alpha", "zed"]


# -- the bounds ---------------------------------------------------------------


def test_a_limit_is_defaulted_and_capped() -> None:
    """The agent may ask for nothing or for everything; it gets neither."""
    assert bounded_limit(0) == DEFAULT_MEMORY_RECALL_RESULTS
    assert bounded_limit(3) == 3
    assert bounded_limit(9_999) == MAX_MEMORY_RECALL_RESULTS


def test_the_candidate_pool_never_exceeds_the_index_ceiling() -> None:
    """The over-fetch multiplier must not turn a large request into a refused one."""
    assert candidate_count(bounded_limit(9_999)) <= MAX_VECTOR_TOP_K


# -- recall, end to end -------------------------------------------------------


async def test_recall_returns_the_matching_episode_ranked(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """Acceptance scenario 5: search on evidence, get the incident that was like this."""
    await seed(
        gateway,
        scope,
        embedder,
        episode("oom", scope),
        episode(
            "certs",
            scope,
            issue_type="certificate_expiry",
            description="ingress certificate expired",
            components=("service:search-api",),
            summary="the ingress certificate for search-api expired",
            root_cause="nobody renewed it",
        ),
    )

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(text="payments-api OOMKilled exit code 137")
    )

    assert found.searched
    assert found.correlation_ids[0] == "oom"


async def test_an_empty_corpus_is_an_empty_search_not_a_failure(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """FR-015: no relevant memory is the common case, and it is a normal outcome.

    The index exists — finalisation declares it on the first write — and holds
    nothing this query is like. That is a searched, empty result with no reason
    attached, and it is what a team's first few weeks look like.
    """
    await seed(gateway, scope, embedder)

    found = await retriever(gateway, scope, embedder).search(RecallQuery(text="anything at all"))

    assert found.searched
    assert found.empty
    assert found.reason == ""


async def test_a_team_that_has_never_written_an_episode_has_an_empty_corpus(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """A namespace that does not exist means nothing was ever written, not a broken store.

    This is every deployment's first weeks. Reporting it as an unavailability
    would tell the agent memory is broken on day one, which is both wrong and
    the kind of wrong that stops it ever searching again.
    """
    found = await retriever(gateway, scope, embedder).search(RecallQuery(text="anything"))

    assert found.searched
    assert found.empty
    assert found.reason == ""


async def test_a_store_that_is_broken_is_not_an_empty_corpus(
    gateway: PersistenceGateway, embedder: LocalEmbedder
) -> None:
    """ "Nothing like this" and "nowhere to look" lead to different next moves.

    An organisation that does not exist is the store failing, not a team with no
    history, and the agent must not conclude "no precedent" from it.
    """
    unknown = TenantScope(org_id="no-such-org", team_node_id="team-payments")

    found = await retriever(gateway, unknown, embedder).search(RecallQuery(text="anything"))

    assert not found.searched
    assert found.empty
    assert found.reason


async def test_a_component_filter_excludes_episodes_that_did_not_touch_it(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """A filter, not a hint: a caller that names a component means it."""
    await seed(
        gateway,
        scope,
        embedder,
        episode("payments", scope, components=("service:payments-api",)),
        episode("search", scope, components=("service:search-api",)),
    )

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(text="restarting with exit code 137", component="search-api")
    )

    assert found.correlation_ids == ("search",)


async def test_an_issue_type_filter_is_applied_inside_the_index(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """The cheap filter runs before any row is loaded."""
    await seed(
        gateway,
        scope,
        embedder,
        episode("oom", scope, issue_type="oom_kill"),
        episode("certs", scope, issue_type="certificate_expiry"),
    )

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(text="payments-api", issue_type="certificate_expiry")
    )

    assert found.correlation_ids == ("certs",)


# -- isolation ----------------------------------------------------------------


async def test_another_teams_episodes_are_invisible(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_team_scope: TenantScope,
    embedder: LocalEmbedder,
) -> None:
    """SC-005, within one organisation. A leaked episode looks like a relevant one."""
    await seed(gateway, other_team_scope, embedder, episode("theirs", other_team_scope))

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(text="payments-api OOMKilled exit code 137")
    )

    assert found.empty


async def test_another_organisations_episodes_are_invisible(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_org_scope: TenantScope,
    embedder: LocalEmbedder,
) -> None:
    """SC-005, across organisations — which the ports make unphrasable, and this proves."""
    await seed(gateway, other_org_scope, embedder, episode("theirs", other_org_scope))

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(text="payments-api OOMKilled exit code 137")
    )

    assert found.empty


def test_recall_cannot_be_constructed_without_a_team(
    gateway: PersistenceGateway, embedder: LocalEmbedder
) -> None:
    """An unscoped search is one that can return another team's incidents."""
    with pytest.raises(ValueError, match="scoped to a team"):
        MemoryRetriever(
            gateway=gateway,
            scope=TenantScope(org_id="acme"),
            embedder=embedder,
        )


# -- the trace ----------------------------------------------------------------


async def test_every_recall_is_recorded_with_its_query_and_results(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """FR-022, the first two thirds."""
    ledger = RecallLedger()
    await seed(gateway, scope, embedder, episode("oom", scope))

    await retriever(gateway, scope, embedder, ledger=ledger).search(
        RecallQuery(text="exit code 137", component="payments-api")
    )

    summary = ledger.trace_summary()
    assert summary["recalls"] == 1
    assert summary["recalls_with_results"] == 1
    assert ledger.records[0].query == "exit code 137"
    assert ledger.records[0].component == "payments-api"
    assert ledger.records[0].returned == ("oom",)


async def test_a_recall_the_answer_used_is_marked_as_acted_on(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """FR-022, the last third — the part that makes "memory helps" measurable."""
    ledger = RecallLedger()
    await seed(gateway, scope, embedder, episode("oom", scope))

    await retriever(gateway, scope, embedder, ledger=ledger).search(
        RecallQuery(text="exit code 137")
    )
    assert ledger.trace_summary()["recalls_acted_on"] == 0

    ledger.mark_acted_on("This matches episode oom, which found the same cause.")

    assert ledger.trace_summary()["recalls_acted_on"] == 1


async def test_reading_disabled_records_the_recall_without_searching(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """The read half of the ablation switch, and the trace still says it happened."""
    ledger = RecallLedger()
    await seed(gateway, scope, embedder, episode("oom", scope))

    found = await retriever(
        gateway,
        scope,
        embedder,
        policy=MemoryPolicy().without("memory_read"),
        ledger=ledger,
    ).search(RecallQuery(text="exit code 137"))

    assert not found.searched
    assert found.empty
    assert "switched off" in found.reason
    assert ledger.records[0].searched is False
