"""One structured call, after the investigation, that can never fail it.

Extraction runs post-turn from the objective, the answer, and the tool trace. It
is one call with a bounded reply, and the single most important property of this
module is the one it does not do: **nothing here raises into the run**. Every
failure path — a provider outage, a malformed object, a field of the wrong type
— comes back as an ``ExtractionOutcome`` carrying the reason.

That is not defensiveness. Memory is a bookkeeping concern attached to the end of
an investigation that has already produced its answer, and letting it turn a
successful investigation into a failed one would be trading the product for the
feature. The reason is recorded, so a deployment where extraction is broken looks
broken rather than looking like a team that never has incidents.

The capability sequence is read from the trace rather than from the model. Asking
the model which tools it called invites it to reconstruct a tidier trajectory
than the one that happened, and the trajectory is precisely what the next
investigation is meant to reuse.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.memory import (
    EPISODE_EXTRACTION_MAX_TOKENS,
    MAX_EPISODE_COMPONENTS,
    MAX_EPISODE_KEY_FINDINGS,
    MAX_EPISODE_SUMMARY_CHARS,
    MIN_EPISODE_RESULT_LENGTH,
)
from config.prompts.memory import (
    EPISODE_EXTRACTION_FAILED,
    EPISODE_EXTRACTION_REQUEST,
    EPISODE_EXTRACTION_SYSTEM_PROMPT,
    EPISODE_SKIPPED_TOO_SHORT,
)
from core.agent.session import Session
from core.capability.telemetry import InvocationOutcome
from core.llm.types import InvokeRequest, LLMClient, Message, Role
from core.llm.usage import UsageRecord
from platform.memory.models import Component, EpisodeSeverity, IssueType, KeyFinding
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What the model is asked to return. Every field is optional in the schema and
#: defaulted here: a model that could not tell what the severity was should leave
#: it out, and a schema that made it required would get a guess instead.
#:
#: ``issue_type`` is an enum rather than free text, and that is the writing half
#: of a controlled vocabulary. Two runs describing one incident chose
#: ``manual_shutdown`` and ``ProxmoxGuestStopped``, and a corpus filed under both
#: is a corpus neither of them can search. A list is also easier to answer than
#: an instruction to invent a short lowercase label, which is worth something on
#: its own: the reply that fails to parse is usually the reply the model had to
#: compose rather than choose.
EPISODE_EXTRACTION_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "issue_type": {
            "type": "string",
            "enum": [member.value for member in IssueType],
            "description": (
                "The class of failure, chosen from this list. Pick the closest one; "
                "use 'other' only when none of them describes what went wrong, and "
                "put your own words in 'issue_label' when you do."
            ),
        },
        "issue_label": {
            "type": "string",
            "description": (
                "The failure class in your own words, when the listed type does not "
                "say it precisely — 'ceph_pg_inconsistent', 'ProxmoxGuestStopped'. "
                "Kept verbatim beside the classification, never instead of it."
            ),
        },
        "issue_description": {
            "type": "string",
            "description": "One sentence saying what was wrong, with the numbers.",
        },
        "severity": {
            "type": "string",
            "enum": [member.value for member in EpisodeSeverity],
            "description": "How bad it was. Use 'unknown' rather than guessing.",
        },
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "service, deployment, database, job, node, queue, …",
                    },
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
            "description": "The systems the failure was about, as the run observed them.",
        },
        "key_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string"},
                    "query": {"type": "string"},
                    "finding": {"type": "string"},
                },
                "required": ["finding"],
            },
            "description": "What each capability revealed, naming the capability.",
        },
        "resolved": {
            "type": "boolean",
            "description": (
                "True when this investigation established a root cause with evidence "
                "behind it. NOT a claim that production was fixed."
            ),
        },
        "root_cause": {
            "type": "string",
            "description": "The cause the evidence supports, or empty if none was established.",
        },
        "summary": {
            "type": "string",
            "description": "A few sentences a future investigation would want to read.",
        },
    },
    "required": ["issue_type", "issue_description", "summary"],
}


@dataclass(frozen=True, slots=True)
class EpisodeExtraction:
    """What one investigation turned out to be about."""

    issue_type: str = ""
    issue_label: str = ""
    issue_description: str = ""
    severity: EpisodeSeverity = EpisodeSeverity.UNKNOWN
    components: tuple[Component, ...] = ()
    key_findings: tuple[KeyFinding, ...] = ()
    resolved: bool = False
    root_cause: str = ""
    summary: str = ""

    @property
    def usable(self) -> bool:
        """Return whether there is enough here to be worth a row and a vector.

        An extraction with neither a classification nor a summary embeds to
        nothing and matches nothing, so writing it costs a row, a vector, and a
        neighbour slot in every future search, and returns none of them.

        ``other`` alone does not count as a classification. Before the vocabulary
        existed an unclassified reply left ``issue_type`` empty and this test saw
        it; a schema with an escape hatch in it means a model can now answer the
        question with the word for having not answered it, and an enum member is
        still a non-empty string.
        """
        return bool(
            self.summary.strip()
            or self.issue_label.strip()
            or IssueType.classify(self.issue_type).classified
        )

    @classmethod
    def from_structured(cls, document: Mapping[str, Any]) -> EpisodeExtraction:
        """Return the extraction a structured reply describes, field by field.

        Every field is read defensively and none of them can raise. A model that
        returned a string where a list was asked for should cost that field, not
        the episode.

        The issue type is the one field that is *transformed* rather than read.
        It arrives as whatever the model said and leaves as a member of the
        vocabulary, with the model's own words preserved on ``issue_label`` — so
        the corpus is filed under a word two runs can both find, and no run's
        description of its own incident is thrown away to get there.
        """
        raw_type = _text(document.get("issue_type"))
        raw_label = _text(document.get("issue_label"))
        # Classified rather than trusted. The enum is a request the provider may
        # or may not enforce, and an unenforced one comes back as whatever the
        # model would have written anyway — which is the free-text problem the
        # enum was added to end.
        classified = IssueType.classify(raw_type or raw_label)
        # The label carries only what the bucket lost. A model that picked from
        # the list said nothing the classification does not already say, and
        # echoing it back would make "the model had words of its own" true of
        # every episode — including the one that answered ``other`` and nothing
        # else, which is a reply with no content wearing a vocabulary member.
        words = raw_label or raw_type
        return cls(
            issue_type=classified.value,
            issue_label="" if words.lower() == classified.value else words,
            issue_description=_text(document.get("issue_description")),
            severity=EpisodeSeverity.parse(_text(document.get("severity"))),
            components=_components(document.get("components")),
            key_findings=_findings(document.get("key_findings")),
            resolved=bool(document.get("resolved", False)),
            root_cause=_text(document.get("root_cause")),
            summary=_text(document.get("summary"))[:MAX_EPISODE_SUMMARY_CHARS],
        )


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    """What extraction produced, including when it produced nothing.

    ``skipped`` and a failed extraction are kept apart. One is a decision the
    system made on purpose and the other is something being broken, and a
    deployment where every investigation is "skipped" is fine while one where
    every investigation "failed" is not.
    """

    extraction: EpisodeExtraction | None = None
    skipped: bool = False
    reason: str = ""
    usage: UsageRecord | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether an episode can be built from this outcome."""
        return self.extraction is not None


def too_short(answer: str) -> bool:
    """Return whether ``answer`` is below the length worth remembering."""
    return len(answer.strip()) < MIN_EPISODE_RESULT_LENGTH


def skip_reason(answer: str) -> str:
    """Return the sentence recorded when an answer is skipped for length."""
    return EPISODE_SKIPPED_TOO_SHORT.format(
        length=len(answer.strip()), minimum=MIN_EPISODE_RESULT_LENGTH
    )


def capability_sequence(session: Session) -> tuple[str, ...]:
    """Return the capabilities this run actually called, in first-use order.

    De-duplicated, because the sequence is what a later investigation would
    *follow*, and "logs, logs, logs, metrics" is one strategy rather than four
    steps. Denied and replayed calls are dropped: neither produced anything, and
    a trajectory that includes them teaches the next run to repeat a refusal.
    """
    seen: dict[str, None] = {}
    for turn in session.turns:
        for execution in turn.executions:
            if execution.denied or execution.replayed:
                continue
            if execution.outcome is InvocationOutcome.SUCCESS:
                seen.setdefault(execution.capability, None)
    return tuple(seen)


def observed_findings(session: Session) -> tuple[KeyFinding, ...]:
    """Return the run's evidence as findings, for the extraction request.

    Built from the session's evidence rather than from the transcript: evidence
    is what the system observed and the transcript is what the model said, and
    only the first is worth carrying into a corpus a later run will trust.
    """
    return tuple(
        KeyFinding(
            capability=entry.capability,
            query=entry.reference,
            finding=entry.summary,
        )
        for entry in session.evidence[:MAX_EPISODE_KEY_FINDINGS]
    )


def describe_findings(findings: Sequence[KeyFinding]) -> str:
    """Return the observations as the extraction call is shown them."""
    if not findings:
        return "None. The investigation recorded no evidence."
    return "\n".join(
        f"- {finding.capability}{f' ({finding.query})' if finding.query else ''}: {finding.finding}"
        for finding in findings
    )


@dataclass(frozen=True, slots=True)
class EpisodeExtractor:
    """The single post-investigation call, with every failure turned into a value."""

    llm: LLMClient

    async def extract(
        self,
        *,
        objective: str,
        answer: str,
        capabilities: Sequence[str],
        findings: Sequence[KeyFinding],
    ) -> ExtractionOutcome:
        """Return what this investigation was about, or why nothing could be said.

        Never raises. That is the whole contract, and the broad catch is
        deliberate: a provider client that grew a new exception type must not be
        able to fail an investigation that already produced its answer.
        """
        if too_short(answer):
            return ExtractionOutcome(skipped=True, reason=skip_reason(answer))

        try:
            result = await self.llm.invoke_structured(
                self._request(
                    objective=objective,
                    answer=answer,
                    capabilities=capabilities,
                    findings=findings,
                ),
                EPISODE_EXTRACTION_SCHEMA,
            )
        except Exception as error:  # noqa: BLE001 — extraction must never fail a run
            reason = EPISODE_EXTRACTION_FAILED.format(failure=f"{type(error).__name__}: {error}")
            logger.warning("memory.extraction_failed", error=str(error))
            return ExtractionOutcome(reason=reason)

        if not result.succeeded or result.structured is None:
            failure = result.failure_message or (
                result.failure.value if result.failure else "no structured object returned"
            )
            logger.warning("memory.extraction_empty", failure=failure)
            return ExtractionOutcome(
                reason=EPISODE_EXTRACTION_FAILED.format(failure=failure), usage=result.usage
            )

        extraction = EpisodeExtraction.from_structured(result.structured)
        if not extraction.usable:
            # The keys are named, the values are not. Which fields arrived tells
            # an operator whether the model answered a different question, whether
            # generation was cut off partway, or whether the object was empty —
            # three causes with three different fixes, and the message that said
            # only "neither an issue type nor a summary" separated none of them.
            # The values would be the investigation's own text and do not belong
            # in a log line.
            carried = ", ".join(sorted(str(key) for key in result.structured)) or "no keys at all"
            logger.warning("memory.extraction_empty", failure="the reply carried no content")
            return ExtractionOutcome(
                reason=EPISODE_EXTRACTION_FAILED.format(
                    failure=(
                        "the structured reply named neither an issue type nor a summary; "
                        f"it carried {carried}"
                    )
                ),
                usage=result.usage,
            )

        return ExtractionOutcome(extraction=extraction, usage=result.usage)

    def _request(
        self,
        *,
        objective: str,
        answer: str,
        capabilities: Sequence[str],
        findings: Sequence[KeyFinding],
    ) -> InvokeRequest:
        """Return the single call this module makes."""
        return InvokeRequest(
            messages=(
                Message(
                    role=Role.USER,
                    text=EPISODE_EXTRACTION_REQUEST.format(
                        objective=objective.strip() or "not recorded",
                        capabilities=", ".join(capabilities) or "none",
                        observations=describe_findings(findings),
                        conclusion=answer.strip(),
                    ),
                ),
            ),
            system=EPISODE_EXTRACTION_SYSTEM_PROMPT,
            max_output_tokens=EPISODE_EXTRACTION_MAX_TOKENS,
        )


def _text(value: Any) -> str:
    """Return ``value`` as trimmed text, whatever it arrived as."""
    return str(value).strip() if isinstance(value, str | int | float) else ""


def _components(value: Any) -> tuple[Component, ...]:
    """Return the components a reply describes, dropping anything unusable."""
    if not isinstance(value, list):
        return ()

    found: list[Component] = []
    for item in value[:MAX_EPISODE_COMPONENTS]:
        if isinstance(item, Mapping):
            name = _text(item.get("name"))
            kind = _text(item.get("type"))
        else:
            name, kind = _text(item), ""
        if name:
            found.append(Component(type=kind, name=name))
    return tuple(found)


def _findings(value: Any) -> tuple[KeyFinding, ...]:
    """Return the key findings a reply describes, dropping anything unusable."""
    if not isinstance(value, list):
        return ()

    found: list[KeyFinding] = []
    for item in value[:MAX_EPISODE_KEY_FINDINGS]:
        if not isinstance(item, Mapping):
            continue
        finding = _text(item.get("finding"))
        if finding:
            found.append(
                KeyFinding(
                    capability=_text(item.get("capability")),
                    query=_text(item.get("query")),
                    finding=finding,
                )
            )
    return tuple(found)


__all__ = [
    "EPISODE_EXTRACTION_SCHEMA",
    "EpisodeExtraction",
    "EpisodeExtractor",
    "ExtractionOutcome",
    "capability_sequence",
    "describe_findings",
    "observed_findings",
    "skip_reason",
    "too_short",
]
