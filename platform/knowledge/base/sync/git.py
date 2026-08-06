"""Markdown in a repository, as a document source.

The one adapter that needs no vendor at all: point it at a checked-out working
tree and it reads the Markdown. That makes it the source most teams should start
with, and it is the reason it ships alongside three hosted ones — documentation
that lives beside the code is reviewed with the code, versioned with the code,
and does not drift out of date in a wiki nobody opens.

Three decisions:

**The path is the identity, and the identity is stable.** A document's external
id is its path relative to the root, so moving a file supersedes nothing and
creates a new document — which is correct, because a moved runbook is one
somebody deliberately re-filed, and the old path stops existing on the next sync.

**The directory tree is the document tree, where a directory has an index.**
``runbooks/payments/failover.md`` hangs under ``runbooks/payments/README.md``
when that file exists, so the hierarchy an operator already made with folders
survives without them declaring it twice. Where there is no index file, the
document is a root — hanging it under a directory that is not itself a document
would put a parent in the tree that nobody can open.

**The type comes from the path.** A file under ``postmortems/`` is a post-mortem.
Reading it from front matter would be more precise and would require every
existing file to be edited before the first sync is useful.

Nothing here executes git. A repository is a directory on disk by the time this
runs, cloned or checked out by whatever the deployment already uses — which keeps
a subprocess, a credential, and a network call out of tier 3.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from platform.knowledge.base.models import DocumentType
from platform.knowledge.base.sync.port import SourceDocument
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The name this source's documents are namespaced under.
SOURCE = "git"

#: Extensions read as Markdown. Anything else in the tree is ignored rather than
#: guessed at: a ``.py`` file ingested as documentation is a runbook made of code.
MARKDOWN_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown"})

#: Directory names that name a document type. Matched against any path segment,
#: so ``docs/postmortems/2026/checkout.md`` is a post-mortem.
TYPE_DIRECTORIES: dict[str, DocumentType] = {
    "runbooks": DocumentType.RUNBOOK,
    "postmortems": DocumentType.POSTMORTEM,
    "post-mortems": DocumentType.POSTMORTEM,
    "architecture": DocumentType.ARCHITECTURE,
    "adr": DocumentType.ARCHITECTURE,
    "procedures": DocumentType.PROCEDURE,
}

#: Directories never walked into. Nothing under them is documentation, and
#: ``.git`` in particular holds a copy of every version of every file.
SKIPPED_DIRECTORIES: frozenset[str] = frozenset({".git", "node_modules", ".venv", "__pycache__"})


@dataclass(slots=True)
class GitMarkdownSource:
    """Markdown files in a checked-out repository, as documents."""

    root: Path
    #: Prefixed to a document's path to build its URL — a repository browse link,
    #: so a citation is clickable. Without one, the location falls back to the
    #: internal reference, which is still resolvable and merely less convenient.
    base_url: str = ""
    subdirectory: str = ""
    _root: Path = field(init=False)

    def __post_init__(self) -> None:
        self._root = (
            (self.root / self.subdirectory).resolve()
            if self.subdirectory
            else (self.root.resolve())
        )

    @property
    def name(self) -> str:
        """Return the identifier this source's documents are namespaced under."""
        return SOURCE

    async def fetch(self) -> Sequence[SourceDocument]:
        """Return the tree's Markdown files as source documents, path order.

        Sorted, so two syncs of an unchanged tree produce the same order and a
        diff of two runs is readable. A file that cannot be decoded is skipped
        with a log line rather than failing the run: one binary file that
        happens to end in ``.md`` must not stop a hundred runbooks syncing.
        """
        files = sorted(self._markdown_files())
        paths = {path.relative_to(self._root).as_posix() for path in files}

        found: list[SourceDocument] = []
        for path in files:
            relative = path.relative_to(self._root).as_posix()
            try:
                body = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as failure:
                logger.info("knowledge.git_file_unreadable", path=relative, error=str(failure))
                continue
            if not body.strip():
                continue

            found.append(
                SourceDocument(
                    external_id=relative,
                    title=title_of(body, relative),
                    body=body,
                    source_uri=self._link(relative),
                    document_type=type_of(relative),
                    parent_external_id=parent_of(relative, paths),
                    updated_at=_modified(path),
                )
            )

        logger.info("knowledge.git_fetched", documents=len(found), root=str(self._root))
        return tuple(found)

    def _markdown_files(self) -> list[Path]:
        """Return every Markdown file under the root, skipping vendored trees."""
        if not self._root.is_dir():
            logger.warning("knowledge.git_root_missing", root=str(self._root))
            return []
        return [
            path
            for path in self._root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in MARKDOWN_SUFFIXES
            and not SKIPPED_DIRECTORIES.intersection(path.relative_to(self._root).parts)
        ]

    def _link(self, relative: str) -> str:
        """Return a browse URL for a path, or ``""`` when none was configured."""
        return f"{self.base_url.rstrip('/')}/{relative}" if self.base_url else ""


def title_of(body: str, relative: str) -> str:
    """Return a document's title: its first heading, or its filename.

    The first heading, because that is what the author called it and what a
    citation should say. The filename is the fallback rather than an error —
    plenty of real documentation starts with a paragraph.
    """
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return Path(relative).stem.replace("-", " ").replace("_", " ").strip()


def type_of(relative: str) -> DocumentType:
    """Return the document type a path implies, or a runbook."""
    for part in Path(relative).parts:
        found = TYPE_DIRECTORIES.get(part.lower())
        if found is not None:
            return found
    return DocumentType.RUNBOOK


#: Filenames that make a directory a document in its own right, in the order
#: they are tried. Both are conventions a repository already uses for exactly
#: this — the page you land on when you open the folder.
INDEX_FILENAMES: tuple[str, ...] = ("README.md", "index.md")


def parent_of(relative: str, paths: set[str]) -> str:
    """Return the index document a file hangs under, or ``""``.

    Walks upward, so a file in a directory with no index still finds the nearest
    ancestor that has one. Never returns the file itself: an index document is
    a root rather than its own parent.
    """
    directory = Path(relative).parent
    while True:
        for filename in INDEX_FILENAMES:
            candidate = (directory / filename).as_posix()
            if candidate in paths and candidate != relative:
                return candidate
        if directory.as_posix() in {"", "."}:
            return ""
        directory = directory.parent


def _modified(path: Path) -> datetime | None:
    """Return the file's modification time, or ``None`` if it cannot be read."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:  # pragma: no cover — the file was read a moment ago
        return None


__all__ = [
    "INDEX_FILENAMES",
    "MARKDOWN_SUFFIXES",
    "SKIPPED_DIRECTORIES",
    "SOURCE",
    "TYPE_DIRECTORIES",
    "GitMarkdownSource",
    "parent_of",
    "title_of",
    "type_of",
]
