"""A repository's documentation directory, as a document source.

The adapter that exists because a deployment arrives with two years of writing
already done. Point it at a checked-out repository and it reads the prose — and
nothing else, which is the whole design.

**The readable set is an allowlist, not a filter.** Markdown under ``docs/`` and
YAML under ``policies/``. A real infrastructure repository holds fifteen
thousand files and the corpus is two directories of it; the rest is OpenTofu
state, lockfiles, scratch output and ``.env.local``. A source that walked the
tree and skipped what it recognised would be one file extension away from
embedding a state file, and there is no version of that failure that is visible
afterwards — the document is simply in the corpus, answering searches.

**Firewall policy is documentation.** Half of "I cannot reach X" is answered by
an ipset and an alias, so the YAML under ``policies/`` is corpus rather than
configuration. It is read, never applied.

**The type comes from the path, and no model is called for it.**
``docs/postmortem/x.md`` is a post-mortem because the directory says so.
Inferring it would be one model call per document to discover what the operator
already wrote down in the filesystem.

**Nothing is executed and nothing is fetched.** A repository is a directory on
disk by the time this runs — cloned by whatever the deployment already uses —
which keeps a subprocess, a credential and a network call out of tier 3. This
adapter reads files; the change history is another feature's problem.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from config.constants.knowledge import (
    CORPUS_DOCUMENT_ROOT,
    CORPUS_POLICY_ROOT,
    MAX_CORPUS_FILE_BYTES,
    MAX_CORPUS_FILES,
)
from platform.knowledge.base.models import DocumentType
from platform.knowledge.base.postmortem import (
    PostmortemExtractor,
    PostmortemFields,
    resolve_recurrences,
)
from platform.knowledge.base.sync.port import SourceDocument
from platform.knowledge.errors import CorpusBoundExceeded
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The name this source's documents are namespaced under, when the deployment
#: does not name it. A second cluster's corpus is a second name, so the two
#: never supersede each other's documents.
SOURCE = "corpus"

#: Extensions read as prose under ``docs/``.
MARKDOWN_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown"})

#: Extensions read as declarative policy under ``policies/``. Markdown there is
#: not read: a ``README.md`` beside a rule set describes the rules, and the
#: rules are what an investigation needs.
POLICY_SUFFIXES: frozenset[str] = frozenset({".yaml", ".yml"})

#: Directory names under ``docs/`` that name a document type, matched against
#: the segment directly under the documentation root. Both spellings of
#: post-mortem, because a real repository holds both.
TYPE_DIRECTORIES: dict[str, DocumentType] = {
    "runbook": DocumentType.RUNBOOK,
    "runbooks": DocumentType.RUNBOOK,
    "postmortem": DocumentType.POSTMORTEM,
    "postmortems": DocumentType.POSTMORTEM,
    "post-mortem": DocumentType.POSTMORTEM,
    "post-mortems": DocumentType.POSTMORTEM,
    "adr": DocumentType.ARCHITECTURE,
    "adrs": DocumentType.ARCHITECTURE,
    "architecture": DocumentType.ARCHITECTURE,
    "procedures": DocumentType.PROCEDURE,
}


def classify(relative: str) -> DocumentType:
    """Return the type a corpus path implies.

    Anything under the policy root is policy. Under the documentation root the
    first segment decides, and a segment nobody anticipated is a reference
    rather than a runbook — ``docs/analysis/`` and ``docs/prd/`` are context,
    and arriving as a procedure is how an agent comes to follow one.
    """
    parts = PurePosixPath(relative).parts
    if not parts:
        return DocumentType.REFERENCE
    if parts[0] == CORPUS_POLICY_ROOT:
        return DocumentType.POLICY
    if len(parts) > 2:
        found = TYPE_DIRECTORIES.get(parts[1].lower())
        if found is not None:
            return found
    return DocumentType.REFERENCE


def title_of(body: str, relative: str) -> str:
    """Return a document's title: its first heading, or its filename.

    The first heading, because that is what the author called it and what a
    citation should say. Headings are only read out of Markdown: ``#`` opens a
    comment in YAML, and a rule set whose first line explains the file would
    otherwise be titled with that explanation.
    """
    path = PurePosixPath(relative)
    if path.suffix.lower() in MARKDOWN_SUFFIXES:
        for line in body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return path.stem.replace("_", " ").strip()


@dataclass(slots=True)
class CorpusSource:
    """One repository's documentation and policy, as documents.

    ``skipped`` is populated by ``fetch`` and is a list rather than a count: an
    entry is a file somebody has to split, and a report saying "two skipped"
    is one nobody can act on.
    """

    root: Path
    #: Prefixed to a document's path to build its URL — a repository browse
    #: link, so a citation is clickable. Without one the citation is the
    #: repository-relative path, which is still something an operator can open.
    base_url: str = ""
    #: What this corpus's documents are namespaced under. A deployment reading
    #: two clusters' repositories names the second one.
    name: str = SOURCE
    #: Pulls a post-mortem's structure out once, here, rather than at each
    #: search. Absent means the corpus is ingested as text alone, which is what
    #: every source but this one does.
    extractor: PostmortemExtractor | None = None
    max_files: int = MAX_CORPUS_FILES
    max_file_bytes: int = MAX_CORPUS_FILE_BYTES
    #: One per file the bounds or the encoding put out of reach, as
    #: ``(path, reason)``.
    skipped: list[tuple[str, str]] = field(default_factory=list, init=False)

    def readable(self) -> tuple[PurePosixPath, ...]:
        """Return every path this source will open, in a stable order.

        Sorted, because a filesystem promises no order and two syncs of an
        unchanged tree have to produce the same report. Raises
        ``CorpusBoundExceeded`` above ``max_files``.
        """
        found = sorted(self._allowed(), key=lambda path: path.as_posix())
        if len(found) > self.max_files:
            raise CorpusBoundExceeded(
                parameter=f"the corpus at {self.root}",
                requested=len(found),
                limit=self.max_files,
                constant="MAX_CORPUS_FILES",
            )
        return tuple(found)

    async def fetch(self) -> Sequence[SourceDocument]:
        """Return the corpus as source documents, in path order.

        A file that cannot be decoded or is past the size ceiling is recorded in
        ``skipped`` rather than raising: one binary file that happens to end in
        ``.md`` must not stop sixty-six runbooks syncing, and the report names
        it so somebody can look.

        Post-mortem extraction happens here, on the way in, and the recurrence
        pass runs over the whole set afterwards — it is the one derived fact
        that needs two documents to be true, and neither of them knows about the
        other on its own.
        """
        self.skipped.clear()
        found: list[SourceDocument] = []
        extracted: dict[str, PostmortemFields] = {}

        for relative in self.readable():
            body = self._read(relative)
            if body is None or not body.strip():
                continue
            external_id = relative.as_posix()
            if self.extractor is not None and classify(external_id) is DocumentType.POSTMORTEM:
                extracted[external_id] = await self.extractor.extract(body, document=external_id)
            found.append(
                SourceDocument(
                    external_id=external_id,
                    title=title_of(body, external_id),
                    body=body,
                    source_uri=self._link(external_id),
                    document_type=classify(external_id),
                    updated_at=_modified(self.root / relative),
                )
            )

        found = _with_metadata(found, extracted)

        logger.info(
            "knowledge.corpus_fetched",
            source=self.name,
            documents=len(found),
            skipped=len(self.skipped),
            root=str(self.root),
        )
        return tuple(found)

    # -- internals -------------------------------------------------------------

    def _allowed(self) -> list[PurePosixPath]:
        """Return the allowlisted paths, relative to the root, unordered."""
        found: list[PurePosixPath] = []
        for directory, suffixes in (
            (CORPUS_DOCUMENT_ROOT, MARKDOWN_SUFFIXES),
            (CORPUS_POLICY_ROOT, POLICY_SUFFIXES),
        ):
            base = self.root / directory
            if not base.is_dir():
                continue
            found.extend(
                PurePosixPath(directory) / path.relative_to(base).as_posix()
                for path in base.rglob("*")
                if path.is_file() and path.suffix.lower() in suffixes
            )
        return found

    def _read(self, relative: PurePosixPath) -> str | None:
        """Return one file's text, or ``None`` having recorded why not."""
        path = self.root / relative
        try:
            size = path.stat().st_size
        except OSError as failure:  # pragma: no cover — read a moment ago
            self.skipped.append((relative.as_posix(), str(failure)))
            return None

        if size > self.max_file_bytes:
            self.skipped.append(
                (
                    relative.as_posix(),
                    f"{size} bytes is above the {self.max_file_bytes} one corpus file may "
                    f"carry, which is MAX_CORPUS_FILE_BYTES. Split it into the sections a "
                    f"reader would follow.",
                )
            )
            logger.info("knowledge.corpus_file_too_large", path=relative.as_posix(), bytes=size)
            return None

        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as failure:
            self.skipped.append((relative.as_posix(), str(failure)))
            logger.info(
                "knowledge.corpus_file_unreadable", path=relative.as_posix(), error=str(failure)
            )
            return None

    def _link(self, relative: str) -> str:
        """Return a browse URL for a path, or the repository-relative path."""
        return f"{self.base_url.rstrip('/')}/{relative}" if self.base_url else relative


def _with_metadata(
    found: list[SourceDocument],
    extracted: dict[str, PostmortemFields],
) -> list[SourceDocument]:
    """Return ``found`` carrying its extractions, recurrence pairs joined.

    A second pass rather than a field set during the walk, because a recurrence
    is true of two documents and the first of them is already built by the time
    the second names it.
    """
    if not extracted:
        return found
    metadata = resolve_recurrences(extracted, [entry.external_id for entry in found])
    return [
        replace(entry, metadata=metadata[entry.external_id])
        if metadata.get(entry.external_id)
        else entry
        for entry in found
    ]


def _modified(path: Path) -> datetime | None:
    """Return the file's modification time, or ``None`` if it cannot be read."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:  # pragma: no cover — the file was read a moment ago
        return None


__all__ = [
    "MARKDOWN_SUFFIXES",
    "POLICY_SUFFIXES",
    "SOURCE",
    "TYPE_DIRECTORIES",
    "CorpusSource",
    "classify",
    "title_of",
]
