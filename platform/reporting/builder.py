"""Assembling one report from a diagnosis, the run's evidence, and what it cost.

Everything here is a pure function of what the run already holds. Nothing calls
a model, nothing reads storage, and nothing invents a section — which is what
makes a report reproducible from a stored trace, and what makes the "no
conclusion" path a *derivation* rather than a decision somebody made about tone.

Three things are load-bearing.

**A citation is resolved against the run's own evidence.** A claim naming an
identifier the run does not hold did not partially work: the model invented a
reference, and the claim is filed as non-validated rather than shipped with a
reference that points nowhere. This is the same rule the diagnosis stage applies,
applied again here because a report is the artefact that outlives the run.

**What was eliminated is derived when nobody supplied it.** A hypothesis the run
gathered evidence *about* and could not confirm is a hypothesis somebody looked
at, and saying so is the whole value of a no-conclusion report. A hypothesis with
no evidence behind it is not ruled out — it was never examined — and reporting it
as eliminated would send the next person past the thing that is actually wrong.

**Screening happens before formatting, not before delivery.** One screened value
feeds all thirteen formatters, so a destination cannot be the one that skipped
it, and a new formatter is not a new place to remember.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime

from core.domain.diagnosis.result import Claim, Diagnosis
from core.state.evidence import EvidenceEntry
from platform.guardrails.engine import GuardrailEngine
from platform.reporting.models import (
    NO_CONCLUSION_STATEMENT,
    EvidenceReference,
    Horizon,
    RecommendedAction,
    Report,
    ReportClaim,
    ReportMetadata,
    RuledOut,
)

#: Why a hypothesis the evidence did not confirm is reported as eliminated. Says
#: what happened rather than asserting the hypothesis is false — the evidence
#: gathered did not support it, which is a narrower and more honest claim.
UNSUPPORTED_HYPOTHESIS_REASON: str = "the evidence gathered for this hypothesis did not support it"


def build_report(
    diagnosis: Diagnosis,
    *,
    run_id: str,
    title: str,
    evidence: Sequence[EvidenceEntry],
    metadata: ReportMetadata | None = None,
    ruled_out: Sequence[RuledOut] = (),
    actions: Sequence[RecommendedAction] | None = None,
    summary: str = "",
) -> Report:
    """Return the report ``diagnosis`` and ``evidence`` describe.

    ``ruled_out`` and ``actions`` override what would otherwise be derived. A
    caller that knows more than the diagnosis does — a pipeline stage that
    tracked which hypotheses were eliminated, an operator classifying a
    recommendation as preventive — supplies them; one that does not gets the
    derivation rather than an empty section.
    """
    held = _index(evidence)
    validated, demoted = _resolve_claims(diagnosis.validated_claims, held)
    non_validated = tuple(
        ReportClaim(statement=claim.statement) for claim in diagnosis.non_validated_claims
    )

    report = Report(
        run_id=run_id,
        title=title,
        summary=summary or diagnosis.summary,
        root_cause=diagnosis.root_cause,
        confidence_score=diagnosis.confidence,
        causal_chain=tuple(diagnosis.causal_chain),
        validated_claims=validated,
        non_validated_claims=demoted + non_validated,
        ruled_out=tuple(ruled_out) or _derived_ruled_out(diagnosis.non_validated_claims, held),
        recommended_actions=(
            tuple(actions)
            if actions is not None
            else tuple(
                RecommendedAction(action=step, horizon=Horizon.IMMEDIATE)
                for step in diagnosis.remediation_steps
            )
        ),
        metadata=metadata if metadata is not None else ReportMetadata(run_id=run_id),
    )
    if report.has_conclusion:
        return report
    return replace(report, summary=_no_conclusion_summary(report.summary))


def metadata_of(
    evidence: Sequence[EvidenceEntry],
    *,
    run_id: str,
    run_link: str = "",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    cost_usd: float = 0.0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    model_id: str = "",
    team_node_id: str = "",
) -> ReportMetadata:
    """Return the metadata section for a run that produced ``evidence``.

    Capabilities are read off the evidence rather than taken as an argument: the
    list of what was *used* is the list of what produced an observation, and a
    caller passing its own would be reporting what it intended to call.
    """
    duration = (
        (finished_at - started_at).total_seconds()
        if started_at is not None and finished_at is not None
        else 0.0
    )
    return ReportMetadata(
        run_id=run_id,
        run_link=run_link,
        capabilities_used=tuple(sorted({item.capability for item in evidence})),
        duration_seconds=duration,
        cost_usd=cost_usd,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model_id=model_id,
        team_node_id=team_node_id,
    )


def screened(report: Report, *, engine: GuardrailEngine) -> Report:
    """Return ``report`` with every string passed through the live ruleset.

    Every string, at every depth, including the evidence summaries a citation
    carries — an observation is the most likely place for a secret to have
    arrived from, because it came out of somebody else's system.
    """
    return Report(
        run_id=report.run_id,
        title=_scan(engine, report.title),
        summary=_scan(engine, report.summary),
        root_cause=_scan(engine, report.root_cause),
        confidence_score=report.confidence_score,
        causal_chain=tuple(_scan(engine, step) for step in report.causal_chain),
        validated_claims=tuple(_screen_claim(engine, claim) for claim in report.validated_claims),
        non_validated_claims=tuple(
            _screen_claim(engine, claim) for claim in report.non_validated_claims
        ),
        ruled_out=tuple(_screen_ruled_out(engine, entry) for entry in report.ruled_out),
        recommended_actions=tuple(
            RecommendedAction(
                action=_scan(engine, action.action),
                horizon=action.horizon,
                rationale=_scan(engine, action.rationale),
            )
            for action in report.recommended_actions
        ),
        metadata=report.metadata,
    )


def _index(evidence: Sequence[EvidenceEntry]) -> Mapping[str, EvidenceReference]:
    """Return the run's evidence as citable references, keyed by identifier."""
    return {
        item.id: EvidenceReference(
            evidence_id=item.id,
            capability=item.capability,
            source=item.source,
            summary=item.summary,
            reference=item.reference,
        )
        for item in evidence
    }


def _resolve_claims(
    claims: Sequence[Claim], held: Mapping[str, EvidenceReference]
) -> tuple[tuple[ReportClaim, ...], tuple[ReportClaim, ...]]:
    """Return the claims that resolved to held evidence, and those that did not."""
    validated: list[ReportClaim] = []
    demoted: list[ReportClaim] = []
    for claim in claims:
        cited = tuple(held[item] for item in claim.evidence_ids if item in held)
        if cited:
            validated.append(ReportClaim(statement=claim.statement, evidence=cited))
        else:
            demoted.append(ReportClaim(statement=claim.statement))
    return tuple(validated), tuple(demoted)


def _derived_ruled_out(
    claims: Sequence[Claim], held: Mapping[str, EvidenceReference]
) -> tuple[RuledOut, ...]:
    """Return the hypotheses the run examined and could not confirm."""
    entries: list[RuledOut] = []
    for claim in claims:
        cited = tuple(held[item] for item in claim.evidence_ids if item in held)
        if cited:
            entries.append(
                RuledOut(
                    hypothesis=claim.statement,
                    reason=UNSUPPORTED_HYPOTHESIS_REASON,
                    evidence=cited,
                )
            )
    return tuple(entries)


def _no_conclusion_summary(summary: str) -> str:
    """Return the summary a report that reached no conclusion carries."""
    body = summary.strip()
    if not body:
        return NO_CONCLUSION_STATEMENT
    return f"{NO_CONCLUSION_STATEMENT}\n\n{body}"


def _scan(engine: GuardrailEngine, text: str) -> str:
    """Return ``text`` as the live ruleset allows it to be written down."""
    return engine.scan(text).text if text else text


def _screen_reference(engine: GuardrailEngine, item: EvidenceReference) -> EvidenceReference:
    """Return ``item`` with its prose screened and its identifier untouched.

    The identifier and the reference URL are not screened: they are NinjaSRE's
    own handles on an observation, and redacting one would break the citation
    the report exists to carry.
    """
    return EvidenceReference(
        evidence_id=item.evidence_id,
        capability=item.capability,
        source=item.source,
        summary=_scan(engine, item.summary),
        reference=item.reference,
    )


def _screen_claim(engine: GuardrailEngine, claim: ReportClaim) -> ReportClaim:
    """Return ``claim`` with its statement and citations screened."""
    return ReportClaim(
        statement=_scan(engine, claim.statement),
        evidence=tuple(_screen_reference(engine, item) for item in claim.evidence),
    )


def _screen_ruled_out(engine: GuardrailEngine, entry: RuledOut) -> RuledOut:
    """Return ``entry`` with its prose and citations screened."""
    return RuledOut(
        hypothesis=_scan(engine, entry.hypothesis),
        reason=_scan(engine, entry.reason),
        evidence=tuple(_screen_reference(engine, item) for item in entry.evidence),
    )


__all__ = [
    "UNSUPPORTED_HYPOTHESIS_REASON",
    "build_report",
    "metadata_of",
    "screened",
]
