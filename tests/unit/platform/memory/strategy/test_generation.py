"""Where the anti-patterns came from, and what happens when synthesis breaks.

**Attribution** is the feature's central claim and the one most easily faked. A
playbook that merely *contains* an anti-patterns section proves nothing — the
question is whether that section was entitled to the episodes it generalises. So
the fixture is mixed on purpose (three runs that found the cause, two that did
not) and the assertions are about attribution: the unresolved ids are recorded as
the anti-patterns' source, the resolved ones are not, and the prompt the model
actually received presented the two halves separately.

**Failure isolation** is asserted three ways, because synthesis can break in three
places — the provider raising, the provider returning nothing usable, and the
reply being structurally fine but empty. All three have to come back as a value.
"""

from __future__ import annotations

import pytest

from config.constants.memory import (
    MAX_STRATEGY_SECTION_ITEMS,
    MIN_EPISODES_FOR_STRATEGY,
    STRATEGY_MAX_INPUT_EPISODES,
    STRATEGY_MAX_OUTPUT_TOKENS,
)
from config.prompts.strategy import (
    STRATEGY_NO_UNRESOLVED_EPISODES,
    STRATEGY_PROMPT_VERSION,
)
from platform.guardrails.engine import GuardrailEngine
from platform.memory.strategy.generator import StrategyGenerator, split_by_outcome
from platform.memory.strategy.models import StrategySection
from platform.persistence.ports import TenantScope
from tests.unit.platform.memory.conftest import at
from tests.unit.platform.memory.strategy.conftest import (
    SYNTHESIS_REPLY,
    CountingLLM,
    episode,
    key_for,
    mixed_corpus,
    scored,
)

pytestmark = pytest.mark.unit


def generator(llm: CountingLLM, *, engine: GuardrailEngine | None = None) -> StrategyGenerator:
    """Return a generator with a fixed clock."""
    return StrategyGenerator(llm=llm, engine=engine, clock=at)


# -- anti-patterns, and where they came from -----------------------------------


async def test_the_anti_patterns_are_attributed_to_the_unresolved_episodes(
    scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """The playbook records which runs its anti-patterns were entitled to come from."""
    outcome = await generator(synthesis_llm).generate(key_for(scope), scored(*mixed_corpus(scope)))

    strategy = outcome.strategy
    assert strategy is not None
    assert strategy.anti_patterns  # the section exists at all
    assert set(strategy.anti_pattern_episode_ids) == {"ep-unresolved-1", "ep-unresolved-2"}
    # And the runs that established a cause are not among them, which is the half
    # of the claim that a section labelled "anti-patterns" would otherwise pass.
    assert not set(strategy.anti_pattern_episode_ids) & {
        "ep-resolved-1",
        "ep-resolved-2",
        "ep-resolved-3",
    }
    assert set(strategy.source_episode_ids) == {item.correlation_id for item in mixed_corpus(scope)}


async def test_the_prompt_presents_the_two_halves_separately(
    scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """Attribution is only checkable because the model was told which runs failed."""
    await generator(synthesis_llm).generate(key_for(scope), scored(*mixed_corpus(scope)))

    sent = synthesis_llm.calls[0].messages[0].text
    resolved_block, _, unresolved_block = sent.partition("did not establish a root cause")

    assert "ep-resolved-1" in resolved_block
    assert "ep-unresolved-1" in unresolved_block
    assert "ep-resolved-1" not in unresolved_block


async def test_a_set_that_all_resolved_is_told_to_leave_the_section_empty(
    scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """An empty half is a fact, not an omission, and the prompt says which."""
    resolved_only = scored(episode("ep-1", scope), episode("ep-2", scope), episode("ep-3", scope))

    outcome = await generator(synthesis_llm).generate(key_for(scope), resolved_only)

    assert STRATEGY_NO_UNRESOLVED_EPISODES in synthesis_llm.calls[0].messages[0].text
    assert outcome.strategy is not None
    assert outcome.strategy.anti_pattern_episode_ids == ()


async def test_a_resolved_but_ineffective_run_counts_as_a_dead_end(scope: TenantScope) -> None:
    """Unresolved is not the only kind of dead end; low-effectiveness counts too."""
    slog = episode("ep-slog", scope, resolved=True, effectiveness=0.1)
    resolved, unresolved = split_by_outcome(scored(episode("ep-good", scope), slog))

    assert [found.correlation_id for found in resolved] == ["ep-good"]
    assert [found.correlation_id for found in unresolved] == ["ep-slog"]


# -- the threshold -------------------------------------------------------------


async def test_below_the_threshold_nothing_is_generated_and_the_reason_is_recorded(
    scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """A young corpus must look young rather than broken."""
    too_few = scored(*mixed_corpus(scope)[: MIN_EPISODES_FOR_STRATEGY - 1])

    outcome = await generator(synthesis_llm).generate(key_for(scope), too_few)

    assert outcome.strategy is None
    assert outcome.skipped
    assert str(MIN_EPISODES_FOR_STRATEGY) in outcome.reason
    assert "oom_kill" in outcome.reason
    assert synthesis_llm.call_count == 0


# -- bounds --------------------------------------------------------------------


async def test_the_input_set_is_bounded_and_takes_the_best_ranked(
    scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """Cost is bounded by a named constant, and the cut is at the tail."""
    many = scored(
        *(episode(f"ep-{index}", scope) for index in range(STRATEGY_MAX_INPUT_EPISODES + 5))
    )

    outcome = await generator(synthesis_llm).generate(key_for(scope), many)

    assert outcome.strategy is not None
    assert outcome.strategy.episode_count == STRATEGY_MAX_INPUT_EPISODES
    assert "ep-0" in outcome.strategy.source_episode_ids
    assert f"ep-{STRATEGY_MAX_INPUT_EPISODES + 4}" not in outcome.strategy.source_episode_ids


async def test_the_reply_is_bounded_in_length_and_in_items(
    scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """A playbook that does not fit in context is one the agent never finishes."""
    await generator(synthesis_llm).generate(key_for(scope), scored(*mixed_corpus(scope)))
    assert synthesis_llm.calls[0].max_output_tokens == STRATEGY_MAX_OUTPUT_TOKENS

    verbose = dict(SYNTHESIS_REPLY)
    verbose[StrategySection.ROOT_CAUSES.value] = [
        f"cause number {index}" for index in range(MAX_STRATEGY_SECTION_ITEMS + 10)
    ]
    outcome = await generator(CountingLLM(structured=verbose)).generate(
        key_for(scope), scored(*mixed_corpus(scope))
    )

    assert outcome.strategy is not None
    assert len(outcome.strategy.root_causes) == MAX_STRATEGY_SECTION_ITEMS


async def test_the_playbook_records_the_prompt_version_and_its_date_range(
    scope: TenantScope, synthesis_llm: CountingLLM
) -> None:
    """What it was generated by, and what it generalises over."""
    outcome = await generator(synthesis_llm).generate(key_for(scope), scored(*mixed_corpus(scope)))

    strategy = outcome.strategy
    assert strategy is not None
    assert strategy.prompt_version == STRATEGY_PROMPT_VERSION
    assert strategy.episode_count == 5
    assert strategy.generated_at == at()
    assert strategy.earliest_episode_at == at(-29.0)
    assert strategy.latest_episode_at == at(-1.0)


# -- failure isolation ---------------------------------------------------------


@pytest.mark.parametrize(
    "llm",
    [
        pytest.param(CountingLLM(raises=RuntimeError("the provider fell over")), id="raises"),
        pytest.param(CountingLLM(structured=None), id="no-structured-reply"),
        pytest.param(
            CountingLLM(structured={section.value: [] for section in StrategySection}),
            id="every-section-empty",
        ),
    ],
)
async def test_a_broken_synthesis_comes_back_as_a_value(
    scope: TenantScope, llm: CountingLLM
) -> None:
    """Nothing here may raise into the recall that asked for it."""
    outcome = await generator(llm).generate(key_for(scope), scored(*mixed_corpus(scope)))

    assert outcome.strategy is None
    assert not outcome.skipped  # broken is not the same fact as "too few episodes"
    assert outcome.reason


# -- content passes the guardrails before it can be persisted -----------------


async def test_a_secret_in_a_generated_section_is_redacted_and_recorded(
    scope: TenantScope, engine: GuardrailEngine
) -> None:
    """A playbook is written to the database, so it is scanned like an episode is."""
    leaky = dict(SYNTHESIS_REPLY)
    leaky[StrategySection.CAPABILITIES.value] = [
        "read_logs with AKIAIOSFODNN7EXAMPLE in the query",
    ]

    outcome = await generator(CountingLLM(structured=leaky), engine=engine).generate(
        key_for(scope), scored(*mixed_corpus(scope))
    )

    strategy = outcome.strategy
    assert strategy is not None
    rendered = " ".join(strategy.capabilities)
    assert "AKIAIOSFODNN7EXAMPLE" not in rendered
    assert strategy.guardrail_rules_fired
