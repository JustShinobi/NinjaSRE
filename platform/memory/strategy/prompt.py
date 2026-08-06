"""Building the one synthesis call: what the model is shown, and what it must return.

The text lives in ``config.prompts.strategy``; this module decides what goes into
it and what shape comes back.

The decision worth reading is the split. The resolved and unresolved episodes are
rendered into two separate blocks and the request names which is which, rather
than handing the model one list and asking it to work it out. The anti-patterns
section has to come from the runs that failed, and a model given a mixed list will
draw cautions from the runs that succeeded — producing a section
that reads exactly like a finding and is not one. Splitting the input is what
makes the requirement checkable rather than hoped for: the unresolved episode ids
are known here, so the playbook's claim about where its anti-patterns came from
can be verified against them afterwards.

The schema asks for four arrays of short strings and nothing else. No prose
field, no confidence, no free-form notes — every one of those becomes the section
a model writes its hedging into, and a playbook is read under time pressure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from config.constants.memory import (
    MAX_STRATEGY_ITEM_CHARS,
    MAX_STRATEGY_SECTION_ITEMS,
    STRATEGY_MAX_OUTPUT_TOKENS,
)
from config.prompts.strategy import (
    STRATEGY_NO_RESOLVED_EPISODES,
    STRATEGY_NO_UNRESOLVED_EPISODES,
    STRATEGY_PROMPT_VERSION,
    STRATEGY_SYNTHESIS_EPISODE,
    STRATEGY_SYNTHESIS_REQUEST,
    STRATEGY_SYNTHESIS_SYSTEM_PROMPT,
)
from core.llm.types import InvokeRequest, Message, Role
from platform.memory.models import ScoredEpisode
from platform.memory.strategy.models import StrategySection, SynthesisInput


def _section_schema(description: str) -> Mapping[str, Any]:
    """Return the schema for one playbook section."""
    return {
        "type": "array",
        "maxItems": MAX_STRATEGY_SECTION_ITEMS,
        "items": {"type": "string", "maxLength": MAX_STRATEGY_ITEM_CHARS},
        "description": description,
    }


#: What the model is asked to return. Every section is optional: a set of
#: episodes that all resolved has no anti-patterns, and a schema that made the
#: field required would get an invented one rather than an empty list.
STRATEGY_SYNTHESIS_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        StrategySection.ROOT_CAUSES.value: _section_schema(
            "Causes that recur across these investigations, each naming how many "
            "runs support it. Not causes that appeared once."
        ),
        StrategySection.INVESTIGATION_STEPS.value: _section_schema(
            "An ordered sequence, most effective first, based on what produced "
            "findings in these runs."
        ),
        StrategySection.CAPABILITIES.value: _section_schema(
            "The capabilities and queries that produced the findings, named as the runs named them."
        ),
        StrategySection.ANTI_PATTERNS.value: _section_schema(
            "Approaches that looked promising and did not help. Drawn only from the "
            "investigations that did not establish a root cause."
        ),
    },
    "required": [],
}


def describe_episode(found: ScoredEpisode) -> str:
    """Return one episode as the synthesis call is shown it.

    The correlation id leads, so the model can attribute a claim to a run and so
    a reviewer holding the playbook can find the investigation behind any line of
    it. Key findings are deliberately absent: they are long, vendor-shaped, and
    full of identifiers, and a playbook that reproduced them would be describing
    one incident's hostnames as though they were a pattern.
    """
    episode = found.episode
    return STRATEGY_SYNTHESIS_EPISODE.format(
        episode_id=episode.correlation_id,
        occurred=episode.occurred_at.isoformat() if episode.occurred_at else "time not recorded",
        issue_description=episode.issue_description or episode.title or "not recorded",
        root_cause=episode.root_cause or "none established",
        capabilities=", ".join(episode.capabilities_used) or "none recorded",
        effectiveness=f"{episode.effectiveness_score:.2f}",
        summary=episode.summary or "no summary recorded",
    )


def describe_set(episodes: Sequence[ScoredEpisode], *, empty: str) -> str:
    """Return one half of the input set, or the sentence standing in for it."""
    if not episodes:
        return empty
    return "\n".join(describe_episode(found) for found in episodes)


def synthesis_request(inputs: SynthesisInput) -> InvokeRequest:
    """Return the single call that produces one playbook."""
    return InvokeRequest(
        messages=(
            Message(
                role=Role.USER,
                text=STRATEGY_SYNTHESIS_REQUEST.format(
                    issue_type=inputs.key.issue_type,
                    component_key=inputs.key.component_key,
                    count=inputs.count,
                    resolved=len(inputs.resolved),
                    unresolved=len(inputs.unresolved),
                    resolved_episodes=describe_set(
                        inputs.resolved, empty=STRATEGY_NO_RESOLVED_EPISODES
                    ),
                    unresolved_episodes=describe_set(
                        inputs.unresolved, empty=STRATEGY_NO_UNRESOLVED_EPISODES
                    ),
                ),
            ),
        ),
        system=STRATEGY_SYNTHESIS_SYSTEM_PROMPT,
        max_output_tokens=STRATEGY_MAX_OUTPUT_TOKENS,
        response_schema=STRATEGY_SYNTHESIS_SCHEMA,
    )


def prompt_version() -> int:
    """Return the version stored on every playbook this prompt produces."""
    return STRATEGY_PROMPT_VERSION


__all__ = [
    "STRATEGY_SYNTHESIS_SCHEMA",
    "describe_episode",
    "describe_set",
    "prompt_version",
    "synthesis_request",
]
