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
from platform.memory.models import (
    Component,
    IssueType,
    MemoryEpisode,
    RecallQuery,
    ScoredEpisode,
)
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


def test_a_component_named_under_a_different_type_scores_partial_credit() -> None:
    """``container:lxc/122`` and ``guest:lxc/122`` are the same box, differently filed.

    Both spellings are in the corpus, written by two runs about one incident.
    Scoring them zero says they are unrelated, which is false; scoring them one
    says the two runs agreed, which is also false. A query that named no type at
    all asserted nothing to disagree with and scores full credit.
    """
    guest = (Component(type="guest", name="lxc/122"),)

    assert component_overlap((Component(type="container", name="lxc/122"),), guest) == 0.5
    assert component_overlap((Component(type="", name="lxc/122"),), guest) == 1.0
    assert component_overlap((Component(type="guest", name="lxc/122"),), guest) == 1.0
    assert component_overlap((Component(type="guest", name="lxc/999"),), guest) == 0.0


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


async def test_a_named_component_promotes_its_episodes_without_hiding_the_rest(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """A signal, not a filter: naming a component orders the results.

    Both episodes are about the same symptom and the query text matches them
    equally. The one on the named component leads, and the other one is still
    there — because "the agent thinks the failing workload is search-api" is a
    belief formed from partial evidence, and a belief must not be able to delete
    the episode that would have corrected it.
    """
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

    assert found.correlation_ids == ("search", "payments")


async def test_a_named_issue_type_promotes_its_episodes_without_hiding_the_rest(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """The classification orders the results too, and excludes nothing.

    This is the exclusion that was measured costing an investigation its
    precedent. The index no longer filters on the issue type at all: the team is
    a boundary and belongs in the filter, and everything the agent asserted about
    the incident is a preference and belongs in the ranker.
    """
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

    assert found.correlation_ids == ("certs", "oom")


# -- vocabulary drift ---------------------------------------------------------


def shutdown_episode(scope: TenantScope) -> MemoryEpisode:
    """Return the episode the live deployment actually wrote.

    Verbatim from the incident this section exists for: the extractor's own
    words for the failure, and the four components the run had looked at.
    """
    return MemoryEpisode(
        correlation_id="lxc-122-shutdown",
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
        issue_type="manual_shutdown",
        issue_description="lxc/122 stopped after a vzshutdown issued by root@pam",
        components=tuple(
            Component.parse(label)
            for label in ("service:redis", "container:lxc/122", "node:pve01", "cluster:HAL9000")
        ),
        capabilities_used=("proxmox_guest_status", "proxmox_task_log"),
        resolved=True,
        root_cause="an operator ran vzshutdown against the container",
        summary=(
            "The container stopped because somebody shut it down. The task log names "
            "root@pam and the guest never restarted."
        ),
        effectiveness_score=0.8,
        occurred_at=at(-1),
    )


async def test_an_episode_is_found_by_a_recall_that_words_it_differently(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """The measured defect: two vocabularies for one incident, forty-four seconds apart.

    An investigation concluded and wrote the episode above. The next
    investigation into the same incident searched with the alert's own words —
    ``ProxmoxGuestStopped`` on ``pve-exporter`` — and got nothing back, because
    both of those were filters and neither matched. Neither vocabulary is wrong.
    They were invented by different callers at different moments, and nothing
    made them agree.

    Ranking is what makes the disagreement survivable: naming a component or an
    issue type says which episodes are *preferred*, never which ones exist.
    """
    await seed(gateway, scope, embedder, shutdown_episode(scope))

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(
            text="ProxmoxGuestStopped lxc 122 vzshutdown root@pam",
            component="pve-exporter",
            issue_type="ProxmoxGuestStopped",
        )
    )

    assert found.correlation_ids == ("lxc-122-shutdown",)


async def test_the_named_component_and_issue_type_order_the_results(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """Preference, not exclusion — the episode that matches both leads.

    The point of demoting the two filters to signals is that they still decide
    what the agent reads *first*. An episode sharing neither the component nor
    the classification comes back last rather than not at all.
    """
    await seed(
        gateway,
        scope,
        embedder,
        episode("both", scope, issue_type="oom_kill", components=("service:payments-api",)),
        episode("neither", scope, issue_type="certificate_expiry", components=("service:tls",)),
    )

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(
            text="payments-api restarting with exit code 137",
            component="payments-api",
            issue_type="oom_kill",
        )
    )

    assert found.correlation_ids == ("both", "neither")


async def test_the_signature_half_runs_even_when_the_recall_carries_filters(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """Exact fingerprint matching depends on no vocabulary, so it always runs.

    The episode is written with an embedding that has nothing in common with the
    query text, so the similarity half cannot reach it. It has fired before under
    exactly this fingerprint, and that is a fact rather than an estimate — it
    leads the results, and it is flagged as an exact match so a reader can tell
    which half found it.
    """
    fingerprinted = MemoryEpisode(
        correlation_id="fired-before",
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
        issue_type="oom_kill",
        issue_description="zzzz",
        components=(Component(type="service", name="payments-api"),),
        resolved=True,
        summary="zzzz",
        occurred_at=at(-1),
    )
    await seed(
        gateway,
        scope,
        embedder,
        fingerprinted,
        episode("closer", scope, components=("service:payments-api-worker",)),
    )

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(
            text="something with no words in common at all",
            component="service:payments-api",
            issue_type="oom_kill",
        )
    )

    assert found.correlation_ids[0] == "fired-before"
    assert found.episodes[0].exact_match is True
    assert found.episodes[1].exact_match is False


async def test_a_signature_match_leads_even_when_the_ranked_search_disagrees(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """When the two halves disagree the fingerprint wins, and both are returned.

    The other episode is the better textual match and would outrank the
    fingerprinted one on every term of the formula. It still comes second: a
    signature is what "this exact alert has fired before" means, and an
    embedding is a guess about what an incident resembles.
    """
    fingerprinted = MemoryEpisode(
        correlation_id="same-fingerprint",
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
        issue_type="oom_kill",
        issue_description="qqqq",
        components=(Component(type="service", name="payments-api"),),
        resolved=False,
        summary="qqqq",
        effectiveness_score=0.0,
        occurred_at=at(-400),
    )
    await seed(
        gateway,
        scope,
        embedder,
        fingerprinted,
        episode(
            "better-on-every-term",
            scope,
            components=("service:payments-api-worker",),
            effectiveness=1.0,
            age_days=0.0,
        ),
    )

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(
            text="payments-api restarting with exit code 137",
            component="service:payments-api",
            issue_type="oom_kill",
        )
    )

    assert found.correlation_ids == ("same-fingerprint", "better-on-every-term")


async def test_a_recall_that_described_nothing_promotes_nothing_as_exact(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """Two runs that each failed to classify anything have not matched each other.

    An episode whose extraction produced neither a classification nor a component
    is fingerprinted over the ``other`` bucket and an empty component list — and
    so would a search that named neither. Letting those meet would give exact-match
    precedence to every unclassifiable episode in the corpus, on every search that
    happened not to carry a filter.
    """
    unclassified = MemoryEpisode(
        correlation_id="nobody-could-say",
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
        issue_type=IssueType.OTHER.value,
        summary="Something went wrong on the cluster and the run could not say what.",
        occurred_at=at(-1),
    )
    await seed(gateway, scope, embedder, unclassified, episode("classified", scope))

    found = await retriever(gateway, scope, embedder).search(
        RecallQuery(text="payments-api restarting with exit code 137")
    )

    assert RecallQuery(text="anything").signature() == ""
    assert not any(entry.exact_match for entry in found.episodes)


async def test_the_ledger_records_the_words_the_agent_used_and_the_bucket(
    gateway: PersistenceGateway, scope: TenantScope, embedder: LocalEmbedder
) -> None:
    """The trace has to answer why an episode matched, so it holds both.

    Recording only the canonical bucket would hide what the agent actually
    searched for; recording only the agent's words would hide why an episode
    classified differently still came back.
    """
    ledger = RecallLedger()
    await seed(gateway, scope, embedder, shutdown_episode(scope))

    await retriever(gateway, scope, embedder, ledger=ledger).search(
        RecallQuery(text="lxc 122 stopped", issue_type="ProxmoxGuestStopped")
    )

    record = ledger.records[0].to_record()
    assert record["issue_type"] == "ProxmoxGuestStopped"
    assert record["canonical_issue_type"] == IssueType.WORKLOAD_STOPPED.value


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
