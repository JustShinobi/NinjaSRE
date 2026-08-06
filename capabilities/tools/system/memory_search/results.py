"""Turning ranked episodes into something the model can act on in one read.

Two things are in the shaped result that a naive rendering would leave out, and
both are the point of having memory at all.

**The capability sequence.** An episode records which capabilities the successful
investigation actually called, in order. A model that can see "this was found by
describing the workload, then reading the container's last-state, then checking
the deploy history" can follow that trajectory instead of rediscovering it, and
rediscovery is the expensive half of an investigation.

**What ``resolved`` means, on every line.** The flag says a root cause was
established with evidence — not that production was fixed. Writing that out
beside each episode is verbose, and it is cheaper than an agent concluding "this
was already fixed last month" from a corpus that never claimed anything of the
kind.

The evidence returned is the episode itself, not its findings. A recalled episode
is a *lead*: the claim it supports is "an investigation six weeks ago concluded
this", and the reference points at the episode so a reader can go and check. A
finding lifted out of a past run and presented as an observation of this one
would be a fabricated citation, which is the exact thing Article I exists to make
impossible.

A synthesised playbook is a lead of a weaker kind again, and it is labelled to
say so. It is a *generalisation over* previous investigations, not an observation
of any of them — so its heading says which failure and which component it
generalises, how many runs it was drawn from, and the span of time they cover,
and it says outright that evidence from this incident wins where the two
disagree. All three of those are the difference between an agent weighing a
playbook and an agent obeying one.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from config.prompts.memory import (
    MEMORY_RECALL_EMPTY,
    MEMORY_RECALL_EPISODE,
    MEMORY_RECALL_HEADER,
)
from config.prompts.strategy import (
    STRATEGY_RECALL_HEADER,
    STRATEGY_RECALL_OPERATOR_EDITS,
    STRATEGY_RECALL_SECTION,
    STRATEGY_SECTION_TITLES,
)
from core.capability.metadata import EvidenceSource, EvidenceType
from core.capability.result import Evidence
from platform.memory.models import ScoredEpisode
from platform.memory.retrieval import RecallResult
from platform.memory.strategy.models import Strategy

#: What one recalled episode's outcome reads as. Spelled out rather than
#: ``True``/``False``, because the flag's meaning is not what the word "resolved"
#: suggests on its own.
OUTCOME_RESOLVED = "root cause established, with evidence"
OUTCOME_UNRESOLVED = "no root cause established"

#: Prefixes the reference on a recalled episode, so a reader can tell a memory
#: citation from an observation made during this investigation.
EPISODE_REFERENCE_PREFIX = "episode"


def describe(found: ScoredEpisode, *, rank: int) -> str:
    """Return one recalled episode as the model is shown it."""
    episode = found.episode
    return MEMORY_RECALL_EPISODE.format(
        rank=rank,
        outcome=OUTCOME_RESOLVED if episode.resolved else OUTCOME_UNRESOLVED,
        issue_type=episode.issue_type or "unclassified",
        issue_description=episode.issue_description or episode.title or "not recorded",
        occurred=episode.occurred_at.isoformat() if episode.occurred_at else "not recorded",
        components=", ".join(episode.component_labels) or "none recorded",
        root_cause=episode.root_cause or "none established",
        capabilities=", ".join(episode.capabilities_used) or "none recorded",
        summary=episode.summary or "no summary recorded",
    )


def describe_strategy(strategy: Strategy) -> str:
    """Return one synthesised playbook as the model is shown it.

    Empty sections are omitted rather than printed as headings with nothing under
    them. A set of episodes that all resolved has no anti-patterns, and an empty
    "Anti-patterns" heading reads as an assertion that none exist rather than as
    the absence of an answer.
    """
    lines = [
        STRATEGY_RECALL_HEADER.format(
            label=strategy.key.label,
            count=strategy.episode_count,
            issue_type=strategy.key.issue_type,
            component_key=strategy.key.component_key,
            earliest=_when(strategy.earliest_episode_at),
            latest=_when(strategy.latest_episode_at),
        )
    ]
    for section, items in strategy.sections().items():
        if items:
            lines.append(
                STRATEGY_RECALL_SECTION.format(
                    title=STRATEGY_SECTION_TITLES[section.value], items=_bullets(items)
                )
            )
    if strategy.operator_edits:
        lines.append(
            STRATEGY_RECALL_OPERATOR_EDITS.format(
                items=_bullets(
                    tuple(f"{edit.note} — {edit.author}" for edit in strategy.operator_edits)
                )
            )
        )
    return "\n".join(lines)


def render(result: RecallResult) -> str:
    """Return the whole recall as one block of text, empty results included.

    Episodes first, playbooks after. The order is the argument the guidance makes
    in prose: a precedent is checked against what has actually been observed, and
    a generalisation over precedents is checked against both. Leading with the
    playbook would put the most confident and least specific thing in the model's
    context first.
    """
    if result.empty:
        return MEMORY_RECALL_EMPTY
    return "\n\n".join(
        (
            MEMORY_RECALL_HEADER.format(count=len(result.episodes)),
            *(
                describe(found, rank=position)
                for position, found in enumerate(result.episodes, start=1)
            ),
            *(describe_strategy(strategy) for strategy in result.strategies),
        )
    )


def _bullets(items: tuple[str, ...]) -> str:
    """Return ``items`` as an indented list under a section heading."""
    return "\n".join(f"    - {item}" for item in items)


def _when(moment: datetime | None) -> str:
    """Return a date as the playbook's range shows it."""
    return moment.date().isoformat() if moment else "not recorded"


def _iso(moment: datetime | None) -> str | None:
    """Return an instant as the structured value carries it."""
    return moment.isoformat() if moment else None


def evidence_for(episodes: Sequence[ScoredEpisode]) -> tuple[Evidence, ...]:
    """Return one evidence entry per recalled episode, referencing the episode."""
    return tuple(
        Evidence(
            source=EvidenceSource.MEMORY,
            evidence_type=EvidenceType.INCIDENT,
            summary=(
                f"A previous investigation of "
                f"{found.episode.issue_type or 'a similar failure'} "
                f"{'established' if found.episode.resolved else 'did not establish'} "
                f"a root cause: {found.episode.root_cause or 'none recorded'}"
            ),
            reference=f"{EPISODE_REFERENCE_PREFIX}:{found.correlation_id}",
        )
        for found in episodes
    )


def strategy_evidence(strategies: Sequence[Strategy]) -> tuple[Evidence, ...]:
    """Return one evidence entry per playbook, referencing the playbook.

    The summary says what the thing is — a generalisation over N investigations —
    rather than what it concludes. An evidence entry that read "the cause is
    usually a lowered memory limit" would enter the trace as an observation, and
    a diagnosis citing it would be citing a summary of other incidents as though
    it were a measurement of this one.
    """
    return tuple(
        Evidence(
            source=EvidenceSource.MEMORY,
            evidence_type=EvidenceType.INCIDENT,
            summary=(
                f"A playbook synthesised from {strategy.episode_count} previous "
                f"investigation(s) of {strategy.key.issue_type} on "
                f"{strategy.key.component_key}. It generalises over those runs and is "
                f"not an observation of this incident."
            ),
            reference=strategy.key.label,
        )
        for strategy in strategies
    )


def shape_strategy(strategy: Strategy) -> dict[str, Any]:
    """Return one playbook as the trace, the console, and the harness read it."""
    return {
        "label": strategy.key.label,
        "issue_type": strategy.key.issue_type,
        "component_key": strategy.key.component_key,
        "synthesised": True,
        **{section.value: list(items) for section, items in strategy.sections().items()},
        "episode_count": strategy.episode_count,
        "source_episode_ids": list(strategy.source_episode_ids),
        "anti_pattern_episode_ids": list(strategy.anti_pattern_episode_ids),
        "earliest_episode_at": _iso(strategy.earliest_episode_at),
        "latest_episode_at": _iso(strategy.latest_episode_at),
        "generated_at": _iso(strategy.generated_at),
        "prompt_version": strategy.prompt_version,
        "stale": strategy.stale,
        "operator_edits": [edit.to_record() for edit in strategy.operator_edits],
    }


def shape(result: RecallResult) -> dict[str, Any]:
    """Return the structured value the tool hands back.

    Both a rendered block and the structured episodes. The text is what the model
    reads; the structure is what the trace, the console, and the evaluation
    harness read, and deriving one from the other afterwards is how the two come
    to disagree.
    """
    return {
        "query": result.query.text,
        "component": result.query.component,
        "issue_type": result.query.issue_type,
        "count": len(result.episodes),
        "strategy_count": len(result.strategies),
        "text": render(result),
        "strategies": [shape_strategy(strategy) for strategy in result.strategies],
        "episodes": [
            {
                "correlation_id": found.correlation_id,
                "issue_type": found.episode.issue_type,
                "issue_description": found.episode.issue_description,
                "resolved": found.episode.resolved,
                "resolved_means": OUTCOME_RESOLVED,
                "root_cause": found.episode.root_cause,
                "summary": found.episode.summary,
                "components": list(found.episode.component_labels),
                "capabilities_used": list(found.episode.capabilities_used),
                "effectiveness_score": found.episode.effectiveness_score,
                "occurred_at": (
                    found.episode.occurred_at.isoformat() if found.episode.occurred_at else None
                ),
                "score": found.score,
                "ranking_terms": found.terms(),
            }
            for found in result.episodes
        ],
    }


__all__ = [
    "EPISODE_REFERENCE_PREFIX",
    "OUTCOME_RESOLVED",
    "OUTCOME_UNRESOLVED",
    "describe",
    "describe_strategy",
    "evidence_for",
    "render",
    "shape",
    "shape_strategy",
    "strategy_evidence",
]
