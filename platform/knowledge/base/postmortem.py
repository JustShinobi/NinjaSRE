"""What a post-mortem contributes beyond its text, extracted once.

A runbook is a procedure. A post-mortem is a *pair*: a symptom somebody saw and
a cause somebody eventually found, with the work between them written down. That
structure is the reason the ten post-mortems in a real repository are worth more
than the fifty-four runbooks beside them, and it is invisible to similarity
search — which returns the paragraph that reads most like the query, from
whichever of the two documents happens to phrase it best.

So the fields are pulled out **at ingestion, once per version**, and stored
beside the document. Doing it per search would be a model call on the hot path
of an investigation, to re-derive something that has not changed since the
document was written.

**Two extractors, in this order.** Headings first: the convention a team's
post-mortems already follow is free to read, deterministic, and cites the
section each field came from, which is what makes an extracted "root cause"
checkable. The model is asked only about the documents the headings missed —
in a real corpus, the ones somebody wrote at two in the morning — and its answer
is cached by the body's checksum, so the second sync of an unchanged corpus
makes no calls at all.

**A deployment with no provider still ingests.** Extraction degrades to
structural alone and the sync report names each document that lost its fields.
Silence would be indistinguishable from a corpus of post-mortems that never
established anything, which is a real and different situation.

**"Root cause" is a section, not a conclusion.** A document with a heading
called "Root cause" whose text says nobody found one has a section and no cause.
``explains`` is what ranking reads, and it is about the presence of a cause the
document actually names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.knowledge import MAX_POSTMORTEM_FIELD_CHARS, POSTMORTEM_EXTRACTION_MAX_TOKENS
from config.prompts.knowledge import (
    POSTMORTEM_EXTRACTION_FAILED,
    POSTMORTEM_EXTRACTION_REQUEST,
    POSTMORTEM_EXTRACTION_SYSTEM_PROMPT,
    POSTMORTEM_EXTRACTION_UNCONFIGURED,
)
from core.llm.types import InvokeRequest, LLMClient, Message, Role
from platform.knowledge.base.chunking import sections
from platform.knowledge.base.models import checksum_of
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The keys a post-mortem's derived facts are stored under, inside the
#: document's metadata bag. Named constants for the reason the topology property
#: keys are: the writer and the reader are different modules, and a key spelled
#: two ways reads back as an absent value rather than failing.
SYMPTOM_KEY = "symptom"
INVESTIGATION_KEY = "investigation"
ROOT_CAUSE_KEY = "root_cause"
CORRECTION_KEY = "correction"
RECURRENCE_OF_KEY = "recurrence_of"
#: The other direction, written by the corpus pass that can see both documents.
#: A list, because one failure can recur more than twice.
RECURRED_AS_KEY = "recurred_as"
#: Which field came from which heading, so an extracted claim is checkable.
SECTIONS_KEY = "sections"
#: ``structure``, ``model``, or absent. A deployment reading its own corpus
#: needs to know which fields a model wrote.
EXTRACTED_BY_KEY = "extracted_by"

#: The four fields a heading can supply, and the headings that supply them.
#: Both languages, because a real repository holds both — and the English
#: spellings alone would silently extract nothing from half a corpus, which
#: looks exactly like a corpus of post-mortems that establish nothing.
HEADING_ALIASES: dict[str, frozenset[str]] = {
    SYMPTOM_KEY: frozenset(
        {"symptom", "symptoms", "sintoma", "sintomas", "impact", "impacto", "what happened"}
    ),
    INVESTIGATION_KEY: frozenset(
        {
            "investigation",
            "investigação",
            "investigacao",
            "what was investigated",
            "timeline",
            "linha do tempo",
            "analysis",
            "análise",
            "analise",
        }
    ),
    ROOT_CAUSE_KEY: frozenset(
        {"root cause", "rootcause", "causa raiz", "causa-raiz", "cause", "causa"}
    ),
    CORRECTION_KEY: frozenset(
        {
            "correction",
            "correção",
            "correcao",
            "fix",
            "remediation",
            "resolution",
            "resolução",
            "what was done",
            "ação corretiva",
        }
    ),
    RECURRENCE_OF_KEY: frozenset(
        {
            "recurrence of",
            "recurrence-of",
            "recurrence",
            "recorrência de",
            "recorrencia de",
            "recorrência",
        }
    ),
}

#: What the model is asked to return. Every field is optional and defaulted: a
#: post-mortem that never found its cause should leave the field empty, and a
#: schema that made it required would get a guess in its place.
POSTMORTEM_EXTRACTION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        SYMPTOM_KEY: {
            "type": "string",
            "description": "What was observed to be wrong, as somebody watching would say it.",
        },
        INVESTIGATION_KEY: {
            "type": "string",
            "description": "What was looked at, in the order it was looked at.",
        },
        ROOT_CAUSE_KEY: {
            "type": "string",
            "description": (
                "The cause the document establishes. Empty when the document does not "
                "establish one — most post-mortems written in a hurry do not."
            ),
        },
        CORRECTION_KEY: {
            "type": "string",
            "description": "What was changed to make it stop, and to stop it returning.",
        },
        RECURRENCE_OF_KEY: {
            "type": "string",
            "description": (
                "The earlier entry this one repeats, if the document names one, as the "
                "document names it. Empty otherwise."
            ),
        },
    },
    "required": [],
}


@dataclass(frozen=True, slots=True)
class PostmortemFields:
    """One post-mortem's structure, as the corpus stores it."""

    symptom: str = ""
    investigation: str = ""
    root_cause: str = ""
    correction: str = ""
    #: What the document says it recurs from, as written. Resolved to a corpus
    #: path by the pass that can see the whole corpus, and left as written when
    #: nothing matches — a dangling reference is a fact about the corpus.
    recurrence_of: str = ""
    #: Field name to the heading it came from. Empty for a model extraction,
    #: which has no section to point at and must not pretend to.
    sections: Mapping[str, str] = field(default_factory=dict)
    #: ``structure``, ``model``, or empty when nothing was extracted.
    extracted_by: str = ""

    @property
    def empty(self) -> bool:
        """Return whether nothing was extracted."""
        return not any(
            (self.symptom, self.investigation, self.root_cause, self.correction, self.recurrence_of)
        )

    @property
    def explains(self) -> bool:
        """Return whether this document names a cause.

        What ranking reads. A heading called "Root cause" under which somebody
        wrote that none was established is a section and not a cause, so the
        text is checked for the phrases that say so before this returns true.
        """
        text = self.root_cause.strip()
        if not text:
            return False
        opening = text.lower()[:MAX_POSTMORTEM_FIELD_CHARS]
        return not any(phrase in opening for phrase in NO_CAUSE_PHRASES)


#: Openings that mean "this section exists and names no cause". Matched against
#: the text rather than inferred, because the alternative — treating any "Root
#: cause" heading as a cause — is what makes a search rank the entry that found
#: nothing above the one that found everything.
NO_CAUSE_PHRASES: frozenset[str] = frozenset(
    {
        "not established",
        "not determined",
        "unknown",
        "none established",
        "no root cause",
        "não estabelecida",
        "nao estabelecida",
        "desconhecida",
    }
)


def extraction_metadata(fields: PostmortemFields) -> dict[str, Any]:
    """Return what a document stores for ``fields``, or an empty bag.

    An empty extraction stores nothing at all rather than five empty strings: a
    metadata bag full of blanks is one every reader has to check twice.
    """
    if fields.empty:
        return {}
    stored: dict[str, Any] = {
        key: value
        for key, value in (
            (SYMPTOM_KEY, fields.symptom),
            (INVESTIGATION_KEY, fields.investigation),
            (ROOT_CAUSE_KEY, fields.root_cause),
            (CORRECTION_KEY, fields.correction),
            (RECURRENCE_OF_KEY, fields.recurrence_of),
        )
        if value
    }
    if fields.sections:
        stored[SECTIONS_KEY] = dict(fields.sections)
    if fields.extracted_by:
        stored[EXTRACTED_BY_KEY] = fields.extracted_by
    return stored


def fields_from_metadata(metadata: Mapping[str, Any]) -> PostmortemFields:
    """Return the fields a document's metadata bag carries.

    Reads defensively: a bag written by an earlier version, or by something
    else entirely, reads back as an empty extraction rather than raising in a
    search.
    """
    raw = metadata.get(SECTIONS_KEY)
    return PostmortemFields(
        symptom=_text(metadata.get(SYMPTOM_KEY)),
        investigation=_text(metadata.get(INVESTIGATION_KEY)),
        root_cause=_text(metadata.get(ROOT_CAUSE_KEY)),
        correction=_text(metadata.get(CORRECTION_KEY)),
        recurrence_of=_text(metadata.get(RECURRENCE_OF_KEY)),
        sections={str(key): str(value) for key, value in raw.items()}
        if isinstance(raw, Mapping)
        else {},
        extracted_by=_text(metadata.get(EXTRACTED_BY_KEY)),
    )


def structural_fields(body: str) -> PostmortemFields:
    """Return what ``body``'s headings say, without calling anything.

    The first section matching each alias wins. A document that repeats a
    heading has one of them as its answer, and the first is the one a reader
    would take.
    """
    found: dict[str, str] = {}
    origin: dict[str, str] = {}

    for section in sections(body):
        title = section.title.strip().lower().rstrip(":")
        if not title:
            continue
        for name, aliases in HEADING_ALIASES.items():
            if name in found or title not in aliases:
                continue
            text = body[section.start : section.end].strip()
            if text:
                found[name] = text[:MAX_POSTMORTEM_FIELD_CHARS]
                origin[name] = section.title.strip()

    if not found:
        return PostmortemFields()
    return PostmortemFields(
        symptom=found.get(SYMPTOM_KEY, ""),
        investigation=found.get(INVESTIGATION_KEY, ""),
        root_cause=found.get(ROOT_CAUSE_KEY, ""),
        correction=found.get(CORRECTION_KEY, ""),
        recurrence_of=found.get(RECURRENCE_OF_KEY, ""),
        sections=origin,
        extracted_by="structure",
    )


@dataclass(slots=True)
class PostmortemExtractor:
    """Structural extraction, with one bounded model call behind it.

    Stateful on purpose. The cache is keyed by the body's checksum, which is the
    same key ingestion uses to decide whether a document moved, so a re-sync of
    an unchanged corpus makes zero calls. ``degradations`` accumulates the
    documents that wanted the model and did not get it, for the sync report.
    """

    #: Absent means "no provider is configured", which is a supported
    #: deployment and not an error.
    llm: LLMClient | None = None
    cache: dict[str, PostmortemFields] = field(default_factory=dict)
    _degradations: list[str] = field(default_factory=list, init=False)

    @property
    def degradations(self) -> tuple[str, ...]:
        """Return one sentence per document that was read without the model."""
        return tuple(self._degradations)

    async def extract(self, body: str, *, document: str) -> PostmortemFields:
        """Return ``body``'s fields, asking the model only when headings found none.

        Never raises. A provider that cannot be reached costs this document its
        fields and is recorded; it does not cost the corpus its sync.
        """
        structural = structural_fields(body)
        if not structural.empty:
            return structural

        checksum = checksum_of(body)
        cached = self.cache.get(checksum)
        if cached is not None:
            return cached

        found = await self._from_model(body, document=document)
        self.cache[checksum] = found
        return found

    async def _from_model(self, body: str, *, document: str) -> PostmortemFields:
        """Return what one structured call says, or an empty extraction and a reason."""
        if self.llm is None:
            self._degradations.append(POSTMORTEM_EXTRACTION_UNCONFIGURED.format(document=document))
            return PostmortemFields()

        try:
            result = await self.llm.invoke_structured(
                InvokeRequest(
                    messages=(
                        Message(
                            role=Role.USER,
                            text=POSTMORTEM_EXTRACTION_REQUEST.format(document=body),
                        ),
                    ),
                    system=POSTMORTEM_EXTRACTION_SYSTEM_PROMPT,
                    max_output_tokens=POSTMORTEM_EXTRACTION_MAX_TOKENS,
                ),
                POSTMORTEM_EXTRACTION_SCHEMA,
            )
        except Exception as error:  # noqa: BLE001 — extraction must never fail a sync
            failure = f"{type(error).__name__}: {error}"
            logger.warning(
                "knowledge.postmortem_extraction_failed", document=document, error=failure
            )
            self._degradations.append(
                POSTMORTEM_EXTRACTION_FAILED.format(document=document, failure=failure)
            )
            return PostmortemFields()

        if not result.succeeded or result.structured is None:
            failure = result.failure_message or "no structured object was returned"
            logger.warning(
                "knowledge.postmortem_extraction_empty", document=document, failure=failure
            )
            self._degradations.append(
                POSTMORTEM_EXTRACTION_FAILED.format(document=document, failure=failure)
            )
            return PostmortemFields()

        return _from_structured(result.structured)


def resolve_recurrences(
    extracted: Mapping[str, PostmortemFields],
    paths: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Return each document's stored metadata, with the recurrence pair joined.

    Both directions are written. A search for the symptom finds whichever entry
    the wording favours, and from either one the other is a lookup rather than a
    second search — which is the whole value of a pair where the second entry
    holds the cause the first one missed.

    A reference to a document the corpus does not hold is left exactly as the
    author wrote it. Dropping it would hide the fact that the corpus is missing
    a document somebody else's document points at.
    """
    by_stem = _index(paths)
    metadata = {path: extraction_metadata(fields) for path, fields in extracted.items()}
    recurred: dict[str, list[str]] = {}

    for path, fields in extracted.items():
        target = _resolve(fields.recurrence_of, by_stem)
        if not target or target == path:
            continue
        metadata[path][RECURRENCE_OF_KEY] = target
        recurred.setdefault(target, []).append(path)

    for target, entries in recurred.items():
        bag = metadata.setdefault(target, {})
        bag[RECURRED_AS_KEY] = sorted(entries)

    return metadata


def _index(paths: Sequence[str]) -> dict[str, str]:
    """Return a lookup from a document's own path and its stem to its path."""
    found: dict[str, str] = {}
    for path in paths:
        found.setdefault(path, path)
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        found.setdefault(stem, path)
    return found


def _resolve(reference: str, by_stem: Mapping[str, str]) -> str:
    """Return the corpus path ``reference`` names, or ``""``."""
    text = reference.strip().strip("`").strip()
    if not text:
        return ""
    return by_stem.get(text, by_stem.get(text.rsplit("/", 1)[-1].rsplit(".", 1)[0], ""))


def _from_structured(document: Mapping[str, Any]) -> PostmortemFields:
    """Return the fields a structured reply describes, read one at a time.

    Every field is read defensively. A model that returned a list where a string
    was asked for should cost that field, not the document.
    """
    fields = PostmortemFields(
        symptom=_text(document.get(SYMPTOM_KEY))[:MAX_POSTMORTEM_FIELD_CHARS],
        investigation=_text(document.get(INVESTIGATION_KEY))[:MAX_POSTMORTEM_FIELD_CHARS],
        root_cause=_text(document.get(ROOT_CAUSE_KEY))[:MAX_POSTMORTEM_FIELD_CHARS],
        correction=_text(document.get(CORRECTION_KEY))[:MAX_POSTMORTEM_FIELD_CHARS],
        recurrence_of=_text(document.get(RECURRENCE_OF_KEY))[:MAX_POSTMORTEM_FIELD_CHARS],
        extracted_by="model",
    )
    return PostmortemFields() if fields.empty else fields


def _text(value: Any) -> str:
    """Return ``value`` as trimmed text, whatever it arrived as."""
    return str(value).strip() if isinstance(value, str | int | float) else ""


__all__ = [
    "CORRECTION_KEY",
    "EXTRACTED_BY_KEY",
    "HEADING_ALIASES",
    "INVESTIGATION_KEY",
    "NO_CAUSE_PHRASES",
    "POSTMORTEM_EXTRACTION_SCHEMA",
    "RECURRED_AS_KEY",
    "RECURRENCE_OF_KEY",
    "ROOT_CAUSE_KEY",
    "SECTIONS_KEY",
    "SYMPTOM_KEY",
    "PostmortemExtractor",
    "PostmortemFields",
    "extraction_metadata",
    "fields_from_metadata",
    "resolve_recurrences",
    "structural_fields",
]
