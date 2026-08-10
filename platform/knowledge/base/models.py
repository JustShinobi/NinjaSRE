"""A team's documentation, as this tier reasons about it, and the stored shapes.

Two pairs of types with similar names exist and the difference matters.
``platform.persistence.ports.knowledge_store`` holds the *stored* records —
``KnowledgeDocument`` and ``KnowledgeChunk``, a title, a checksum, an ordinal, a
blob of text, and an untyped metadata bag. ``Document`` and ``Chunk`` here are
the *domain* records: a type, a place in the team's hierarchy, a version, an
origin, and — on a chunk — the section it came from and where in the source it
starts. This module owns the translation, in one place, so the storage layer
never learns what a runbook is and nothing above it has to remember which fields
live in the metadata bag.

Three definitions are load-bearing.

**A chunk knows its section, and that is what makes a result citable** (FR-013).
A passage returned without the heading it sat under is a passage the agent has to
paraphrase, and a paraphrase of a procedure is a procedure nobody wrote. The
section, the document, and a resolvable location travel with every chunk from
ingestion through to the model's context.

**``origin`` is attribution, not provenance trivia.** A document the agent
proposed and a human approved reads differently from one an engineer wrote, and
a reader who cannot tell which is which has no way to weigh it. Article III's
review requirement would be worth much less if the result of a review were
indistinguishable from an original.

**A version supersedes; it does not accumulate.** Re-ingesting a runbook whose
middle section was deleted must not leave that section retrievable — confident,
well-embedded, and describing a procedure that no longer exists. One document id,
one live body, a version counter that says how many times it has moved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from hashlib import blake2b
from typing import Any

from platform.persistence.ports.knowledge_store import KnowledgeChunk, KnowledgeDocument

#: Keys this tier keeps inside the stored metadata bag. Named constants for the
#: same reason the topology property keys are: the writer and the reader are
#: different modules, and a key spelled two ways reads back as an absent value
#: rather than failing.
TEAM_KEY = "team_node_id"
DOCUMENT_TYPE_KEY = "document_type"
ORIGIN_KEY = "origin"
PARENT_KEY = "parent_id"
VERSION_KEY = "version"
TAGS_KEY = "tags"
ATTRIBUTION_KEY = "attribution"
#: Where a document's derived facts sit inside the stored metadata bag. One key
#: holding a sub-mapping rather than fields spread across the bag, so reading
#: them back is a lookup instead of a list of names this module has to keep in
#: step with whatever last wrote one.
EXTRA_KEY = "extra"
SECTION_KEY = "section"
START_KEY = "start"
END_KEY = "end"

#: Length of the hex checksum a document is fingerprinted with. Sixteen
#: characters is far past collision risk for one team's corpus and short enough
#: to read in a sync log.
CHECKSUM_LENGTH = 16

#: Separates the levels of a section path — ``Recovery > Restart the pods``. A
#: path rather than the nearest heading, because "Restart the pods" alone is an
#: instruction whose preconditions were in the heading above it.
SECTION_SEPARATOR = " > "


class DocumentType(StrEnum):
    """What kind of document this is (FR-010).

    The kinds are read differently by anyone using them, and the difference is
    worth carrying into the model's context. A runbook is a procedure to follow,
    a post-mortem is a record of one past failure, an architecture note
    describes intent, and a procedure is an operational routine. An agent that
    cannot tell a post-mortem from a runbook will follow the post-mortem.

    ``POLICY`` and ``REFERENCE`` were added when a real repository's
    documentation was first ingested, and each earns its place by being read
    differently rather than by being filed differently. A firewall rule set is
    *enforced*: what it says is true of the network right now, which is the
    opposite of a runbook's "this was true when it was written", and an agent
    that treats one as the other will propose a change the packet filter has
    already refused. A reference document — a capacity review, a migration plan,
    a requirements note — is context and is the one kind an agent must not
    follow at all; without a name of its own it would arrive as a runbook,
    which is the default and the worst available answer for it.
    """

    RUNBOOK = "runbook"
    POSTMORTEM = "postmortem"
    ARCHITECTURE = "architecture"
    PROCEDURE = "procedure"
    POLICY = "policy"
    REFERENCE = "reference"

    @classmethod
    def parse(cls, value: str) -> DocumentType:
        """Return the type ``value`` names, or ``RUNBOOK``.

        An unrecognised type degrades rather than raising: a sync source that
        labels its pages with a vocabulary nobody anticipated should still get
        its documents ingested, and the commonest kind is the safe default.
        """
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.RUNBOOK


class DocumentOrigin(StrEnum):
    """Where a document came from, as the reader is told it (FR-019).

    ``AGENT_PROPOSED`` only ever appears on a document a human approved — there
    is no path that writes one otherwise — so it means "agent-originated,
    human-approved" rather than "written by a machine and trusted".
    """

    OPERATOR = "operator"
    SYNC = "sync"
    AGENT_PROPOSED = "agent_proposed"

    @classmethod
    def parse(cls, value: str) -> DocumentOrigin:
        """Return the origin ``value`` names, or ``OPERATOR``."""
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.OPERATOR


def checksum_of(text: str) -> str:
    """Return the fingerprint re-ingestion compares to decide whether to work.

    A document whose checksum has not moved needs no re-chunking and no
    re-embedding, which is the difference between a nightly sync of a hundred
    runbooks costing a hundred embedding passes and costing the two that changed.
    """
    return blake2b(text.encode("utf-8"), digest_size=CHECKSUM_LENGTH // 2).hexdigest()


def _tags(values: Iterable[str] | None) -> tuple[str, ...]:
    """Return ``values`` stripped, de-duplicated, in first-seen order."""
    seen: dict[str, None] = {}
    for value in values or ():
        text = str(value).strip()
        if text:
            seen.setdefault(text, None)
    return tuple(seen)


def _extra(value: Any) -> Mapping[str, Any]:
    """Return the derived-facts bag a stored record carries, or an empty one.

    A row written before this key existed reads as "nothing was derived" rather
    than raising, which is what lets a corpus ingested by an earlier version
    still be searched.
    """
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True, slots=True)
class Document:
    """One document as the team owns it: typed, placed, versioned, attributed."""

    document_id: str
    org_id: str
    team_node_id: str
    title: str
    body: str = ""
    document_type: DocumentType = DocumentType.RUNBOOK
    origin: DocumentOrigin = DocumentOrigin.OPERATOR
    source_uri: str = ""
    parent_id: str = ""
    version: int = 1
    tags: tuple[str, ...] = ()
    attribution: str = ""
    updated_at: datetime | None = None
    #: Facts derived from the body once, at ingestion, rather than at each
    #: search — a post-mortem's root cause, the entry it recurs from. Kept out
    #: of the checksum on purpose: the body is what makes a version, and an
    #: extractor that improved would otherwise supersede a corpus nobody edited.
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("a document must have an id")
        if not self.org_id or not self.team_node_id:
            raise ValueError(
                f"{self.document_id}: a document must carry an organisation and a team — "
                "an unscoped document is one every team can retrieve"
            )
        if not self.title.strip():
            raise ValueError(f"{self.document_id}: a document must have a title")
        object.__setattr__(self, "document_id", self.document_id.strip())
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "tags", _tags(self.tags))

    @property
    def checksum(self) -> str:
        """Return the fingerprint of this document's body."""
        return checksum_of(self.body)

    @property
    def location(self) -> str:
        """Return where a reader goes to find this document (FR-013).

        The source URI when the document came from somewhere with one, and an
        internal reference otherwise. Never blank: a citation whose location is
        an empty string is a citation the reader cannot check, which is the whole
        thing citations exist to prevent.
        """
        return self.source_uri.strip() or f"knowledge:{self.document_id}"

    def superseded_by(self, body: str, *, at: datetime | None = None) -> Document:
        """Return this document carrying ``body`` as its next version.

        The identity is kept and the version moves. Ingesting a changed runbook
        as a *new* document would leave both retrievable, and a search returning
        two versions of one procedure is a search that has told the agent to
        follow whichever it read first.
        """
        return replace(self, body=body, version=self.version + 1, updated_at=at)

    def to_stored(self) -> KnowledgeDocument:
        """Return this document in the shape ``KnowledgeStore`` persists."""
        return KnowledgeDocument(
            document_id=self.document_id,
            title=self.title,
            checksum=self.checksum,
            source_uri=self.source_uri or None,
            updated_at=self.updated_at,
            metadata={
                TEAM_KEY: self.team_node_id,
                DOCUMENT_TYPE_KEY: self.document_type.value,
                ORIGIN_KEY: self.origin.value,
                PARENT_KEY: self.parent_id,
                VERSION_KEY: self.version,
                TAGS_KEY: list(self.tags),
                ATTRIBUTION_KEY: self.attribution,
                EXTRA_KEY: dict(self.metadata),
            },
        )

    @classmethod
    def from_stored(cls, stored: KnowledgeDocument, *, org_id: str, body: str = "") -> Document:
        """Return the domain document a stored record describes.

        ``org_id`` comes from the unit of work rather than from the row: no port
        method takes an organisation, so the only honest source for it is the
        scope the row was read under. ``body`` is likewise not stored — the
        chunks are the retrievable form — so a caller that needs the text passes
        what it has.
        """
        metadata: Mapping[str, Any] = stored.metadata
        return cls(
            document_id=stored.document_id,
            org_id=org_id,
            team_node_id=str(metadata.get(TEAM_KEY, "")),
            title=stored.title,
            body=body,
            document_type=DocumentType.parse(str(metadata.get(DOCUMENT_TYPE_KEY, ""))),
            origin=DocumentOrigin.parse(str(metadata.get(ORIGIN_KEY, ""))),
            source_uri=stored.source_uri or "",
            parent_id=str(metadata.get(PARENT_KEY, "")),
            version=int(metadata.get(VERSION_KEY, 1)),
            tags=_tags(metadata.get(TAGS_KEY)),
            attribution=str(metadata.get(ATTRIBUTION_KEY, "")),
            updated_at=stored.updated_at,
            metadata=_extra(metadata.get(EXTRA_KEY)),
        )


@dataclass(frozen=True, slots=True)
class Chunk:
    """One retrievable passage, with everything a citation needs attached.

    ``start`` and ``end`` are character offsets into the document body. They are
    what lets ingestion report *where* a rejected document's secret was without
    quoting it, and what lets a console show a retrieved passage in place.
    """

    chunk_id: str
    document_id: str
    ordinal: int
    text: str
    section: str = ""
    start: int = 0
    end: int = 0

    def __post_init__(self) -> None:
        if not self.chunk_id.strip():
            raise ValueError("a chunk must have an id")
        if self.end < self.start:
            raise ValueError(
                f"{self.chunk_id}: a chunk cannot end ({self.end}) before it starts ({self.start})"
            )

    def to_stored(self) -> KnowledgeChunk:
        """Return this chunk in the shape ``KnowledgeStore`` persists."""
        return KnowledgeChunk(
            chunk_id=self.chunk_id,
            document_id=self.document_id,
            ordinal=self.ordinal,
            text=self.text,
            metadata={SECTION_KEY: self.section, START_KEY: self.start, END_KEY: self.end},
        )

    @classmethod
    def from_stored(cls, stored: KnowledgeChunk) -> Chunk:
        """Return the domain chunk a stored record describes."""
        metadata: Mapping[str, Any] = stored.metadata
        return cls(
            chunk_id=stored.chunk_id,
            document_id=stored.document_id,
            ordinal=stored.ordinal,
            text=stored.text,
            section=str(metadata.get(SECTION_KEY, "")),
            start=int(metadata.get(START_KEY, 0)),
            end=int(metadata.get(END_KEY, 0)),
        )

    def vector_metadata(self, document: Document) -> dict[str, Any]:
        """Return what a similarity search filters on without a second read.

        The team is here because the filter is the cheap half of team scoping:
        the organisation boundary is already structural — no port method takes an
        org — and this narrows within it before any row is loaded. The document
        type is here because an agent looking for a procedure and an agent
        reading post-mortems are asking different questions.
        """
        return {
            TEAM_KEY: document.team_node_id,
            "document_id": self.document_id,
            DOCUMENT_TYPE_KEY: document.document_type.value,
            SECTION_KEY: self.section,
        }


@dataclass(frozen=True, slots=True)
class Citation:
    """Where a retrieved passage came from, in the form the agent quotes.

    Assembled once, at retrieval, rather than formatted at each of the three
    places that show a result — the model's context, the trace, and the console.
    Three formatters is how a citation comes to name a section the passage is not
    in.
    """

    document_id: str
    title: str
    section: str
    location: str
    document_type: DocumentType = DocumentType.RUNBOOK
    origin: DocumentOrigin = DocumentOrigin.OPERATOR
    updated_at: datetime | None = None

    @property
    def reference(self) -> str:
        """Return the one-line reference an evidence entry carries."""
        return f"{self.location}#{self.section}" if self.section else self.location


@dataclass(frozen=True, slots=True)
class TreeNode:
    """One document's place in the team's hierarchy, with its children (FR-012).

    Built on demand from the documents' ``parent_id`` rather than stored as a
    structure. The hierarchy is a view for humans navigating a corpus; search
    spans the whole tree regardless, so storing it would be storing a second
    thing to keep in agreement with the first.
    """

    document: Document
    children: tuple[TreeNode, ...] = field(default_factory=tuple)

    @property
    def document_id(self) -> str:
        """Return the id of the document at this node."""
        return self.document.document_id

    def walk(self, depth: int = 0) -> Iterable[tuple[TreeNode, int]]:
        """Yield this node and every descendant, with its depth, parents first."""
        yield self, depth
        for child in self.children:
            yield from child.walk(depth + 1)

    def count(self) -> int:
        """Return how many documents this subtree holds, including this one."""
        return sum(1 for _ in self.walk())


def chunks_from_stored(stored: Sequence[KnowledgeChunk]) -> tuple[Chunk, ...]:
    """Return stored chunks as domain chunks, in order."""
    return tuple(Chunk.from_stored(chunk) for chunk in stored)


__all__ = [
    "ATTRIBUTION_KEY",
    "CHECKSUM_LENGTH",
    "DOCUMENT_TYPE_KEY",
    "END_KEY",
    "EXTRA_KEY",
    "ORIGIN_KEY",
    "PARENT_KEY",
    "SECTION_KEY",
    "SECTION_SEPARATOR",
    "START_KEY",
    "TAGS_KEY",
    "TEAM_KEY",
    "VERSION_KEY",
    "Chunk",
    "Citation",
    "Document",
    "DocumentOrigin",
    "DocumentType",
    "TreeNode",
    "checksum_of",
    "chunks_from_stored",
]
