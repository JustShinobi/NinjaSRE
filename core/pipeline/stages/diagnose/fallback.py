"""The degraded parser, and an honest account of what it can and cannot do.

Structured output fails. A local model without native support and a provider
having a bad afternoon both produce the same thing — a conclusion in prose and
no object — and the choice at that moment is between a weaker diagnosis and no
diagnosis. An investigation that gathered eleven observations and then reported
nothing because a schema call failed has thrown away the expensive part to
protect the cheap part.

So this recovers what it can, and every result it produces is marked
``fallback_used``. What it does:

- takes the root cause from an explicit ``Root cause:`` line, or the first
  substantial sentence;
- matches the category on the vocabulary each category's own name and
  description supply, scoring by how many distinctive words appear;
- reads a numbered or bulleted list as the causal chain, and a list under a
  remediation heading as the steps;
- extracts claims from sentences citing an evidence identifier in the
  ``[e1]`` form the prompt asked for.

What it cannot do: distinguish a claim the conclusion asserted from one it
considered and rejected. Prose says "we ruled out a deploy" the same way it
says "a deploy caused this", and no heuristic here reads the difference. That
is exactly why the flag travels on the result rather than being logged and
forgotten — a corpus scored without separating fallback diagnoses from
structured ones is a corpus measuring two different things at once.
"""

from __future__ import annotations

import re
from typing import Final

from config.constants.investigation import (
    MAX_CAUSAL_CHAIN_STEPS,
    MAX_DIAGNOSIS_CLAIMS,
    MAX_REMEDIATION_STEPS,
)
from core.domain.diagnosis.result import Claim, Diagnosis
from core.domain.diagnosis.taxonomy import (
    CATEGORY_DESCRIPTIONS,
    TAXONOMY_VERSION,
    RootCauseCategory,
)

#: Headings that introduce the root cause, lower-cased and without punctuation.
_ROOT_CAUSE_HEADINGS: Final[tuple[str, ...]] = (
    "root cause",
    "root-cause",
    "cause",
    "conclusion",
    "diagnosis",
)

#: Headings that introduce the remediation list.
_REMEDIATION_HEADINGS: Final[tuple[str, ...]] = (
    "remediation",
    "next steps",
    "recommended",
    "recommendation",
    "recommendations",
    "fix",
    "mitigation",
)

#: Headings that introduce the causal chain.
_CHAIN_HEADINGS: Final[tuple[str, ...]] = (
    "causal chain",
    "chain",
    "sequence",
    "timeline",
    "how it happened",
)

#: An evidence citation as the prompt asks for it. Also matches a bare ``e12``
#: at a word boundary, because a model that dropped the brackets still meant the
#: identifier — and an identifier that does not exist is demoted anyway.
_CITATION = re.compile(r"\[(?P<bracketed>[a-z]+\d+)\]|\b(?P<bare>e\d+)\b", re.IGNORECASE)

#: A list item: a bullet or a number, with its marker.
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(?P<text>.+)$")

#: Sentence boundaries, good enough for prose a model wrote.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

#: Words too common to distinguish one category from another. Without this,
#: "failure" alone would score four categories equally.
_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {
        "the",
        "and",
        "was",
        "were",
        "this",
        "that",
        "with",
        "from",
        "for",
        "its",
        "out",
        "ran",
        "than",
        "rather",
        "here",
        "not",
        "under",
        "over",
        "what",
        "which",
        "when",
        "where",
        "something",
        "anything",
        "one",
        "regardless",
        "own",
        "outside",
        "inside",
        "between",
        "against",
        "system",
        "systems",
        "problem",
        "cause",
        "caused",
        "causes",
        "failed",
        "failure",
        "failing",
        "error",
        "errors",
        "incident",
        "alert",
        "choose",
        "evidence",
        "gathered",
        "does",
        "support",
        "attributing",
        "correctly",
        "behaving",
        "describing",
        "real",
        "run",
        "time",
        "component",
        "components",
    }
)

#: The minimum score a category needs before it beats ``unknown``. One shared
#: word is a coincidence; two is a signal.
_CATEGORY_FLOOR: Final[int] = 2

_WORD = re.compile(r"[a-z]+")


def _terms(text: str) -> frozenset[str]:
    """Return the distinctive words in ``text``."""
    return frozenset(
        word for word in _WORD.findall(text.lower()) if len(word) > 3 and word not in _STOP_WORDS
    )


#: Each category's vocabulary, built once from its name and its description.
_CATEGORY_TERMS: Final[dict[RootCauseCategory, frozenset[str]]] = {
    category: _terms(f"{category.value.replace('_', ' ')} {description}")
    for category, description in CATEGORY_DESCRIPTIONS.items()
    if category is not RootCauseCategory.UNKNOWN
}


def parse_conclusion(conclusion: str, *, note: str = "") -> Diagnosis:
    """Return the best-effort diagnosis ``conclusion`` supports.

    Always marked ``fallback_used``. The flag is what keeps a corpus scored
    over these separable from one scored over structured results, and the two
    are not the same measurement.
    """
    text = conclusion.strip()
    if not text:
        return Diagnosis(
            summary=note,
            fallback_used=True,
            taxonomy_version=TAXONOMY_VERSION,
        )

    root_cause = _root_cause(text)
    return Diagnosis(
        root_cause=root_cause,
        root_cause_category=classify(text),
        summary=f"{note}\n\n{text}".strip() if note else text,
        causal_chain=_section(text, _CHAIN_HEADINGS, MAX_CAUSAL_CHAIN_STEPS),
        validated_claims=_claims(text),
        remediation_steps=_section(text, _REMEDIATION_HEADINGS, MAX_REMEDIATION_STEPS),
        confidence=0.0,
        fallback_used=True,
        taxonomy_version=TAXONOMY_VERSION,
    )


def classify(text: str) -> RootCauseCategory:
    """Return the category ``text`` best matches, or ``UNKNOWN``.

    Ties break towards ``UNKNOWN`` rather than towards whichever category
    happens to sort first: a conclusion that matches two categories equally has
    not identified either, and guessing between them is the mistake the closed
    taxonomy exists to make visible.
    """
    found = _terms(text)
    scores = {category: len(found & vocabulary) for category, vocabulary in _CATEGORY_TERMS.items()}
    best = max(scores.values(), default=0)
    if best < _CATEGORY_FLOOR:
        return RootCauseCategory.UNKNOWN

    winners = [category for category, score in scores.items() if score == best]
    if len(winners) != 1:
        return RootCauseCategory.UNKNOWN
    return winners[0]


def _root_cause(text: str) -> str:
    """Return the sentence naming the cause, from a heading or from the prose."""
    for line in text.splitlines():
        stripped = line.strip().lstrip("#*- ").strip()
        lowered = stripped.lower()
        for heading in _ROOT_CAUSE_HEADINGS:
            if lowered.startswith(heading):
                remainder = stripped[len(heading) :].lstrip(":—- ").strip()
                if remainder:
                    return remainder
    sentences = [
        sentence.strip()
        for sentence in _SENTENCE.split(text.replace("\n", " "))
        if len(sentence.strip()) > 20
    ]
    return sentences[0] if sentences else text.splitlines()[0].strip()


def _section(text: str, headings: tuple[str, ...], limit: int) -> tuple[str, ...]:
    """Return the list items under the first of ``headings`` that appears.

    Falling back to every list item in the document when no heading matches
    would put the remediation steps in the causal chain and vice versa, so an
    absent heading yields nothing.
    """
    lines = text.splitlines()
    start: int | None = None

    for index, line in enumerate(lines):
        lowered = line.strip().lstrip("#*- ").strip().lower()
        if any(lowered.startswith(heading) for heading in headings):
            start = index + 1
            break

    if start is None:
        return ()

    items: list[str] = []
    for line in lines[start:]:
        match = _LIST_ITEM.match(line)
        if match:
            items.append(match.group("text").strip())
            continue
        if line.strip() and items:
            break
    return tuple(items[:limit])


def _claims(text: str) -> tuple[Claim, ...]:
    """Return the sentences that cite an evidence identifier, as claims.

    A sentence with no citation is not extracted at all. The parser cannot tell
    an assertion from a rejected hypothesis in prose, so it only recovers the
    sentences that were written as findings — and validation checks those
    citations against what the run actually holds.
    """
    claims: list[Claim] = []
    for raw in _SENTENCE.split(text.replace("\n", " ")):
        sentence = raw.strip()
        if not sentence:
            continue
        cited = tuple(
            dict.fromkeys(
                (match.group("bracketed") or match.group("bare")).lower()
                for match in _CITATION.finditer(sentence)
            )
        )
        if cited:
            claims.append(Claim(statement=sentence, evidence_ids=cited))
        if len(claims) >= MAX_DIAGNOSIS_CLAIMS:
            break
    return tuple(claims)


__all__ = [
    "classify",
    "parse_conclusion",
]
