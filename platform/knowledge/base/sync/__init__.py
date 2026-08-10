"""Five ways a team's existing documentation gets into the knowledge base.

Teams do not write their runbooks here. They already have them — in a wiki, in a
Notion workspace, in a shared drive, or beside the code — and a knowledge base
that required them to be re-typed is a knowledge base with four documents in it.
So the sync adapters exist to make the corpus something an operator points at
rather than something they fill in.

All of them share the same shape and the same guarantees. Each is a *reader* plus a
mapping: the reader is whatever the deployment already has, because ``platform``
is tier 3 and cannot import a vendor client, and the mapping is the adapter's
real work. Each document goes through the same ingestion boundary as an upload,
so a page whose author pasted a credential into it is refused with the location
reported, and the other ninety-nine pages sync.

``git`` is the one to start with. It needs no vendor at all, and documentation
that lives beside the code is reviewed with the code.

``corpus`` is the one for a deployment that arrives with two years of writing
already done. It is ``git`` narrowed to an allowlist — Markdown under ``docs/``
and YAML under ``policies/``, and nothing else in a repository of fifteen
thousand files — with a post-mortem's structure pulled out on the way in.
"""

from __future__ import annotations

from platform.knowledge.base.sync.confluence import ConfluenceReader, ConfluenceSource
from platform.knowledge.base.sync.corpus import CorpusSource
from platform.knowledge.base.sync.corpus_run import CorpusReport, CorpusSync, settings_patch
from platform.knowledge.base.sync.git import GitMarkdownSource
from platform.knowledge.base.sync.google_docs import GoogleDocsReader, GoogleDocsSource
from platform.knowledge.base.sync.notion import NotionReader, NotionSource
from platform.knowledge.base.sync.port import (
    DocumentSource,
    KnowledgeSync,
    SourceDocument,
    SyncReport,
    document_id_for,
)
from platform.knowledge.base.sync.schedule import (
    knowledge_sync_job,
    topology_discovery_job,
)

__all__ = [
    "ConfluenceReader",
    "ConfluenceSource",
    "CorpusReport",
    "CorpusSource",
    "CorpusSync",
    "DocumentSource",
    "GitMarkdownSource",
    "GoogleDocsReader",
    "GoogleDocsSource",
    "KnowledgeSync",
    "NotionReader",
    "NotionSource",
    "SourceDocument",
    "SyncReport",
    "document_id_for",
    "knowledge_sync_job",
    "settings_patch",
    "topology_discovery_job",
]
