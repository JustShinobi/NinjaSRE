"""Ranking the catalogue against one incident, with no model in the loop.

An LLM ranker would score better than this on any single incident. It is still
the wrong answer, for two reasons that outweigh accuracy.

**Reproducibility.** Trajectory evaluation compares runs. If the set of tools
offered to the model varies between two runs of the same scenario, every
downstream difference is unattributable — the suite can no longer tell a better
loop from a luckier selection.

**Cost.** Selection happens before every turn. A model call there is a call on
the critical path of an incident, times twenty iterations, for a decision that
weighted arithmetic answers well enough.

So: deterministic weights, ties broken by name, and every contribution recorded
in the rationale. When selection gets something wrong, the trace says which
signal was responsible rather than leaving an engineer to guess at a ranking.

The weights themselves are constants rather than literals here, because the
ablation suite has to be able to zero one and re-run.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from config.constants.capabilities import (
    SCORE_ALERT_SOURCE_MATCH,
    SCORE_ANTI_EXAMPLE_PENALTY,
    SCORE_DOMAIN_MATCH,
    SCORE_EFFECTIVENESS_MAX,
    SCORE_MINIMUM_TERM_LENGTH,
    SCORE_STOP_WORDS,
    SCORE_SUBJECT_SOURCE_MATCH,
    SCORE_TAG_OVERLAP_MAX,
    SCORE_TAG_OVERLAP_PER_TAG,
    SCORE_USE_CASE_SIMILARITY_MAX,
)
from core.capability.metadata import (
    CapabilityKind,
    CapabilityMetadata,
    SkillMetadata,
    ToolMetadata,
)
from core.capability.ports import (
    EffectivenessProvider,
    NeutralEffectiveness,
    validate_effectiveness,
)

_WORD = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True, slots=True)
class Incident:
    """What is known about the situation when capabilities are chosen.

    Deliberately small. Everything here is available before the first model
    call, because selection has to happen before the first model call.
    """

    alert_source: str = ""
    summary: str = ""
    tags: tuple[str, ...] = ()
    domain: str = ""
    planned_capabilities: tuple[str, ...] = ()
    #: The systems that hold what this incident is about, as the estate names
    #: them — ``proxmox`` for a node swept from Proxmox, and so on. Alert
    #: resolution has already matched the alert onto a resource by the time
    #: capabilities are ranked, so this costs no lookup here.
    #:
    #: Separate from ``alert_source`` because they answer different questions.
    #: One says which system is broken and the other says which system said so,
    #: and a deployment that routes every alert through one receiver has the
    #: same ``alert_source`` on every incident it will ever have.
    subject_sources: tuple[str, ...] = ()

    def terms(self) -> frozenset[str]:
        """Return the meaningful words in the summary, for lexical overlap."""
        return _terms(self.summary)


@dataclass(frozen=True, slots=True)
class ScoredCapability:
    """One capability's score against one incident, and how it got there."""

    name: str
    kind: CapabilityKind
    score: float
    rationale: tuple[str, ...] = ()

    @property
    def suppressed(self) -> bool:
        """Return whether an anti-example put this below zero."""
        return self.score < 0.0


def _terms(text: str) -> frozenset[str]:
    """Return the words in ``text`` worth matching on."""
    return frozenset(
        word
        for word in _WORD.findall(text.lower())
        if len(word) >= SCORE_MINIMUM_TERM_LENGTH and word not in SCORE_STOP_WORDS
    )


def _declared_alert_sources(metadata: CapabilityMetadata) -> frozenset[str]:
    """Return the alert sources ``metadata`` claims, whichever kind it is.

    A skill says so directly. A tool says so by naming the system its evidence
    comes from, which is the same claim written in the place a tool has for it.
    """
    if isinstance(metadata, SkillMetadata):
        return frozenset(metadata.applies_when.alert_sources)
    if isinstance(metadata, ToolMetadata):
        return frozenset({metadata.evidence_source})
    return frozenset()


def _declared_subject_sources(metadata: CapabilityMetadata) -> frozenset[str]:
    """Return the systems ``metadata`` says it is *about*, whichever kind it is.

    A tool names one outright: the system its evidence comes from is the system
    it can say anything about. A skill names none — a methodology has no
    evidence source — so what it declares instead is read: the situations its
    author said it applies to, which is where a Proxmox methodology writes
    ``proxmox``.

    Distinct from ``_declared_alert_sources`` even though a tool answers both
    from the same field. The two questions differ whenever the system that
    reported a failure is not the system that has it, which is the ordinary
    case: one Alertmanager reports on an estate of many vendors.
    """
    if isinstance(metadata, ToolMetadata):
        source = metadata.evidence_source.strip().lower()
        return frozenset({source}) if source else frozenset()
    if isinstance(metadata, SkillMetadata):
        return frozenset(
            tag.strip().lower()
            for tag in (*metadata.tags, *metadata.applies_when.tags)
            if tag.strip()
        )
    return frozenset()


def _declared_tags(metadata: CapabilityMetadata) -> frozenset[str]:
    """Return every tag ``metadata`` matches on."""
    tags = set(metadata.tags)
    if isinstance(metadata, SkillMetadata):
        tags.update(metadata.applies_when.tags)
    return frozenset(tag.lower() for tag in tags)


def _declared_domains(metadata: CapabilityMetadata) -> frozenset[str]:
    """Return every domain ``metadata`` claims."""
    domains = {metadata.domain} if metadata.domain else set()
    if isinstance(metadata, SkillMetadata):
        domains.update(metadata.applies_when.domains)
    return frozenset(domain.lower() for domain in domains if domain)


def score_capability(
    metadata: CapabilityMetadata,
    incident: Incident,
    *,
    effectiveness: EffectivenessProvider | None = None,
) -> ScoredCapability:
    """Return ``metadata``'s score against ``incident``, with its rationale.

    An anti-example match is a large negative rather than an exclusion. The
    author of the capability said "not for this", which is strong evidence and
    not a veto — a plan entry naming the capability explicitly still wins,
    because a human or a planning stage asking for it by name knows something
    the declaration did not.
    """
    provider = effectiveness if effectiveness is not None else NeutralEffectiveness()
    score = 0.0
    rationale: list[str] = []

    # The vendor holding the broken thing, before the vendor that reported it.
    # Both terms can fire on one capability — an Alertmanager tool on an
    # Alertmanager-hosted subject is relevant twice over — and that is the
    # correct arithmetic rather than a double count to guard against.
    subjects = {source.strip().lower() for source in incident.subject_sources if source.strip()}
    about = _declared_subject_sources(metadata) & subjects
    if about:
        score += SCORE_SUBJECT_SOURCE_MATCH
        rationale.append(
            f"the incident's subject is held by {', '.join(sorted(about))} "
            f"(+{SCORE_SUBJECT_SOURCE_MATCH:g})"
        )

    alert_source = incident.alert_source.strip().lower()
    if alert_source and alert_source in {
        source.lower() for source in _declared_alert_sources(metadata)
    }:
        score += SCORE_ALERT_SOURCE_MATCH
        rationale.append(f"alert source {alert_source!r} matches (+{SCORE_ALERT_SOURCE_MATCH:g})")

    if incident.domain and incident.domain.lower() in _declared_domains(metadata):
        score += SCORE_DOMAIN_MATCH
        rationale.append(f"domain {incident.domain!r} matches (+{SCORE_DOMAIN_MATCH:g})")

    shared_tags = {tag.lower() for tag in incident.tags} & _declared_tags(metadata)
    if shared_tags:
        contribution = min(SCORE_TAG_OVERLAP_PER_TAG * len(shared_tags), SCORE_TAG_OVERLAP_MAX)
        score += contribution
        rationale.append(f"tags {', '.join(sorted(shared_tags))} overlap (+{contribution:g})")

    incident_terms = incident.terms()
    if incident_terms and metadata.use_cases:
        use_case_terms = _terms(" ".join(metadata.use_cases))
        shared = incident_terms & use_case_terms
        if shared:
            ratio = len(shared) / len(use_case_terms | incident_terms)
            contribution = SCORE_USE_CASE_SIMILARITY_MAX * ratio
            score += contribution
            rationale.append(f"use cases overlap the summary (+{contribution:g})")

    historical = validate_effectiveness(
        provider.effectiveness(metadata.name, alert_source=incident.alert_source)
    )
    if historical:
        contribution = SCORE_EFFECTIVENESS_MAX * historical
        score += contribution
        rationale.append(f"historically effective here (+{contribution:g})")

    if incident_terms and metadata.anti_examples:
        anti_terms = _terms(" ".join(metadata.anti_examples))
        # Every meaningful word of an anti-example present in the summary. A
        # partial match is a coincidence; the whole phrase is the author
        # describing this incident and saying not to use this.
        if anti_terms and anti_terms <= incident_terms:
            score += SCORE_ANTI_EXAMPLE_PENALTY
            rationale.append(
                f"an anti-example describes this incident ({SCORE_ANTI_EXAMPLE_PENALTY:g})"
            )

    if metadata.name in incident.planned_capabilities:
        rationale.append("named by the plan")

    return ScoredCapability(
        name=metadata.name,
        kind=metadata.kind,
        score=score,
        rationale=tuple(rationale),
    )


def rank(
    catalogue: Sequence[CapabilityMetadata],
    incident: Incident,
    *,
    effectiveness: EffectivenessProvider | None = None,
) -> tuple[ScoredCapability, ...]:
    """Return every capability scored, highest first, ties broken by name.

    The tiebreak is what makes SC-005 hold. Without it, two capabilities
    scoring identically would order by whatever the catalogue happened to
    produce, and a rebuild on another machine could reorder them — turning a
    trajectory comparison into noise.
    """
    scored = [
        score_capability(metadata, incident, effectiveness=effectiveness) for metadata in catalogue
    ]
    return tuple(sorted(scored, key=lambda entry: (-entry.score, entry.name)))


__all__ = [
    "Incident",
    "ScoredCapability",
    "rank",
    "score_capability",
]
