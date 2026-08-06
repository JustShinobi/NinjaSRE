"""Shaping a retrieved passage so the agent quotes it rather than absorbing it.

The whole difficulty of returning documentation to a language model is that a
passage in the context window is indistinguishable, by the time an answer is
written, from something the model worked out itself. A diagnosis that says "the
replica lag threshold is ten seconds" is a claim about production; the same
sentence attributed to a runbook is a claim about what somebody wrote down. Those
are different claims and only one of them is checkable.

So the citation leads every result. The document, the section, and a resolvable
location come before the text, the guidance asks the agent to reproduce them, and
the evidence entry carries the same reference so the trace can be walked back to
the source.

The **age** of a document is shown for the same reason a topology edge shows its
verification date. A runbook describes what was true when it was written, and a
procedure last touched two years ago is a lead rather than an instruction.

An agent-originated document says so. It reached the corpus through human review,
which is what makes it usable at all — and a reader who could not tell it from an
engineer's own writing would have no way to weigh it.
"""

from __future__ import annotations

from typing import Any

from config.prompts.knowledge import KNOWLEDGE_CHUNK, KNOWLEDGE_EMPTY, KNOWLEDGE_HEADER
from core.capability.metadata import EvidenceSource, EvidenceType
from core.capability.result import Evidence
from platform.knowledge.base.models import Citation, DocumentOrigin
from platform.knowledge.base.search import KnowledgeResult, RetrievedChunk

#: How an agent-originated document is labelled in the answer. Spelled out rather
#: than abbreviated, because "proposed" alone reads as "not yet approved" and the
#: opposite is true — nothing reaches the corpus without a human.
AGENT_ORIGIN_NOTE = "agent-originated, human-approved"

#: Prefixes the reference on a retrieved passage, so a reader can tell a document
#: citation from an observation made during this investigation.
KNOWLEDGE_REFERENCE_PREFIX = "knowledge"


def describe(found: RetrievedChunk, *, rank: int) -> str:
    """Return one retrieved passage as the model is shown it."""
    citation = found.citation
    return KNOWLEDGE_CHUNK.format(
        rank=rank,
        title=citation.title,
        section=citation.section or "the document body",
        document_type=_kind(citation),
        location=citation.reference,
        updated=citation.updated_at.date().isoformat() if citation.updated_at else "not recorded",
        text=found.chunk.text,
    )


def _kind(citation: Citation) -> str:
    """Return the document's kind, saying so when it came from the agent."""
    if citation.origin is DocumentOrigin.AGENT_PROPOSED:
        return f"{citation.document_type.value}, {AGENT_ORIGIN_NOTE}"
    return citation.document_type.value


def render(result: KnowledgeResult) -> str:
    """Return the whole search as one block of text, empty results included."""
    if result.empty:
        return KNOWLEDGE_EMPTY
    return "\n\n".join(
        (
            KNOWLEDGE_HEADER.format(count=len(result.chunks)),
            *(
                describe(found, rank=position)
                for position, found in enumerate(result.chunks, start=1)
            ),
        )
    )


def evidence_for(result: KnowledgeResult) -> tuple[Evidence, ...]:
    """Return one evidence entry per passage, referencing where it came from.

    The summary says what the thing *is* — a passage from a named document —
    rather than what it asserts. An entry reading "the replica lag threshold is
    ten seconds" would enter the trace as an observation, and a diagnosis citing
    it would be citing a runbook as though it were a measurement.
    """
    return tuple(
        Evidence(
            source=EvidenceSource.RUNBOOK
            if found.citation.document_type.value == "runbook"
            else EvidenceSource.KNOWLEDGE_BASE,
            evidence_type=EvidenceType.DOCUMENT,
            summary=(
                f"A passage from {found.citation.title!r} "
                f"({_kind(found.citation)}), section "
                f"{found.citation.section or 'the document body'}. It records what somebody "
                f"wrote down, not an observation of this incident."
            ),
            reference=found.citation.reference,
        )
        for found in result.chunks
    )


def shape(result: KnowledgeResult) -> dict[str, Any]:
    """Return the structured value the tool hands back.

    Both a rendered block and the structured passages. The text is what the model
    reads; the structure is what the trace, the console, and the evaluation
    harness read, and deriving one from the other afterwards is how the two come
    to disagree.
    """
    return {
        "query": result.query.text,
        "document_type": result.query.document_type,
        "count": len(result.chunks),
        "documents": list(result.documents),
        "text": render(result),
        "passages": [
            {
                "chunk_id": found.chunk.chunk_id,
                "document_id": found.citation.document_id,
                "title": found.citation.title,
                "section": found.citation.section,
                "location": found.citation.location,
                "reference": found.citation.reference,
                "document_type": found.citation.document_type.value,
                "origin": found.citation.origin.value,
                "updated_at": (
                    found.citation.updated_at.isoformat() if found.citation.updated_at else None
                ),
                "score": found.score,
                "text": found.chunk.text,
            }
            for found in result.chunks
        ],
    }


__all__ = [
    "AGENT_ORIGIN_NOTE",
    "KNOWLEDGE_REFERENCE_PREFIX",
    "describe",
    "evidence_for",
    "render",
    "shape",
]
