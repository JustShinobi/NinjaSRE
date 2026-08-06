"""The one thing memory needs from an embedding model, and nothing else.

Three members, and the two that are not ``embed`` are the point. A vector store
that does not know which model produced a vector cannot tell a re-embed from a
corruption, and one that does not know the width cannot reject a write that is
the wrong shape — it will pad it, truncate it, or index it, and all three of
those *return results*. They are merely the wrong results, and nothing
downstream can tell.

So a model declares its identity and its width, the index records both, and a
mismatch is an error at the boundary rather than a slow drift in recall quality
that somebody eventually notices.

Batching is in the signature because embedding is the one part of writing an
episode that is worth batching: a re-embedding pass over a hundred thousand
episodes through a one-at-a-time interface is a hundred thousand round trips.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Turns text into vectors of a fixed, declared width."""

    @property
    def model(self) -> str:
        """Return the identifier recorded beside every vector this produces."""

    @property
    def dimension(self) -> int:
        """Return the width of every vector this produces."""

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Return one vector per input, in the order the inputs were given.

        The order is part of the contract. A caller zips these back against the
        episodes they came from, and an implementation that reordered for
        batching efficiency would attach every vector to the wrong record.
        """


async def embed_one(embedder: Embedder, text: str) -> tuple[float, ...]:
    """Return the vector for one piece of text.

    A helper rather than a second protocol method: the single-item case is
    common enough to be worth writing once, and a port with two ways to do the
    same thing is a port with two implementations to keep in agreement.
    """
    vectors = await embedder.embed([text])
    if len(vectors) != 1:
        raise ValueError(
            f"{embedder.model} returned {len(vectors)} vectors for one input — "
            "an embedder must return one vector per input, in order"
        )
    return vectors[0]


__all__ = ["Embedder", "embed_one"]
