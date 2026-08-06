"""Cutting a document into passages a search can return and a reader can trust.

Chunking is where retrieval quality is actually decided, and the failure it has
to avoid is specific: **a passage that changes meaning when separated from what
surrounded it.** A runbook that says "if the replica is behind, fail over" split
between the condition and the instruction produces a chunk that reads as an
unconditional instruction to fail over. Nothing downstream can detect that, and
the agent will follow it.

Three mechanisms address it, and each is a bound rather than a heuristic.

**Cuts follow the document's own structure.** Sections come first: a chunk never
spans a heading, because a heading is the author's own statement that what
follows is a different subject. Within a section, cuts fall on paragraph
boundaries, then on sentence boundaries, and only then mid-text — and a mid-text
cut is a document that wrote one paragraph longer than the whole chunk budget.

**Chunks overlap.** ``CHUNK_OVERLAP_CHARS`` of the previous chunk's tail is
repeated at the head of the next, so a sentence that spans a boundary is whole in
at least one of them.

**Every chunk carries its section, both ways.** ``path`` is the breadcrumb a
citation shows — "Payments recovery > Emergency access" — because the preconditions
for a procedure are usually stated in the heading above it. ``title`` is the
nearest heading alone, which is what somebody looking for a line in the source
actually scans for.

Offsets are into the original body, unmodified. That is what lets ingestion
report *where* a rejected document's secret was without quoting it, and what lets
a console show a retrieved passage in place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config.constants.knowledge import (
    CHUNK_OVERLAP_CHARS,
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
)
from platform.knowledge.base.models import SECTION_SEPARATOR

#: A Markdown ATX heading: one to six hashes, a space, and the title. Setext
#: headings (underlined with ``===``) are not recognised, and that is a stated
#: limitation rather than an oversight — every tool that exports the documents
#: this ingests writes ATX.
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)

#: A paragraph break: a blank line, however much trailing whitespace it carries.
PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")

#: A sentence end, used only when one paragraph exceeds the whole chunk budget.
#: Deliberately crude: this is a fallback before a mid-word cut, not a linguistic
#: claim, and a cleverer rule here would be a second thing to be wrong about
#: abbreviations.
SENTENCE_END = re.compile(r"(?<=[.!?])[ \t]+")


@dataclass(frozen=True, slots=True)
class Section:
    """One heading and the text under it, with where it sits in the document."""

    title: str
    path: str
    level: int
    start: int
    end: int

    @property
    def empty(self) -> bool:
        """Return whether the section holds no text."""
        return self.end <= self.start


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One passage, its position, and the section it came from."""

    ordinal: int
    text: str
    section: str
    title: str
    start: int
    end: int

    def embedding_text(self) -> str:
        """Return what this chunk is embedded from.

        The section path leads. Two runbooks both containing "restart the pods"
        differ mostly in what they are about, and the heading is where a document
        says so — without it, a search for "payments recovery" matches every
        runbook that mentions restarting anything.
        """
        return f"{self.section}\n{self.text}" if self.section else self.text


def sections(body: str) -> tuple[Section, ...]:
    """Return the document's sections, in order, spanning the whole body.

    Text before the first heading is a section too, titled ``""``. A document
    with no headings at all is one section, which is the common case for a page
    exported from a wiki that keeps its title outside the body.
    """
    headings = list(HEADING.finditer(body))
    if not headings:
        return (Section(title="", path="", level=0, start=0, end=len(body)),)

    found: list[Section] = []
    if headings[0].start() > 0:
        found.append(Section(title="", path="", level=0, start=0, end=headings[0].start()))

    trail: list[tuple[int, str]] = []
    for position, match in enumerate(headings):
        level = len(match.group(1))
        title = match.group(2).strip()
        while trail and trail[-1][0] >= level:
            trail.pop()
        trail.append((level, title))

        end = headings[position + 1].start() if position + 1 < len(headings) else len(body)
        found.append(
            Section(
                title=title,
                path=SECTION_SEPARATOR.join(name for _, name in trail),
                level=level,
                # The body of a section starts after its heading line. The
                # heading itself is carried on the chunk as its path, and
                # repeating it in the text would put it in the model's context
                # twice for every chunk of a long section.
                start=match.end(),
                end=end,
            )
        )

    return tuple(found)


def section_at(body: str, offset: int) -> Section:
    """Return the section an offset falls in, for reporting a location.

    Used by ingestion to say where a rejected document's secret was. The nearest
    heading is what somebody scanning the source is looking for, which is why
    ``Section`` carries the bare title as well as the breadcrumb.
    """
    found = sections(body)
    for section in found:
        if section.start <= offset < section.end:
            return section
    return found[-1]


def line_at(body: str, offset: int) -> int:
    """Return the one-based line number an offset falls on."""
    return body.count("\n", 0, max(offset, 0)) + 1


def chunk_document(
    body: str,
    *,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap: int = CHUNK_OVERLAP_CHARS,
    minimum: int = MIN_CHUNK_CHARS,
) -> tuple[TextChunk, ...]:
    """Return ``body`` cut into overlapping, section-aware passages.

    The bounds are parameters rather than reads of the constants so a caller with
    a different embedding model can pass its own. They default to the shipped
    ones, which is what every caller in this repository uses.

    ``max_chars`` bounds the *stored passage*, overlap included. So the new text
    in each chunk is budgeted at ``max_chars - overlap``: the constant means what
    it says at the place the number matters, which is the embedder's input and
    the model's context, rather than at an intermediate the caller never sees.
    """
    if max_chars <= 0:
        raise ValueError(f"a chunk budget must be positive, got {max_chars}")
    if overlap >= max_chars:
        raise ValueError(
            f"an overlap of {overlap} within a {max_chars}-character chunk would repeat most "
            "of every passage; overlap must be smaller than the budget"
        )

    budget = max_chars - overlap
    chunks: list[TextChunk] = []
    for section in sections(body):
        text = body[section.start : section.end]
        if not text.strip():
            continue
        for start, end in _spans(text, max_chars=budget, minimum=minimum):
            head = _overlap_start(text, start, overlap)
            passage = text[head:end].strip()
            if not passage:
                continue
            # Offsets are recomputed against the stripped passage so a chunk's
            # span is exactly the text it carries. A citation that pointed at
            # leading whitespace would be off by a line as often as not.
            leading = text[head:end].index(passage[0]) if passage else 0
            chunks.append(
                TextChunk(
                    ordinal=len(chunks),
                    text=passage,
                    section=section.path,
                    title=section.title,
                    start=section.start + head + leading,
                    end=section.start + head + leading + len(passage),
                )
            )

    return tuple(chunks)


def _spans(text: str, *, max_chars: int, minimum: int) -> list[tuple[int, int]]:
    """Return the cut points for one section, before overlap is applied."""
    blocks = _blocks(text, max_chars=max_chars)
    spans: list[tuple[int, int]] = []

    for start, end in blocks:
        if not spans:
            spans.append((start, end))
            continue
        previous_start, _ = spans[-1]
        # Grow the previous chunk while it fits, which is what keeps a document
        # of short paragraphs from becoming a chunk per paragraph.
        if end - previous_start <= max_chars:
            spans[-1] = (previous_start, end)
        else:
            spans.append((start, end))

    return _widened_tail(spans, minimum)


def _widened_tail(spans: list[tuple[int, int]], minimum: int) -> list[tuple[int, int]]:
    """Return ``spans`` with a too-short final chunk grown backwards.

    A trailing fragment below the minimum matches everything weakly and nothing
    well, and it costs a retrieval slot to say so. It is *not* folded into the
    chunk before it, because that chunk is already at the budget and folding
    would push the stored passage past the bound the caller set. Instead the
    fragment reaches back over text the previous chunk also carries — which is
    what overlap is for, applied a little more generously at the one place it
    prevents a useless chunk.
    """
    if len(spans) < 2:
        return spans
    start, end = spans[-1]
    if end - start >= minimum:
        return spans
    spans[-1] = (max(spans[-2][0], end - minimum), end)
    return spans


def _blocks(text: str, *, max_chars: int) -> list[tuple[int, int]]:
    """Return the section's paragraphs, splitting any that exceed the budget."""
    blocks: list[tuple[int, int]] = []
    cursor = 0

    for match in PARAGRAPH_BREAK.finditer(text):
        blocks.extend(_bounded(text, cursor, match.start(), max_chars=max_chars))
        cursor = match.end()
    blocks.extend(_bounded(text, cursor, len(text), max_chars=max_chars))

    return [(start, end) for start, end in blocks if text[start:end].strip()]


def _bounded(text: str, start: int, end: int, *, max_chars: int) -> list[tuple[int, int]]:
    """Return one paragraph as spans no longer than the budget.

    Sentence boundaries first; a mid-text cut only for a paragraph with no
    sentence boundary inside the budget, which in practice is a table, a stack
    trace, or a base64 blob — none of which a cleverer rule would help.
    """
    if end - start <= max_chars:
        return [(start, end)]

    spans: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > max_chars:
        limit = cursor + max_chars
        boundary = _last_sentence_end(text, cursor, limit)
        cut = boundary if boundary > cursor else limit
        spans.append((cursor, cut))
        cursor = cut
    if cursor < end:
        spans.append((cursor, end))
    return spans


def _last_sentence_end(text: str, start: int, limit: int) -> int:
    """Return the last sentence boundary before ``limit``, or ``start``."""
    cut = start
    for match in SENTENCE_END.finditer(text, start, limit):
        cut = match.end()
    return cut


def _overlap_start(text: str, start: int, overlap: int) -> int:
    """Return where a chunk's text begins once the overlap is included.

    The overlap is taken back to a whitespace boundary where one is available, so
    a repeated tail begins at a word rather than mid-word — a chunk starting
    ``...ction refused`` reads as a different error than the one it repeats.
    """
    if start == 0 or overlap <= 0:
        return start
    head = max(0, start - overlap)
    space = text.rfind(" ", head, start)
    return space + 1 if space > head else head


__all__ = [
    "HEADING",
    "PARAGRAPH_BREAK",
    "SENTENCE_END",
    "Section",
    "TextChunk",
    "chunk_document",
    "line_at",
    "section_at",
    "sections",
]
