"""Running the two knowledge jobs the scheduler can now dispatch.

``schedule.py`` is the two job *definitions* and says in as many words that it is
"not the running of them, which is the worker's job and lives with the worker".
This is that half, and it stayed missing long enough for both kinds to be
registerable and inert.

These are adapters and nothing more. Neither decides what a sync does — that is
``KnowledgeSync`` and ``CorpusSync``, each with its own suite — and neither
constructs one, because building an ingestor means an embedder, a guardrail
engine and a store, all of which belong to a composition root. What they add is
exactly the two things a scheduled run needs and a request-driven one gets for
free: **which source**, and **for which team**.

**An unknown source is refused, loudly.** A job naming a source this deployment
does not have is somebody's configuration drifting from somebody else's, and
answering it with a sync of nothing would report success for a corpus that is
not being read. The dispatcher turns the refusal into a failed run with the name
in it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

from platform.knowledge.base.sync.corpus import CorpusSource
from platform.knowledge.base.sync.corpus_run import CorpusReport
from platform.knowledge.base.sync.port import DocumentSource, SyncReport
from platform.knowledge.base.sync.schedule import NODE_KEY, SOURCE_KEY
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope
from platform.scheduler.dispatch import JobContext

logger = get_logger(__name__)


class UnknownSource(LookupError):
    """A scheduled job names a source this deployment has not configured."""

    def __init__(self, source: str, known: tuple[str, ...]) -> None:
        super().__init__(
            f"No sync source named {source or '(none)'!r} is configured. "
            f"This deployment can sync: {', '.join(known) or 'nothing'}."
        )
        self.source = source
        self.known = known


@runtime_checkable
class DocumentSync(Protocol):
    """What a document-sync runner needs from the sync itself."""

    async def run(self, source: DocumentSource) -> SyncReport:
        """Ingest ``source`` and report what happened, per document."""


@runtime_checkable
class CorpusPass(Protocol):
    """What a corpus runner needs from the corpus pass itself."""

    async def run(self, source: CorpusSource) -> CorpusReport:
        """Read ``source`` and report everything the pass produced."""


def _pick(sources: Mapping[str, Any], context: JobContext) -> Any:
    """Return the source ``context`` names, or raise ``UnknownSource``."""
    name = context.named(SOURCE_KEY)
    source = sources.get(name)
    if source is None:
        raise UnknownSource(name, tuple(sources))
    return source


def scope_for(context: JobContext) -> TenantScope:
    """Return the scope a knowledge job runs in.

    The team comes off the payload rather than off the claim: a claim is scoped
    to an organisation, and a corpus is read *for a team* — its checks become
    that team's detectors and its proposals arrive in that team's queue. A job
    carrying no team runs at the organisation root, which is what a
    single-team deployment's wiki sync is.
    """
    return replace(context.scope, team_node_id=context.named(NODE_KEY))


@dataclass(slots=True)
class KnowledgeSyncRunner:
    """Runs the document sync one claimed ``knowledge.sync`` job names."""

    sources: Mapping[str, DocumentSource]
    #: Built per run rather than held, because the sync is scoped to a tenant
    #: and one runner serves every tenant a worker claims for.
    sync_for: Callable[[TenantScope], DocumentSync]

    async def run(self, context: JobContext) -> Mapping[str, Any]:
        """Sync the named source and return the report as the record."""
        source = _pick(self.sources, context)
        report = await self.sync_for(scope_for(context)).run(source)
        return report.to_record()


@dataclass(slots=True)
class CorpusSyncRunner:
    """Runs the corpus pass one claimed ``knowledge.corpus_sync`` job names."""

    sources: Mapping[str, CorpusSource]
    corpus_for: Callable[[TenantScope], CorpusPass]

    async def run(self, context: JobContext) -> Mapping[str, Any]:
        """Read the named repository and return everything the pass produced.

        The detector candidates travel in the record and are not written. A
        document changing what a deployment watches, with no record of who
        agreed, is the thing the configuration service's approval gate exists to
        stop — and a scheduled run is exactly where nobody would notice.
        """
        source = _pick(self.sources, context)
        report = await self.corpus_for(scope_for(context)).run(source)
        return report.to_record()


__all__ = [
    "CorpusPass",
    "CorpusSyncRunner",
    "DocumentSync",
    "KnowledgeSyncRunner",
    "UnknownSource",
    "scope_for",
]
