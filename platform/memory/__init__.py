"""Episodic memory: what every investigation learned, and proof that it helps.

An episode is one investigation conversation reduced to what a later one would
want to know — what broke, on what, which capabilities helped, what the cause
turned out to be, and how well the run went. Features 011 and 028 read this
corpus; this package writes it and searches it.

Three decisions shape everything here, and each one is a decision to give
something up.

**Recall is agent-driven, never pre-injected.** Nothing about a past incident
enters the opening prompt. The agent is told memory exists and told to search it
once it holds concrete evidence, and it costs an extra capability call per
investigation. What that buys is not anchoring on an episode that shares
vocabulary with a vague alert and nothing else, which is the failure mode of the
obvious alternative and is expensive in a way the extra call is not.

**Effectiveness and ranking are documented formulas, not heuristics.** Both feed
decisions that change agent behaviour, both carry a version, and the version is
stored on every record they produce. A weight change is therefore visible in the
corpus rather than a silent reinterpretation of it.

**Every mechanism has an ablation switch.** Article VII forbids claiming learning
that has not been measured, and reading and writing switch separately so the
interesting experiment — a populated corpus the agent may not consult — is one
the harness can actually run.

Hold a ``MemoryService``. It wires the guidance hook, the finalisation hook, and
the retriever from one policy and one tenant scope, which is what stops the three
disagreeing about which team's corpus they are working on.
"""

from __future__ import annotations

from platform.memory.effectiveness import (
    EffectivenessInputs,
    effectiveness,
    evidence_backing_ratio,
    trajectory_efficiency,
)
from platform.memory.embeddings import (
    Embedder,
    EmbeddingBackend,
    LocalEmbedder,
    ProviderEmbedder,
    ensure_episode_index,
    reembed_episodes,
)
from platform.memory.extraction import (
    EpisodeExtraction,
    EpisodeExtractor,
    ExtractionOutcome,
    capability_sequence,
)
from platform.memory.guidance import MemoryGuidance
from platform.memory.lifecycle import FinalisationOutcome, MemoryLifecycle
from platform.memory.models import (
    Component,
    EpisodeSeverity,
    KeyFinding,
    MemoryEpisode,
    RecallQuery,
    ScoredEpisode,
)
from platform.memory.policy import (
    MEMORY_READ_SWITCH,
    MEMORY_SWITCHES,
    MEMORY_WRITE_SWITCH,
    MemoryPolicy,
)
from platform.memory.purge import PurgeReport, purge_episodes, purge_expired
from platform.memory.ranking import component_overlap, rank, recency, score_episode
from platform.memory.retrieval import (
    MemoryRetriever,
    RecallLedger,
    RecallRecord,
    RecallResult,
)
from platform.memory.service import MemoryService

__all__ = [
    "MEMORY_READ_SWITCH",
    "MEMORY_SWITCHES",
    "MEMORY_WRITE_SWITCH",
    "Component",
    "EffectivenessInputs",
    "Embedder",
    "EmbeddingBackend",
    "EpisodeExtraction",
    "EpisodeExtractor",
    "EpisodeSeverity",
    "ExtractionOutcome",
    "FinalisationOutcome",
    "KeyFinding",
    "LocalEmbedder",
    "MemoryEpisode",
    "MemoryGuidance",
    "MemoryLifecycle",
    "MemoryPolicy",
    "MemoryRetriever",
    "MemoryService",
    "ProviderEmbedder",
    "PurgeReport",
    "RecallLedger",
    "RecallQuery",
    "RecallRecord",
    "RecallResult",
    "ScoredEpisode",
    "capability_sequence",
    "component_overlap",
    "effectiveness",
    "ensure_episode_index",
    "evidence_backing_ratio",
    "purge_episodes",
    "purge_expired",
    "rank",
    "recency",
    "reembed_episodes",
    "score_episode",
    "trajectory_efficiency",
]
