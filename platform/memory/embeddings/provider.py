"""A hosted embedding model behind the same port, with the width checked here.

The backend is injected rather than imported. There is no vendor SDK in this
module and there will not be one: an operator who wants OpenAI's embeddings, a
self-hosted TEI server, or a model behind their own gateway writes the four
lines that call it and hands the result over. That keeps the no-egress
deployment free of an optional dependency it would never install, and it keeps
this package from growing a provider registry that duplicates the one in
``core/llm/``.

What this class does add is the check the port exists for. A hosted model can
change width between releases — a provider ships ``-v2``, an operator changes a
``dimensions`` parameter — and the failure mode is not an error but a corpus
where half the vectors are 1536 wide and half are 3072. Every batch is measured
against the declared width, and a disagreement raises the same
``EmbeddingDimensionMismatch`` the index would have raised, before anything is
written.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from config.constants.persistence import EPISODE_VECTOR_NAMESPACE
from platform.persistence.errors import EmbeddingDimensionMismatch


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Whatever actually computes the vectors, however it reaches them."""

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector per input, in the order the inputs were given."""


@dataclass(frozen=True, slots=True)
class ProviderEmbedder:
    """A hosted model, with its declared identity enforced on every batch."""

    backend: EmbeddingBackend
    model: str
    dimension: int
    namespace: str = EPISODE_VECTOR_NAMESPACE

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("an embedder must name its model — the index records it per vector")
        if self.dimension < 1:
            raise ValueError(f"an embedder needs at least one dimension, got {self.dimension}")

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Return one vector per input, checked against the declared width.

        Both the count and each width are checked. A backend that dropped an
        input would otherwise leave the caller zipping vectors against the wrong
        episodes, which produces a searchable corpus of confident nonsense.
        """
        produced = await self.backend.embed(texts)
        if len(produced) != len(texts):
            raise ValueError(
                f"{self.model} returned {len(produced)} vectors for {len(texts)} input(s) — "
                "an embedder must return one vector per input, in order"
            )

        for vector in produced:
            if len(vector) != self.dimension:
                raise EmbeddingDimensionMismatch(
                    namespace=self.namespace,
                    expected=self.dimension,
                    found=len(vector),
                )

        return tuple(tuple(float(value) for value in vector) for vector in produced)


__all__ = ["EmbeddingBackend", "ProviderEmbedder"]
