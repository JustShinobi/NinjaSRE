"""Embedding models behind one three-member port.

The port is the whole export surface. ``LocalEmbedder`` is the default and needs
no network; ``ProviderEmbedder`` wraps whatever a deployment would rather use.
Both declare a model and a width, both are checked against what the index was
declared with, and swapping one for the other is a re-embedding generation
rather than a configuration change that quietly invalidates the corpus.
"""

from __future__ import annotations

from platform.memory.embeddings.generations import (
    EmbeddingGeneration,
    ensure_episode_index,
    reembed_episodes,
    verify_dimension,
)
from platform.memory.embeddings.local import LocalEmbedder, tokenise
from platform.memory.embeddings.port import Embedder, embed_one
from platform.memory.embeddings.provider import EmbeddingBackend, ProviderEmbedder

__all__ = [
    "Embedder",
    "EmbeddingBackend",
    "EmbeddingGeneration",
    "LocalEmbedder",
    "ProviderEmbedder",
    "embed_one",
    "ensure_episode_index",
    "reembed_episodes",
    "tokenise",
    "verify_dimension",
]
