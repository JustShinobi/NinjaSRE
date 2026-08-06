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
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from config.prompts.memory import (
    MEMORY_RECALL_EMPTY,
    MEMORY_RECALL_EPISODE,
    MEMORY_RECALL_HEADER,
)
from core.capability.metadata import EvidenceSource, EvidenceType
from core.capability.result import Evidence
from platform.memory.models import ScoredEpisode
from platform.memory.retrieval import RecallResult

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


def render(result: RecallResult) -> str:
    """Return the whole recall as one block of text, empty results included."""
    if result.empty:
        return MEMORY_RECALL_EMPTY
    return "\n\n".join(
        (
            MEMORY_RECALL_HEADER.format(count=len(result.episodes)),
            *(
                describe(found, rank=position)
                for position, found in enumerate(result.episodes, start=1)
            ),
        )
    )


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
        "text": render(result),
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
    "evidence_for",
    "render",
    "shape",
]
