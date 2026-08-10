"""The checks an operator already runs, read out of a document as proposals.

A repository that has been operated for two years holds a file of verification
queries — the things somebody runs before believing the cluster is well, each
one written down because it has caught something. Every one of them is a
detector that does not exist, and the distance between "written down" and
"watched continuously" is most of why an estate has a problem nobody noticed.

**Proposed, never enabled.** A document that could turn itself into something
which pages people is the one outcome this must not have. Each candidate arrives
``enabled=false``, carrying the sentence its author wrote and a citation to the
document, and enabling it is an operator's act — previewed with the dry run that
already exists.

**Ordinary detector rows.** The detectors screen, the dry run, and the enable
and disable routes all exist. A parallel candidate store would need its own of
each and would buy nothing except a second place a detector can live.

**A candidate has one number, and that is honest.** The document states a firing
value and says nothing about hysteresis, so the clear value is left to default
to the firing value — which is the declaration the document actually supports.
Choosing the gap is part of what the operator is being asked to decide, and
inventing one here would hide the decision inside a proposal.

Nothing here imports the configuration schema. ``to_settings`` returns the plain
mapping a ``DetectorSettings`` is built from, so the knowledge base proposes and
the configuration service — which owns the audit line and the approval gate —
is what writes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from config.constants.knowledge import (
    MAX_DETECTOR_CANDIDATES,
    MAX_DETECTOR_ORIGIN_EXCERPT_CHARS,
)
from platform.knowledge.base.chunking import sections
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What a proposed detector's identifier begins with. Prefixed so a candidate
#: and a shipped detector can never collide, and so an operator scanning the
#: list can see at a glance which rows came out of a document.
CANDIDATE_ID_PREFIX = "corpus-"

#: The two lines a verification has to state before it is a detector rather than
#: an instruction. A check that says "have a look at the mounts" is good advice
#: and is not something a threshold can evaluate, so it is left alone.
SIGNAL_LINE = re.compile(
    r"^\s*[-*]\s*signal\s*:\s*`?([\w.\-]+)`?\s*$", re.IGNORECASE | re.MULTILINE
)
FIRES_LINE = re.compile(
    r"^\s*[-*]\s*fires\s+when\s*:\s*(above|below)\s+(-?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: Any run of characters that cannot be in an identifier, for the slug.
NOT_IDENTIFIER = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class DetectorCandidate:
    """One verification, in the shape a detector declaration is built from."""

    detector_id: str
    name: str
    description: str
    signal: str
    comparison: str
    fire_value: float
    #: The document this came out of, and where to open it. Both, because the
    #: identifier is what the row links by and the location is what a human
    #: reads.
    origin: str = ""
    location: str = ""
    #: What the author wrote, quoted. An operator deciding whether to enable a
    #: threshold needs the reason beside it, and the reason is in the document.
    origin_excerpt: str = ""

    def to_settings(self) -> dict[str, Any]:
        """Return the mapping a ``DetectorSettings`` entry is built from.

        A plain mapping rather than the schema type, so this module stays free
        of the configuration package: knowledge proposes, and the configuration
        service — which owns the audit line, the field locks and the approval
        gate — is what writes.
        """
        return {
            "detector_id": self.detector_id,
            "name": self.name,
            "description": self.description,
            "signal": self.signal,
            "kind": "threshold",
            "comparison": self.comparison,
            "fire_value": self.fire_value,
            "enabled": False,
            "origin": self.origin,
            "origin_excerpt": self.origin_excerpt,
        }


def candidates_from(
    body: str,
    *,
    document_id: str,
    location: str = "",
) -> tuple[DetectorCandidate, ...]:
    """Return the detectors ``body``'s verification sections propose.

    One per section that states both a signal and a number. A section that
    states neither is prose, and proposing a detector from it would be inventing
    a threshold nobody wrote.
    """
    found: list[DetectorCandidate] = []

    for section in sections(body):
        title = section.title.strip()
        if not title:
            continue
        text = body[section.start : section.end]
        signal = SIGNAL_LINE.search(text)
        fires = FIRES_LINE.search(text)
        if signal is None or fires is None:
            continue

        slug = _slug(title)
        if not slug:
            continue
        found.append(
            DetectorCandidate(
                detector_id=f"{CANDIDATE_ID_PREFIX}{slug}",
                name=title,
                description=_prose(text) or title,
                signal=signal.group(1),
                comparison=fires.group(1).lower(),
                fire_value=float(fires.group(2)),
                origin=document_id,
                location=location,
                origin_excerpt=_excerpt(title, text),
            )
        )

    if len(found) > MAX_DETECTOR_CANDIDATES:
        logger.info(
            "knowledge.detector_candidates_truncated",
            document=document_id,
            found=len(found),
            limit=MAX_DETECTOR_CANDIDATES,
        )

    return tuple(found[:MAX_DETECTOR_CANDIDATES])


def settings_entries(candidates: Mapping[str, DetectorCandidate]) -> list[dict[str, Any]]:
    """Return the configuration entries a set of candidates becomes, by identifier."""
    return [candidates[key].to_settings() for key in sorted(candidates)]


def _slug(title: str) -> str:
    """Return the identifier fragment a heading becomes."""
    return NOT_IDENTIFIER.sub("-", title.lower()).strip("-")


def _prose(text: str) -> str:
    """Return the section's sentences, without its declaration lines.

    The prose is what the author wrote to explain the check, and it is the
    ``description`` a detector is refused without. The bullets are the machine
    half and repeating them in the description would say the threshold twice.
    """
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
        and SIGNAL_LINE.match(line) is None
        and FIRES_LINE.match(line) is None
    ]
    return " ".join(lines)


def _excerpt(title: str, text: str) -> str:
    """Return what the row quotes: the heading and the reason, bounded."""
    prose = _prose(text)
    quoted = f"{title} — {prose}" if prose else title
    return quoted[:MAX_DETECTOR_ORIGIN_EXCERPT_CHARS]


__all__ = [
    "CANDIDATE_ID_PREFIX",
    "FIRES_LINE",
    "SIGNAL_LINE",
    "DetectorCandidate",
    "candidates_from",
    "settings_entries",
]
