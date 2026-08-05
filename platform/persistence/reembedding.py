"""Re-embedding a corpus without search going down (FR-014).

Changing the embedding model means every vector in a namespace is wrong at once,
and rebuilding a hundred thousand of them takes long enough that "just do it at
startup" is an outage. The ports already carry the mechanism — generations, and
an activation that is a pointer move — and this module is the loop that drives
it, written once so that features 010 and 012 do not each write their own.

The shape is four steps and the third is the one that matters:

1. Open a generation with the new model's width.
2. Fill it in batches, each its own unit of work. Search is still reading the
   old generation, and every batch that lands is a batch that will not have to
   be recomputed if the process restarts.
3. **Verify before activating.** A generation that is short of the corpus is
   activated into a search that silently returns fewer neighbours than it should.
   Counting first turns that into a refusal.
4. Activate, then drop the old one.

Deliberately not a background task. The platform has a scheduler (feature 016)
and it is the thing that should own "run this later"; a module that spawned its
own would be a second answer to that question, and the two would drift on
cancellation, retries, and what happens at shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from config.constants.persistence import MIGRATION_BACKFILL_BATCH_SIZE
from platform.persistence.errors import PersistenceError
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
from platform.persistence.ports.vector_index import IndexDescriptor, VectorRecord

#: Vectors written per unit of work. Shares the migration backfill's bound
#: because it is the same trade: a batch small enough that no single transaction
#: holds locks long enough to stall an investigation writing its trace.
REEMBED_BATCH_SIZE = MIGRATION_BACKFILL_BATCH_SIZE


class ReembedIncomplete(PersistenceError):
    """A new generation was short of the corpus, so it was not activated.

    The old generation is still active and search is unaffected. Something
    dropped records — an embedding call that failed quietly, a source that ran
    out — and activating anyway would turn that into a corpus with holes in it
    that nothing would report.
    """

    def __init__(self, *, namespace: str, expected: int, written: int) -> None:
        super().__init__(
            f"Re-embedding {namespace!r} produced {written} vectors for a corpus of "
            f"{expected}. The new generation was left inactive and the old one is "
            f"still serving searches."
        )
        self.namespace = namespace
        self.expected = expected
        self.written = written


@dataclass(frozen=True, slots=True)
class ReembedReport:
    """What one re-embedding pass did."""

    namespace: str
    model: str
    dimension: int
    generation: int
    written: int
    dropped: int = 0
    descriptor: IndexDescriptor | None = None


@dataclass(slots=True)
class Reembedder:
    """Drives a namespace from one embedding model to another."""

    gateway: PersistenceGateway
    scope: TenantScope
    batch_size: int = field(default=REEMBED_BATCH_SIZE)

    async def run(
        self,
        namespace: str,
        *,
        model: str,
        dimension: int,
        records: AsyncIterator[Sequence[VectorRecord]],
        expected: int | None = None,
        drop_previous: bool = True,
    ) -> ReembedReport:
        """Re-embed ``namespace`` from ``records`` and activate the result.

        ``records`` yields batches. Taking an iterator of batches rather than a
        callback keeps the embedding provider out of this module entirely — what
        arrives here is vectors, and where they came from is feature 010's
        business.

        ``expected`` is the corpus size the caller believes it is replacing.
        Given it, a short generation raises ``ReembedIncomplete`` and nothing is
        activated.
        """
        async with self.gateway.begin(self.scope) as uow:
            previous = await uow.vectors.describe(namespace)
            generation = await uow.vectors.begin_generation(
                namespace, model=model, dimension=dimension
            )

        written = 0
        async for batch in records:
            for chunk in _chunked(batch, self.batch_size):
                # One unit of work per chunk. A pass that dies half way has
                # written half a generation nobody is searching, which is the
                # correct amount of damage.
                async with self.gateway.begin(self.scope) as uow:
                    written += await uow.vectors.upsert(namespace, chunk, generation=generation)

        if expected is not None and written < expected:
            raise ReembedIncomplete(namespace=namespace, expected=expected, written=written)

        async with self.gateway.begin(self.scope) as uow:
            descriptor = await uow.vectors.activate_generation(namespace, generation)

        dropped = 0
        if drop_previous and previous is not None and previous.generation != generation:
            async with self.gateway.begin(self.scope) as uow:
                dropped = await uow.vectors.drop_generation(namespace, previous.generation)

        return ReembedReport(
            namespace=namespace,
            model=model,
            dimension=dimension,
            generation=generation,
            written=written,
            dropped=dropped,
            descriptor=descriptor,
        )


def _chunked(records: Sequence[VectorRecord], size: int) -> list[Sequence[VectorRecord]]:
    """Split ``records`` into chunks of at most ``size``."""
    if size < 1:
        raise ValueError(f"A re-embedding batch must hold at least one vector, got {size}.")
    return [records[start : start + size] for start in range(0, len(records), size)] or []


__all__ = ["REEMBED_BATCH_SIZE", "ReembedIncomplete", "ReembedReport", "Reembedder"]
