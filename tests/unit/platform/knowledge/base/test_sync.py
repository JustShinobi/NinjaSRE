"""Four sources, one boundary, and the page that must not stop the other ninety-nine.

Each adapter is tested on the mapping, because the mapping is the part that is
different and the part that is wrong when a citation points at the wrong page.
The sync runner is tested on one property above all: a document refused at the
ingestion boundary is *named in the report* and does not fail the run. A sync
that stopped at the first page somebody pasted a credential into is a sync that
never completes, and a sync that swallowed it is a page nobody fixes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from config.constants.knowledge import KNOWLEDGE_SYNC_JOB_KIND, TOPOLOGY_DISCOVERY_JOB_KIND
from platform.guardrails.engine import GuardrailEngine
from platform.knowledge.base.ingestion import KnowledgeIngestor
from platform.knowledge.base.models import DocumentType
from platform.knowledge.base.sync.confluence import ConfluenceSource
from platform.knowledge.base.sync.git import GitMarkdownSource
from platform.knowledge.base.sync.google_docs import GoogleDocsSource
from platform.knowledge.base.sync.notion import NotionSource
from platform.knowledge.base.sync.port import KnowledgeSync, SourceDocument, document_id_for
from platform.knowledge.base.sync.schedule import (
    knowledge_sync_job,
    source_of,
    topology_discovery_job,
)
from platform.knowledge.base.sync.text import from_html
from platform.knowledge.base.tree import KnowledgeTree
from platform.memory.embeddings.local import LocalEmbedder
from platform.persistence.ports import PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import Clock

pytestmark = pytest.mark.unit

#: A page body carrying a PEM block, which the shipped ruleset blocks. Enough to
#: match and nothing more.
PAGE_WITH_A_SECRET = (
    "<h1>Access</h1><p>-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAx\n"
    "-----END RSA PRIVATE KEY-----</p>"
)


class StubSource:
    """A document source over fixed documents."""

    def __init__(self, *documents: SourceDocument, name: str = "stub") -> None:
        self._documents = documents
        self._name = name

    @property
    def name(self) -> str:
        """Return the identifier this source's documents are namespaced under."""
        return self._name

    async def fetch(self) -> Sequence[SourceDocument]:
        """Return the fixed documents."""
        return self._documents


class StubConfluence:
    """A Confluence reader over fixed page payloads."""

    def __init__(self, *pages: Mapping[str, Any]) -> None:
        self._pages = pages

    async def pages(self) -> Sequence[Mapping[str, Any]]:
        """Return the fixed pages."""
        return self._pages


class StubNotion:
    """A Notion reader over fixed pages and blocks."""

    def __init__(
        self,
        pages: Sequence[Mapping[str, Any]],
        blocks: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> None:
        self._pages = pages
        self._blocks = blocks

    async def pages(self) -> Sequence[Mapping[str, Any]]:
        """Return the fixed pages."""
        return self._pages

    async def blocks(self, page_id: str) -> Sequence[Mapping[str, Any]]:
        """Return the fixed blocks for one page."""
        return self._blocks.get(page_id, ())


class StubGoogleDocs:
    """A Google Docs reader over fixed document resources."""

    def __init__(self, *documents: Mapping[str, Any]) -> None:
        self._documents = documents

    async def documents(self) -> Sequence[Mapping[str, Any]]:
        """Return the fixed documents."""
        return self._documents


def source_document(external_id: str, body: str = "# Title\n\nSome prose.\n") -> SourceDocument:
    """Return one source document."""
    return SourceDocument(external_id=external_id, title="Title", body=body)


def syncer(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> KnowledgeSync:
    """Return a sync runner over a real ingestor."""
    return KnowledgeSync(
        ingestor=KnowledgeIngestor(
            gateway=gateway, scope=scope, embedder=embedder, engine=engine, clock=clock
        ),
        scope=scope,
        clock=clock,
    )


# --- The runner ---------------------------------------------------------------


async def test_a_refused_page_is_named_and_the_rest_of_the_run_completes(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    """The property that makes a scheduled sync safe to leave running."""
    run = syncer(gateway, scope, embedder, engine, clock)
    source = StubSource(
        source_document("good-1"),
        SourceDocument(
            external_id="leaky",
            title="Access",
            body="# Access\n\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEAx\n",
        ),
        source_document("good-2"),
    )

    report = await run.run(source)

    assert set(report.stored) == {
        document_id_for("stub", "good-1"),
        document_id_for("stub", "good-2"),
    }
    assert [document_id for document_id, _ in report.rejected] == [document_id_for("stub", "leaky")]
    assert "private-key-block" in report.rejected[0][1]
    assert "MIIEowIBAAKCAQEAx" not in report.rejected[0][1]


async def test_a_second_run_of_an_unchanged_source_stores_nothing(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    run = syncer(gateway, scope, embedder, engine, clock)
    source = StubSource(source_document("good-1"))

    await run.run(source)
    again = await run.run(source)

    assert again.stored == ()
    assert again.unchanged == (document_id_for("stub", "good-1"),)


async def test_two_sources_using_the_same_identifier_produce_two_documents(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    # A corpus where one silently superseded the other would lose a document
    # with no error anywhere.
    run = syncer(gateway, scope, embedder, engine, clock)

    await run.run(StubSource(source_document("42"), name="confluence"))
    await run.run(StubSource(source_document("42"), name="notion"))

    documents = await KnowledgeTree(gateway=gateway, scope=scope).documents()
    assert {item.document_id for item in documents} == {"confluence:42", "notion:42"}


async def test_a_run_larger_than_the_bound_reports_that_it_was_cut(
    gateway: PersistenceGateway,
    scope: TenantScope,
    embedder: LocalEmbedder,
    engine: GuardrailEngine,
    clock: Clock,
) -> None:
    run = syncer(gateway, scope, embedder, engine, clock)
    run.limit = 2
    source = StubSource(*(source_document(f"page-{index}") for index in range(5)))

    report = await run.run(source)

    assert report.truncated is True
    assert len(report.stored) == 2


# --- Confluence ---------------------------------------------------------------


async def test_confluence_maps_the_storage_body_the_tree_and_the_link() -> None:
    source = ConfluenceSource(
        reader=StubConfluence(
            {
                "id": "1201",
                "title": "Payments failover",
                "body": {
                    "storage": {
                        "value": "<h2>Failing over</h2><p>Promote the standby.</p>"
                        "<ul><li>Drain the pool</li></ul>"
                    }
                },
                "ancestors": [{"id": "10"}, {"id": "99"}],
                "_links": {"webui": "/spaces/OPS/pages/1201"},
                "metadata": {"labels": {"results": [{"name": "postmortem"}]}},
                "version": {"when": "2026-05-30T09:00:00.000Z"},
            }
        ),
        base_url="https://wiki.example/",
    )

    found = (await source.fetch())[0]

    assert found.external_id == "1201"
    assert "## Failing over" in found.body
    assert "- Drain the pool" in found.body
    # The immediate ancestor is the last one: Confluence lists them root-first.
    assert found.parent_external_id == "99"
    assert found.source_uri == "https://wiki.example/spaces/OPS/pages/1201"
    assert found.document_type is DocumentType.POSTMORTEM
    assert found.updated_at is not None


async def test_a_confluence_page_with_no_text_is_skipped() -> None:
    # A placeholder or an empty template. Ingesting it would put a title in the
    # index with nothing behind it.
    source = ConfluenceSource(
        reader=StubConfluence({"id": "1", "title": "Empty", "body": {"storage": {"value": ""}}})
    )

    assert await source.fetch() == ()


def test_confluence_macros_are_dropped_rather_than_rendered() -> None:
    # A macro that expands to a live chart at read time has no text to
    # contribute, and inventing one would put a sentence in a runbook.
    text = from_html(
        '<p>Before</p><ac:structured-macro ac:name="chart"><ac:parameter>x</ac:parameter>'
        "</ac:structured-macro><p>After</p>"
    )

    assert "Before" in text
    assert "After" in text
    assert "structured-macro" not in text


# --- Notion -------------------------------------------------------------------


async def test_notion_finds_the_title_property_by_type_not_by_name() -> None:
    # Notion lets a database rename its title property, and a lookup on "Name"
    # works until the first team that did.
    source = NotionSource(
        reader=StubNotion(
            pages=[
                {
                    "id": "page-1",
                    "url": "https://notion.so/page-1",
                    "properties": {
                        "Runbook name": {
                            "type": "title",
                            "title": [{"plain_text": "Payments failover"}],
                        }
                    },
                    "parent": {"page_id": "parent-1"},
                    "last_edited_time": "2026-05-30T09:00:00.000Z",
                }
            ],
            blocks={
                "page-1": [
                    {
                        "type": "heading_2",
                        "heading_2": {"rich_text": [{"plain_text": "Failing over"}]},
                    },
                    {
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": [{"plain_text": "Drain the pool"}]},
                    },
                    {
                        "type": "code",
                        "code": {
                            "language": "bash",
                            "rich_text": [{"plain_text": "kubectl rollout restart deploy/x"}],
                        },
                    },
                ]
            },
        )
    )

    found = (await source.fetch())[0]

    assert found.title == "Payments failover"
    assert "## Failing over" in found.body
    assert "- Drain the pool" in found.body
    # A command that lost its fence is a command somebody will run wrong.
    assert "```bash" in found.body
    assert found.parent_external_id == "parent-1"


# --- Google Docs --------------------------------------------------------------


async def test_google_docs_uses_the_named_style_to_find_headings() -> None:
    source = GoogleDocsSource(
        reader=StubGoogleDocs(
            {
                "documentId": "doc-1",
                "title": "Payments failover",
                "modifiedTime": "2026-05-30T09:00:00.000Z",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "HEADING_2"},
                                "elements": [{"textRun": {"content": "Failing over"}}],
                            }
                        },
                        {
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                "elements": [{"textRun": {"content": "Promote the standby."}}],
                            }
                        },
                        {"table": {"rows": 2}},
                    ]
                },
            }
        )
    )

    found = (await source.fetch())[0]

    assert "## Failing over" in found.body
    assert "Promote the standby." in found.body
    assert found.source_uri.endswith("/doc-1/edit")


# --- Git ----------------------------------------------------------------------


async def test_git_reads_markdown_and_hangs_it_under_the_directory_index(
    tmp_path: Path,
) -> None:
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "runbooks" / "README.md").write_text("# Runbooks\n\nThe index.\n")
    (tmp_path / "runbooks" / "failover.md").write_text("# Failover\n\nPromote the standby.\n")
    (tmp_path / "postmortems").mkdir()
    (tmp_path / "postmortems" / "checkout.md").write_text("# Checkout 5xx\n\nWhat happened.\n")
    (tmp_path / "notes.txt").write_text("not markdown")

    found = {item.external_id: item for item in await GitMarkdownSource(root=tmp_path).fetch()}

    assert set(found) == {
        "runbooks/README.md",
        "runbooks/failover.md",
        "postmortems/checkout.md",
    }
    assert found["runbooks/failover.md"].parent_external_id == "runbooks/README.md"
    assert found["runbooks/README.md"].parent_external_id == ""
    assert found["postmortems/checkout.md"].document_type is DocumentType.POSTMORTEM
    assert found["runbooks/failover.md"].title == "Failover"


async def test_git_skips_the_repository_metadata(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "COMMIT_EDITMSG.md").write_text("# not documentation\n")
    (tmp_path / "runbook.md").write_text("# A runbook\n\nSomething.\n")

    found = await GitMarkdownSource(root=tmp_path).fetch()

    assert [item.external_id for item in found] == ["runbook.md"]


async def test_a_missing_git_root_is_an_empty_fetch_not_an_exception(tmp_path: Path) -> None:
    # A scheduled sync against a checkout that has not happened yet must not
    # take the worker down with it.
    found = await GitMarkdownSource(root=tmp_path / "nothing-here").fetch()

    assert found == ()


# --- Scheduling ---------------------------------------------------------------


def test_the_job_definitions_are_idempotent_and_name_their_source() -> None:
    # Two syncs of one space racing each other is a corpus where the winner is
    # whichever transaction committed last.
    first = knowledge_sync_job(source="confluence", schedule="0 2 * * *")
    again = knowledge_sync_job(source="confluence", schedule="0 3 * * *")

    assert first.job_id == again.job_id
    assert first.kind == KNOWLEDGE_SYNC_JOB_KIND
    assert source_of(first) == "confluence"

    discovery = topology_discovery_job(source="kubernetes", schedule="*/30 * * * *")
    assert discovery.kind == TOPOLOGY_DISCOVERY_JOB_KIND
    assert discovery.job_id != first.job_id
