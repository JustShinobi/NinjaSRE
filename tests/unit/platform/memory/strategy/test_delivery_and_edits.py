"""What the agent is shown, what the trace records, and what a human's edit survives.

Three things are asserted here and each is a requirement that would otherwise be
satisfied by something that looks right and is not.

**A playbook must arrive labelled as a generalisation.** The failure this
prevents is an agent citing "the cause is usually a lowered memory limit" as an
observation of the incident in front of it. So the assertions are about the
*framing* — the word synthesised, the episode count, the date range, the sentence
saying evidence from this incident wins — not merely about the content being
present.

**Synthesis must never fail a recall.** Asserted at the delivery layer rather than
only at the generator: a broken provider, a broken store, and a broken cache all
have to leave the episodes coming back.

**An operator edit must survive regeneration.** The requirement exists because of
what happens when it does not: an operator whose correction disappears learns
that correcting playbooks is wasted effort and stops, and the highest-quality
signal in the system is gone for a reason nobody records.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager

import pytest

from capabilities.tools.system.memory_search import results
from config.constants.memory import MAX_STRATEGY_KEYS_PER_RECALL
from platform.memory.embeddings.local import LocalEmbedder
from platform.memory.models import RecallQuery
from platform.memory.policy import MemoryPolicy
from platform.memory.retrieval import MemoryRetriever, RecallLedger, RecallResult
from platform.memory.strategy.models import OperatorEdit, StrategySection
from platform.memory.strategy.policy import StrategyPolicy
from platform.memory.strategy.service import StrategyDirectory, StrategyRecall, candidate_keys
from platform.persistence.errors import PersistenceError
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.health import HealthState, StoreHealth
from platform.persistence.ports.transaction import SystemUnitOfWork, UnitOfWork
from tests.unit.platform.memory.conftest import at
from tests.unit.platform.memory.strategy.conftest import (
    SYNTHESIS_REPLY,
    CountingLLM,
    cache_for,
    episode,
    key_for,
    mixed_corpus,
    scored,
    seed,
)

pytestmark = pytest.mark.unit

QUERY = RecallQuery(text="payments-api restarting with exit code 137")


class BrokenGateway:
    """A gateway that has gone away, for the degradation assertions."""

    def begin(self, scope: TenantScope) -> AbstractAsyncContextManager[UnitOfWork]:
        """Refuse to open a unit of work."""
        raise PersistenceError("the strategy table is gone")

    def begin_system(self) -> AbstractAsyncContextManager[SystemUnitOfWork]:
        """Refuse, as above."""
        raise PersistenceError("the strategy table is gone")

    async def health(self) -> StoreHealth:
        """Report the store as unreachable."""
        return StoreHealth(state=HealthState.UNAVAILABLE, reasons=("broken on purpose",))

    async def close(self) -> None:
        """Nothing to release."""


def recall_for(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    llm: CountingLLM,
    *,
    policy: StrategyPolicy | None = None,
    ledger: RecallLedger | None = None,
) -> StrategyRecall:
    """Return the enriched recall path the capability binds."""
    shared = ledger if ledger is not None else RecallLedger()
    return StrategyRecall(
        retriever=MemoryRetriever(
            gateway=gateway,
            scope=scope,
            embedder=embedder,
            policy=MemoryPolicy(),
            ledger=shared,
            clock=at,
        ),
        cache=cache_for(gateway, scope, llm, policy=policy),
        policy=policy or StrategyPolicy(),
        ledger=shared,
        clock=at,
    )


# -- playbooks arrive through the memory capability ---------------------------


async def test_a_recall_returns_the_playbook_alongside_the_episodes(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    await seed(gateway, scope, embedder, *mixed_corpus(scope))

    result = await recall_for(gateway, scope, embedder, synthesis_llm).search(QUERY)

    assert result.episodes, "the episodes are the point; the playbook is the enrichment"
    assert len(result.strategies) == 1
    assert result.strategies[0].key.component_key == "service:payments"


async def test_the_playbook_is_labelled_as_synthesised_and_carries_its_range(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    """The agent has to be able to weigh it, so it is shown what to weigh."""
    await seed(gateway, scope, embedder, *mixed_corpus(scope))
    result = await recall_for(gateway, scope, embedder, synthesis_llm).search(QUERY)

    rendered = results.render(result)

    assert "SYNTHESISED PLAYBOOK" in rendered
    assert "not an observation of this incident" in rendered
    assert "5 previous investigation(s)" in rendered
    assert at(-29.0).date().isoformat() in rendered
    assert at(-1.0).date().isoformat() in rendered
    assert "your evidence wins" in rendered
    # And the anti-patterns are labelled as what they are.
    assert "did not help" in rendered
    assert SYNTHESIS_REPLY[StrategySection.ANTI_PATTERNS.value][0] in rendered


async def test_the_structured_value_keeps_the_playbook_traceable(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    """A wrong playbook has to be diagnosable from the trace alone."""
    await seed(gateway, scope, embedder, *mixed_corpus(scope))
    result = await recall_for(gateway, scope, embedder, synthesis_llm).search(QUERY)

    shaped = results.shape(result)
    playbook = shaped["strategies"][0]

    assert shaped["strategy_count"] == 1
    assert playbook["synthesised"] is True
    assert set(playbook["anti_pattern_episode_ids"]) == {"ep-unresolved-1", "ep-unresolved-2"}
    assert len(playbook["source_episode_ids"]) == 5
    assert playbook["prompt_version"] >= 1


async def test_the_evidence_entry_says_what_the_playbook_is_not_what_it_concludes(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    """An entry reading like a finding would enter the trace as a measurement."""
    await seed(gateway, scope, embedder, *mixed_corpus(scope))
    result = await recall_for(gateway, scope, embedder, synthesis_llm).search(QUERY)

    entry = results.strategy_evidence(result.strategies)[0]

    assert "not an observation of this incident" in entry.summary
    assert entry.reference == result.strategies[0].key.label


# -- the trace records it, and whether the agent used it ----------------------


async def test_the_ledger_records_the_playbook_and_whether_it_was_used(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    await seed(gateway, scope, embedder, *mixed_corpus(scope))
    ledger = RecallLedger()
    recall = recall_for(gateway, scope, embedder, synthesis_llm, ledger=ledger)
    result = await recall.search(QUERY)
    label = result.strategies[0].key.label

    ignored = ledger.trace_summary()
    assert ignored["strategies_returned"] == 1
    assert ignored["strategies_acted_on"] == 0

    ledger.mark_acted_on(f"Following the playbook {label}, the cause was a lowered limit.")

    assert ledger.trace_summary()["strategies_acted_on"] == 1


async def test_widening_the_episode_set_is_not_recorded_as_a_recall(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    """The agent asked once; counting the system's own search would skew the ratio."""
    await seed(gateway, scope, embedder, *mixed_corpus(scope))
    ledger = RecallLedger()

    await recall_for(gateway, scope, embedder, synthesis_llm, ledger=ledger).search(QUERY)

    assert ledger.trace_summary()["recalls"] == 1


# -- failure isolation at the delivery layer ----------------------------------


@pytest.mark.parametrize(
    "llm",
    [
        pytest.param(CountingLLM(raises=RuntimeError("the provider fell over")), id="raises"),
        pytest.param(CountingLLM(structured=None), id="no-structured-reply"),
    ],
)
async def test_a_broken_synthesis_leaves_episode_recall_working(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    llm: CountingLLM,
) -> None:
    await seed(gateway, scope, embedder, *mixed_corpus(scope))

    result = await recall_for(gateway, scope, embedder, llm).search(QUERY)

    assert result.searched
    assert result.episodes
    assert result.strategies == ()
    assert results.render(result)  # and the episodes still render


async def test_a_broken_strategy_store_leaves_episode_recall_working(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    """Whatever goes wrong below the recall, the episodes come back.

    Broken by giving the cache a gateway that refuses to open a unit of work,
    which is what a store that has gone away looks like from up here. The
    retriever keeps the working gateway, because the assertion is that the
    strategy half failing does not take the episode half with it.
    """
    await seed(gateway, scope, embedder, *mixed_corpus(scope))
    recall = recall_for(gateway, scope, embedder, synthesis_llm)
    recall.cache = cache_for(BrokenGateway(), scope, synthesis_llm)

    result = await recall.search(QUERY)

    assert result.episodes
    assert result.strategies == ()


# -- the ablation baseline ----------------------------------------------------


async def test_with_strategies_disabled_the_recall_is_the_episodes_only_baseline(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    """The run is otherwise identical, which is what makes it a baseline."""
    await seed(gateway, scope, embedder, *mixed_corpus(scope))

    enabled = await recall_for(gateway, scope, embedder, synthesis_llm).search(QUERY)
    disabled = await recall_for(
        gateway, scope, embedder, synthesis_llm, policy=StrategyPolicy.disabled()
    ).search(QUERY)

    assert disabled.strategies == ()
    assert disabled.correlation_ids == enabled.correlation_ids
    assert results.render(disabled) not in ("", results.render(enabled))
    assert "SYNTHESISED PLAYBOOK" not in results.render(disabled)


async def test_an_empty_recall_asks_for_no_playbook(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    """A team with no corpus must not pay a synthesis call to be told so."""
    result = await recall_for(gateway, scope, embedder, synthesis_llm).search(QUERY)

    assert result.empty
    assert result.strategies == ()
    assert synthesis_llm.call_count == 0


def test_the_candidate_keys_are_capped(scope: TenantScope) -> None:
    """A recall touching many components must not become many synthesis calls."""
    names = ("payments", "orders", "checkout", "search", "billing", "shipping")
    sprawling = tuple(
        episode(f"ep-{name}", scope, components=(f"service:{name}", f"database:{name}"))
        for name in names
    )

    keys = candidate_keys(
        RecallResult(query=QUERY, episodes=scored(*sprawling)),
        org_id=scope.org_id,
        team_node_id=scope.team_node_id or "",
    )

    assert len(keys) == MAX_STRATEGY_KEYS_PER_RECALL
    # The best-ranked episode's subjects come first, which is what the cap keeps.
    assert [key.component_key for key in keys] == ["service:payments", "database:payments"]


# -- operator edits -----------------------------------------------------------


async def test_an_operator_edit_survives_regeneration_and_stays_attributed(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """The requirement that keeps operators correcting playbooks."""
    cache = cache_for(gateway, scope, synthesis_llm)
    directory = StrategyDirectory(gateway=gateway, scope=scope, cache=cache, clock=at)
    episodes = scored(*mixed_corpus(scope))
    key = key_for(scope)
    await cache.get_or_generate(key, episodes)

    amended = await directory.amend(
        key, OperatorEdit(author="ana", note="Check the HPA before the memory limit.")
    )
    assert amended is not None
    assert amended.operator_edits[0].edited_at == at()

    await directory.invalidate(key)
    regenerated = await cache.get_or_generate(key, episodes)

    assert regenerated.generated
    assert regenerated.strategy is not None
    notes = [edit.note for edit in regenerated.strategy.operator_edits]
    assert "Check the HPA before the memory limit." in notes
    assert regenerated.strategy.operator_edits[0].author == "ana"


async def test_an_operator_edit_reaches_the_agent_marked_as_a_human_amendment(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    synthesis_llm: CountingLLM,
) -> None:
    await seed(gateway, scope, embedder, *mixed_corpus(scope))
    recall = recall_for(gateway, scope, embedder, synthesis_llm)
    await recall.search(QUERY)

    directory = StrategyDirectory(gateway=gateway, scope=scope, cache=recall.cache, clock=at)
    await directory.amend(key_for(scope), OperatorEdit(author="ana", note="Check the HPA first."))

    rendered = results.render(await recall.search(QUERY))

    assert "Operator amendments" in rendered
    assert "authoritative over the generated sections" in rendered
    assert "Check the HPA first. — ana" in rendered


async def test_amending_a_playbook_that_does_not_exist_creates_nothing(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """An edit is a correction of something."""
    cache = cache_for(gateway, scope, synthesis_llm)
    directory = StrategyDirectory(gateway=gateway, scope=scope, cache=cache, clock=at)

    assert await directory.amend(key_for(scope), OperatorEdit(author="ana", note="x")) is None
    assert await directory.list() == ()


async def test_deleting_a_playbook_takes_its_edits_with_it(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """The difference between invalidate and delete, stated as behaviour."""
    cache = cache_for(gateway, scope, synthesis_llm)
    directory = StrategyDirectory(gateway=gateway, scope=scope, cache=cache, clock=at)
    key = key_for(scope)
    await cache.get_or_generate(key, scored(*mixed_corpus(scope)))
    await directory.amend(key, OperatorEdit(author="ana", note="Check the HPA first."))

    assert await directory.delete(key) is True
    assert await directory.get(key) is None
    assert await directory.delete(key) is False


async def test_the_console_can_list_a_teams_playbooks_without_generating(
    gateway: PersistenceGateway, scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """The read API the console is built over."""
    cache = cache_for(gateway, scope, synthesis_llm)
    directory = StrategyDirectory(gateway=gateway, scope=scope, cache=cache, clock=at)
    await cache.get_or_generate(key_for(scope, issue_type="oom_kill"), scored(*mixed_corpus(scope)))
    await cache.get_or_generate(
        key_for(scope, issue_type="disk_pressure"), scored(*mixed_corpus(scope))
    )
    calls = synthesis_llm.call_count

    listed = await directory.list()

    assert {strategy.key.issue_type for strategy in listed} == {"oom_kill", "disk_pressure"}
    assert synthesis_llm.call_count == calls


async def test_one_teams_console_lists_only_its_own_playbooks(
    gateway: PersistenceGateway,
    scope: TenantScope,
    other_team_scope: TenantScope,
    synthesis_llm: CountingLLM,
) -> None:
    mine = cache_for(gateway, scope, synthesis_llm)
    await mine.get_or_generate(key_for(scope), scored(*mixed_corpus(scope)))

    theirs = cache_for(gateway, other_team_scope, synthesis_llm)
    directory = StrategyDirectory(gateway=gateway, scope=other_team_scope, cache=theirs, clock=at)

    assert await directory.list() == ()
