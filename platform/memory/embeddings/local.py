"""The default embedder: in-process, deterministic, and reaching no network.

A cloud embedding call on every episode write and every recall would make memory
the one feature that breaks the deployment the product exists for — an operator
who may not send production text off their infrastructure would have an SRE
agent that cannot remember anything. So the default has to work with no egress,
and it does.

The model is hashed character-and-word n-grams projected into a fixed-width
space, signed by a second hash bit and L2-normalised. That is a lexical model
rather than a semantic one, and the trade is deliberate and stated: it will match
"OOMKilled on payments-api" to a previous OOMKill on payments-api, and it will
not match "the pod ran out of memory" to it. A deployment that wants semantic
recall installs a sentence-transformer or a provider behind the same port and
re-embeds; nothing above this module changes, because the port is three members
and this one satisfies them.

Determinism matters more than it looks. Python's ``hash`` is salted per process,
so a corpus embedded by one worker would be unsearchable by the next. ``blake2b``
is stable across processes, machines, and releases, which is what makes a stored
vector still mean something tomorrow.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from hashlib import blake2b

from config.constants.memory import (
    LOCAL_EMBEDDING_DIMENSION,
    LOCAL_EMBEDDING_MODEL,
    LOCAL_EMBEDDING_NGRAM_SIZES,
)

#: Splits on anything that is not a letter, a digit, or one of the three
#: punctuation marks that carry meaning in an identifier. Keeping ``-``, ``_``
#: and ``.`` inside tokens is what stops ``payments-api`` becoming two words that
#: match half the estate.
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def tokenise(text: str) -> tuple[str, ...]:
    """Return the lowercase tokens ``text`` contributes."""
    return tuple(match.group(0).lower() for match in _TOKEN.finditer(text))


def _ngrams(tokens: Sequence[str], sizes: Sequence[int]) -> Iterator[str]:
    """Yield every n-gram of ``tokens`` at each requested width."""
    for size in sizes:
        if size < 1:
            raise ValueError(f"an n-gram width must be at least one, got {size}")
        for start in range(len(tokens) - size + 1):
            yield " ".join(tokens[start : start + size])


@dataclass(frozen=True, slots=True)
class LocalEmbedder:
    """A deterministic hashing embedder that never leaves the process."""

    model: str = LOCAL_EMBEDDING_MODEL
    dimension: int = LOCAL_EMBEDDING_DIMENSION
    ngram_sizes: tuple[int, ...] = LOCAL_EMBEDDING_NGRAM_SIZES

    def __post_init__(self) -> None:
        if self.dimension < 1:
            raise ValueError(f"an embedder needs at least one dimension, got {self.dimension}")
        if not self.ngram_sizes:
            raise ValueError("a hashing embedder needs at least one n-gram width")

    async def embed(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Return one vector per input, in order."""
        return tuple(self.vector(text) for text in texts)

    def vector(self, text: str) -> tuple[float, ...]:
        """Return the unit-length vector for one piece of text.

        Synchronous and exposed, because it is pure arithmetic over a string and
        a caller that already holds the text — a test, a re-embedding pass —
        should not have to enter an event loop to get a vector out of it.
        """
        weights = [0.0] * self.dimension
        for gram in _ngrams(tokenise(text), self.ngram_sizes):
            digest = blake2b(gram.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            # The sign comes from a different slice of the same digest, so two
            # unrelated grams landing in one bucket cancel as often as they
            # reinforce. Without it, every collision inflates the same
            # direction and a long document drifts towards a fixed vector.
            weights[index] += 1.0 if digest[4] & 1 else -1.0

        norm = math.sqrt(sum(weight * weight for weight in weights))
        if norm == 0.0:
            # Empty or unembeddable text. A zero vector has no direction, and
            # the index scores it 0.5 against everything — which is the honest
            # answer for a query that said nothing.
            return tuple(weights)
        return tuple(weight / norm for weight in weights)


__all__ = ["LocalEmbedder", "tokenise"]
