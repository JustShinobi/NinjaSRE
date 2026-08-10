"""What the corpus source reads, what it refuses to read, and what it calls it.

The tree under `tests/corpus/operational/` is shaped like a real repository's
documentation, decoys included, and these are the assertions that shape is for.
A repository holds fifteen thousand files; the corpus is two directories of it,
and every other file in the fixture is here so that a test can say the source
did not open it rather than the source merely happening not to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.constants.knowledge import MAX_CORPUS_FILE_BYTES, MAX_CORPUS_FILES
from platform.knowledge.base.models import DocumentType
from platform.knowledge.base.sync.corpus import CorpusSource, classify
from platform.knowledge.errors import CorpusBoundExceeded

CORPUS = Path(__file__).resolve().parents[4] / "corpus" / "operational"


def _source(root: Path | None = None, **overrides: object) -> CorpusSource:
    return CorpusSource(root=root or CORPUS, **overrides)  # type: ignore[arg-type]


class TestWhatTheSourceEnumerates:
    """Exactly Markdown under ``docs/`` and YAML under ``policies/``."""

    def test_the_readable_set_is_markdown_under_docs_and_yaml_under_policies(self) -> None:
        found = {path.as_posix() for path in _source().readable()}

        assert found == {
            "docs/adr/0001-one-control-plane-per-cluster.md",
            "docs/adr/0002-an-overlay-network-per-workload-class.md",
            "docs/adr/0003-backups-land-on-a-second-datastore.md",
            "docs/analysis/capacity-review-2026-q2.md",
            "docs/postmortem/2025-11-08-a-mount-that-would-not-clear.md",
            "docs/postmortem/2025-12-05-certificate-expiry-on-edge-proxy.md",
            "docs/postmortem/2026-01-19-datastore-full-during-snapshot.md",
            "docs/postmortem/2026-02-02-backup-job-disabled-and-unnoticed.md",
            "docs/postmortem/2026-03-11-quorum-lost-during-node-reboot.md",
            "docs/postmortem/2026-04-24-fileserver-nfs-hard-mount-stall.md",
            "docs/postmortem/2026-07-17-adguard-dns-stall-both-instances.md",
            "docs/postmortem/2026-07-20-adguard-dns-recurrence-memcg-oom.md",
            "docs/postmortem/2026-07-27-vxlan-overlay-mtu-equal-to-underlay.md",
            "docs/postmortem/2026-07-28-observability-stack-log-storm.md",
            "docs/runbooks/adguard-dns-recovery.md",
            "docs/runbooks/backup-restore.md",
            "docs/runbooks/cluster-double-check-queries.md",
            "docs/runbooks/vxlan-zone-mtu.md",
            "policies/firewall/cluster.yaml",
            "policies/firewall/datacenter-aliases.yaml",
        }

    @pytest.mark.parametrize(
        "decoy",
        [
            ".env.local",
            "infrastructure/terraform.tfstate",
            "uv.lock",
            "scripts/rotate-credentials.sh",
            "docs/notes.txt",
            "docs/runbooks/topology.png.md.bak",
            "policies/firewall/README.md",
            "README.md",
        ],
    )
    def test_a_decoy_is_never_read(self, decoy: str) -> None:
        assert (CORPUS / decoy).is_file(), "the fixture must actually hold the decoy"
        assert decoy not in {path.as_posix() for path in _source().readable()}

    def test_the_order_is_the_same_twice(self) -> None:
        # Two syncs of an unchanged tree have to produce the same report, and a
        # filesystem does not promise an order.
        assert _source().readable() == _source().readable()

    def test_a_root_that_does_not_exist_reads_as_an_empty_corpus(self, tmp_path: Path) -> None:
        assert _source(tmp_path / "nowhere").readable() == ()


class TestTheBounds:
    """Both are named constants, and exceeding one says which."""

    def test_more_files_than_the_ceiling_is_refused_naming_the_constant(
        self, tmp_path: Path
    ) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        for ordinal in range(4):
            (docs / f"{ordinal}.md").write_text(f"# {ordinal}\n\nbody\n", encoding="utf-8")

        with pytest.raises(CorpusBoundExceeded) as refused:
            _source(tmp_path, max_files=3).readable()

        assert refused.value.constant == "MAX_CORPUS_FILES"
        assert refused.value.limit == 3
        assert refused.value.requested == 4

    def test_the_file_ceiling_defaults_to_the_constant(self) -> None:
        assert _source().max_files == MAX_CORPUS_FILES
        assert _source().max_file_bytes == MAX_CORPUS_FILE_BYTES

    @pytest.mark.asyncio
    async def test_one_oversized_file_is_skipped_naming_the_constant_and_the_rest_are_read(
        self, tmp_path: Path
    ) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "manual.md").write_text("# Manual\n\n" + ("x" * 400), encoding="utf-8")
        (docs / "short.md").write_text("# Short\n\nbody\n", encoding="utf-8")

        source = _source(tmp_path, max_file_bytes=100)
        found = await source.fetch()

        assert [entry.external_id for entry in found] == ["docs/short.md"]
        assert len(source.skipped) == 1
        path, reason = source.skipped[0]
        assert path == "docs/manual.md"
        assert "MAX_CORPUS_FILE_BYTES" in reason


class TestClassificationComesFromThePath:
    """The directory already says what the document is; a model call would not."""

    @pytest.mark.parametrize(
        ("relative", "expected"),
        [
            ("docs/runbooks/adguard-dns-recovery.md", DocumentType.RUNBOOK),
            ("docs/runbooks/deep/nested/thing.md", DocumentType.RUNBOOK),
            (
                "docs/postmortem/2026-07-17-adguard-dns-stall-both-instances.md",
                DocumentType.POSTMORTEM,
            ),
            ("docs/postmortems/anything.md", DocumentType.POSTMORTEM),
            ("docs/adr/0001-one-control-plane-per-cluster.md", DocumentType.ARCHITECTURE),
            ("policies/firewall/cluster.yaml", DocumentType.POLICY),
            ("policies/anything/else.yaml", DocumentType.POLICY),
            ("docs/analysis/capacity-review-2026-q2.md", DocumentType.REFERENCE),
            ("docs/plans/whatever.md", DocumentType.REFERENCE),
            ("docs/index.md", DocumentType.REFERENCE),
        ],
    )
    def test_a_path_classifies(self, relative: str, expected: DocumentType) -> None:
        assert classify(relative) is expected

    @pytest.mark.asyncio
    async def test_every_fixture_document_carries_the_type_its_directory_implies(self) -> None:
        found = {entry.external_id: entry for entry in await _source().fetch()}

        assert found["docs/runbooks/adguard-dns-recovery.md"].document_type is DocumentType.RUNBOOK
        assert (
            found["docs/postmortem/2026-07-20-adguard-dns-recurrence-memcg-oom.md"].document_type
            is DocumentType.POSTMORTEM
        )
        assert (
            found["docs/adr/0001-one-control-plane-per-cluster.md"].document_type
            is DocumentType.ARCHITECTURE
        )
        assert found["policies/firewall/cluster.yaml"].document_type is DocumentType.POLICY
        assert (
            found["docs/analysis/capacity-review-2026-q2.md"].document_type
            is DocumentType.REFERENCE
        )


class TestWhatOneFetchedDocumentCarries:
    """A citation an operator can open, and a title somebody wrote."""

    @pytest.mark.asyncio
    async def test_the_source_uri_is_the_path_relative_to_the_repository(self) -> None:
        found = {entry.external_id: entry for entry in await _source().fetch()}

        assert (
            found["docs/runbooks/adguard-dns-recovery.md"].source_uri
            == "docs/runbooks/adguard-dns-recovery.md"
        )

    @pytest.mark.asyncio
    async def test_a_base_url_makes_the_citation_clickable(self) -> None:
        source = _source(base_url="https://code.example.invalid/infra/blob/main/")
        found = {entry.external_id: entry for entry in await source.fetch()}

        assert found["policies/firewall/cluster.yaml"].source_uri == (
            "https://code.example.invalid/infra/blob/main/policies/firewall/cluster.yaml"
        )

    @pytest.mark.asyncio
    async def test_the_title_is_the_first_heading_and_falls_back_to_the_filename(self) -> None:
        found = {entry.external_id: entry for entry in await _source().fetch()}

        assert found["docs/runbooks/adguard-dns-recovery.md"].title == "Recovering AdGuard DNS"
        # YAML has no heading; the filename is what a citation can still say.
        assert found["policies/firewall/cluster.yaml"].title == "cluster"

    @pytest.mark.asyncio
    async def test_the_source_is_namespaced_so_two_corpora_do_not_collide(self) -> None:
        assert _source().name == "corpus"
        assert _source(name="second-cluster").name == "second-cluster"
