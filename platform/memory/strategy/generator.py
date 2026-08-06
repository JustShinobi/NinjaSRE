"""One structured call over a scored episode set, that can never fail a recall.

Three properties, in the order they matter.

**Nothing here raises into an investigation.** A provider outage, a malformed
reply, a guardrail that threw — all of it comes back as a ``SynthesisOutcome``
carrying the reason. A playbook is an enrichment of a recall that has already
succeeded, and letting synthesis turn a working recall into a failed one would
trade the feature for the enrichment. The suite asserts it; the broad catch is how
it is true.

**The threshold is enforced here, with the reason recorded.** Below
``MIN_EPISODES_FOR_STRATEGY`` no call is made and the outcome says how many were
found and how many were needed. A deployment whose corpus is still young should
look young, not broken, and the difference is whether anything says so.

**The input set is bounded and ordered.** The top ``STRATEGY_MAX_INPUT_EPISODES``
by rank, split into the runs that established a cause and the runs that did not.
The split is what makes the attribution verifiable: the anti-pattern episode ids
are known before the call, so the playbook records where that section was entitled
to come from.

Content is scanned before it is returned. A playbook is written to the database
and read into a later prompt, and a secret carried through synthesis would be one
in every backup and every future context window from then on.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from config.constants.memory import MIN_EPISODES_FOR_STRATEGY, STRATEGY_MAX_INPUT_EPISODES
from config.prompts.strategy import STRATEGY_BELOW_THRESHOLD, STRATEGY_SYNTHESIS_FAILED
from core.llm.types import LLMClient
from core.llm.usage import UsageRecord
from platform.guardrails.engine import GuardrailEngine
from platform.memory.models import ScoredEpisode
from platform.memory.models import now as _utc_now
from platform.memory.strategy.models import (
    Strategy,
    StrategyKey,
    StrategySection,
    SynthesisInput,
)
from platform.memory.strategy.prompt import (
    STRATEGY_SYNTHESIS_SCHEMA,
    prompt_version,
    synthesis_request,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Effectiveness at or below which a resolved episode is treated as a dead end
#: for the purpose of the anti-patterns section. Unresolved is not the only kind
#: of dead end: a run that reached a cause after fifteen iterations of reading the
#: wrong thing has as much to say about what does not work as one that reached no
#: cause at all.
LOW_EFFECTIVENESS_CEILING = 0.35


def split_by_outcome(
    episodes: Sequence[ScoredEpisode],
) -> tuple[
    tuple[ScoredEpisode, ...],
    tuple[ScoredEpisode, ...],
]:
    """Return ``episodes`` split into the runs that worked and the runs that did not."""

    def worked(found: ScoredEpisode) -> bool:
        return (
            found.episode.resolved and found.episode.effectiveness_score > LOW_EFFECTIVENESS_CEILING
        )

    return (
        tuple(found for found in episodes if worked(found)),
        tuple(found for found in episodes if not worked(found)),
    )


def synthesis_input(key: StrategyKey, episodes: Sequence[ScoredEpisode]) -> SynthesisInput:
    """Return the bounded, split episode set one generation is drawn from.

    Bounded before splitting, on rank, so the cut takes the least relevant
    episodes rather than an arbitrary share of one half. A set truncated per-half
    would silently change the ratio the model reads and therefore how confident
    the playbook sounds.
    """
    resolved, unresolved = split_by_outcome(tuple(episodes)[:STRATEGY_MAX_INPUT_EPISODES])
    return SynthesisInput(key=key, resolved=resolved, unresolved=unresolved)


def below_threshold(key: StrategyKey, found: int) -> str:
    """Return the sentence recorded when the corpus is too small to generalise."""
    return STRATEGY_BELOW_THRESHOLD.format(
        found=found,
        issue_type=key.issue_type,
        component_key=key.component_key,
        minimum=MIN_EPISODES_FOR_STRATEGY,
    )


@dataclass(frozen=True, slots=True)
class SynthesisOutcome:
    """What one generation produced, including when it produced nothing.

    ``skipped`` and a failure are kept apart. One is a decision the system made
    on purpose — too few episodes — and the other is something being broken, and
    a deployment where every key is "skipped" is healthy while one where every
    key "failed" is not.
    """

    strategy: Strategy | None = None
    skipped: bool = False
    reason: str = ""
    usage: UsageRecord | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether a playbook can be persisted from this outcome."""
        return self.strategy is not None


@dataclass(slots=True)
class StrategyGenerator:
    """The single synthesis call, with every failure turned into a value."""

    llm: LLMClient
    engine: GuardrailEngine | None = None
    clock: Callable[[], datetime] = _utc_now
    calls: int = field(default=0, init=False)

    async def generate(
        self,
        key: StrategyKey,
        episodes: Sequence[ScoredEpisode],
    ) -> SynthesisOutcome:
        """Return the playbook these episodes support, or why there is none.

        Never raises. The broad catch is deliberate and is the same contract
        episode extraction holds: a provider client that grew a new exception
        type must not be able to fail a recall that already returned its
        episodes.
        """
        if len(episodes) < MIN_EPISODES_FOR_STRATEGY:
            reason = below_threshold(key, len(episodes))
            logger.info(
                "strategy.below_threshold",
                team=key.team_node_id,
                issue_type=key.issue_type,
                component=key.component_key,
                found=len(episodes),
                minimum=MIN_EPISODES_FOR_STRATEGY,
            )
            return SynthesisOutcome(skipped=True, reason=reason)

        inputs = synthesis_input(key, episodes)
        self.calls += 1
        try:
            result = await self.llm.invoke_structured(
                synthesis_request(inputs), STRATEGY_SYNTHESIS_SCHEMA
            )
        except Exception as error:  # noqa: BLE001 — synthesis must never fail a recall
            return self._failed(key, f"{type(error).__name__}: {error}")

        if not result.succeeded or result.structured is None:
            failure = result.failure_message or (
                result.failure.value if result.failure else "no structured object returned"
            )
            return self._failed(key, failure, usage=result.usage)

        strategy = self._build(inputs, result.structured)
        if not strategy.usable:
            return self._failed(
                key, "the structured reply carried no content in any section", usage=result.usage
            )

        logger.info(
            "strategy.generated",
            team=key.team_node_id,
            issue_type=key.issue_type,
            component=key.component_key,
            episodes=inputs.count,
            anti_patterns=len(strategy.anti_patterns),
        )
        return SynthesisOutcome(strategy=strategy, usage=result.usage)

    # -- building --------------------------------------------------------------

    def _build(self, inputs: SynthesisInput, document: Mapping[str, Any]) -> Strategy:
        """Return the playbook a structured reply describes, scanned and attributed."""
        earliest, latest = inputs.range()
        strategy = Strategy(
            key=inputs.key,
            root_causes=_items(document.get(StrategySection.ROOT_CAUSES.value)),
            investigation_steps=_items(document.get(StrategySection.INVESTIGATION_STEPS.value)),
            capabilities=_items(document.get(StrategySection.CAPABILITIES.value)),
            anti_patterns=_items(document.get(StrategySection.ANTI_PATTERNS.value)),
            source_episode_ids=inputs.source_episode_ids,
            anti_pattern_episode_ids=inputs.anti_pattern_episode_ids,
            episode_count=inputs.count,
            earliest_episode_at=earliest,
            latest_episode_at=latest,
            generated_at=self.clock(),
            prompt_version=prompt_version(),
        )
        return self._scan(strategy)

    def _scan(self, strategy: Strategy) -> Strategy:
        """Return ``strategy`` with every section redacted, and the rules recorded.

        Redacts rather than refuses, for the reason the episode writer does: the
        investigations already happened, dropping the playbook would lose the
        learning, and the secret has already been removed from the text. Which
        rules fired is stored on the playbook, so a corpus can be audited without
        anybody reading it.
        """
        engine = self.engine
        if engine is None:
            return strategy

        fired: dict[str, None] = {}

        def clean(items: tuple[str, ...]) -> tuple[str, ...]:
            scanned: list[str] = []
            for item in items:
                result = engine.scan(item)
                for rule in result.rules_fired:
                    fired.setdefault(rule, None)
                scanned.append(result.text)
            return tuple(scanned)

        return replace(
            strategy,
            root_causes=clean(strategy.root_causes),
            investigation_steps=clean(strategy.investigation_steps),
            capabilities=clean(strategy.capabilities),
            anti_patterns=clean(strategy.anti_patterns),
            guardrail_rules_fired=tuple(fired),
        )

    def _failed(
        self,
        key: StrategyKey,
        failure: str,
        *,
        usage: UsageRecord | None = None,
    ) -> SynthesisOutcome:
        """Return the outcome a broken synthesis produces, having said so."""
        logger.warning(
            "strategy.synthesis_failed",
            team=key.team_node_id,
            issue_type=key.issue_type,
            component=key.component_key,
            failure=failure,
        )
        return SynthesisOutcome(
            reason=STRATEGY_SYNTHESIS_FAILED.format(failure=failure), usage=usage
        )


def _items(value: Any) -> tuple[str, ...]:
    """Return one section of a reply as text, dropping anything unusable.

    A model that returned a string where a list was asked for should cost that
    section, not the playbook.
    """
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if isinstance(item, str) and item.strip())


__all__ = [
    "LOW_EFFECTIVENESS_CEILING",
    "StrategyGenerator",
    "SynthesisOutcome",
    "below_threshold",
    "split_by_outcome",
    "synthesis_input",
]
