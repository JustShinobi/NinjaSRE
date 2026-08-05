"""One call, scoped to the conclusion and the evidence, and nothing else.

Asking the loop for structure on its last turn is the obvious alternative and
it is worse in a specific way: that turn is context-pressured and often
tool-stripped, and the model is being asked to reason and to format at the same
moment it has least room for either. A dedicated call that sees the conclusion,
the evidence, and the category list — and no transcript, no tool schemas, no
prior turns — is more reliable and is testable on its own.

The stage does three things in order and none of them are optional.

**Call.** Structured output against the closed taxonomy.

**Fall back.** A failure produces a degraded diagnosis from the conclusion text
rather than nothing, marked so a corpus can separate the two.

**Validate.** Every claim is checked against the evidence the run holds and
demoted if it cites none of it. This happens on both paths, because
the fallback's citations are exactly as unverified as the model's.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from config.constants.investigation import MAX_DIAGNOSIS_EVIDENCE_ENTRIES
from config.prompts.investigation import (
    DIAGNOSE_EVIDENCE_LINE,
    DIAGNOSE_FALLBACK_NOTE,
    DIAGNOSE_REQUEST,
    DIAGNOSE_SYSTEM_PROMPT,
)
from core.domain.diagnosis.result import Diagnosis
from core.domain.diagnosis.taxonomy import CATEGORY_DESCRIPTIONS
from core.llm.types import InvokeRequest, InvokeResult, LLMClient, Message, Role
from core.pipeline.accounting import account_for
from core.pipeline.stages.diagnose.fallback import parse_conclusion
from core.pipeline.stages.diagnose.models import DIAGNOSIS_SCHEMA, diagnosis_from_structured
from core.pipeline.stages.diagnose.validation import validate
from core.state.agent_state import AgentState, StateUpdates
from core.state.slices import EvidenceSlice
from core.state.types import StageName

#: What the request says when the run gathered nothing. A diagnosis over no
#: evidence is possible — the conclusion may say why nothing could be gathered —
#: and every claim in it will be demoted, which is the correct outcome.
NO_EVIDENCE = "None. Every claim in this diagnosis will be recorded as unvalidated."

#: What it says when the run reached no conclusion at all.
NO_CONCLUSION = "The investigation produced no conclusion text."


@dataclass(frozen=True, slots=True)
class DiagnoseStage:
    """Turn the free-text conclusion into a structured, evidence-checked diagnosis."""

    llm: LLMClient

    @property
    def name(self) -> StageName:
        """Return which of the six stages this is."""
        return StageName.DIAGNOSE

    async def __call__(self, state: AgentState) -> StateUpdates:
        """Return the structured diagnosis, with unbacked claims demoted."""
        result = await self.llm.invoke_structured(self._request(state), DIAGNOSIS_SCHEMA)
        diagnosis = _from(result, state)

        return StateUpdates(
            investigation=replace(
                state.investigation, diagnosis=validate(diagnosis, state.evidence)
            ),
            accounting=account_for(state.accounting, result),
        )

    def _request(self, state: AgentState) -> InvokeRequest:
        """Return the single call this stage makes."""
        alert = state.investigation.alert
        window = state.investigation.window

        return InvokeRequest(
            messages=(
                Message(
                    role=Role.USER,
                    text=DIAGNOSE_REQUEST.format(
                        alert=alert.summary or alert.alert_name if alert else "not recorded",
                        window=(
                            f"{window.start.isoformat()} .. {window.end.isoformat()}"
                            if window
                            else "not derived"
                        ),
                        categories=describe_categories(),
                        evidence_count=len(state.evidence),
                        evidence=describe_evidence(state.evidence),
                        conclusion=state.investigation.conclusion.strip() or NO_CONCLUSION,
                    ),
                ),
            ),
            system=DIAGNOSE_SYSTEM_PROMPT,
        )


def _from(result: InvokeResult, state: AgentState) -> Diagnosis:
    """Return the diagnosis this result carries, degraded rather than absent."""
    if result.succeeded and result.structured is not None:
        return diagnosis_from_structured(result.structured)

    return parse_conclusion(
        state.investigation.conclusion,
        note=DIAGNOSE_FALLBACK_NOTE.format(
            failure=result.failure_message
            or (result.failure.value if result.failure else "no structured output returned")
        ),
    )


def describe_categories() -> str:
    """Return the closed taxonomy as the model is shown it.

    With the descriptions, not as bare identifiers. A model asked to choose
    from fourteen names it has never seen routinely picks
    ``configuration_error`` for anything it cannot place.
    """
    return "\n".join(
        f"- {category.value}: {description}"
        for category, description in CATEGORY_DESCRIPTIONS.items()
    )


def describe_evidence(evidence: EvidenceSlice) -> str:
    """Return the evidence as the model is shown it, identifier first and bounded.

    Bounded most-recent-first: this call sees only the conclusion and the
    evidence, so the cap is its whole context budget, and the entries a
    conclusion rests on are overwhelmingly the ones the loop gathered last.
    """
    if not evidence.entries:
        return NO_EVIDENCE

    shown = evidence.entries[-MAX_DIAGNOSIS_EVIDENCE_ENTRIES:]
    return "\n".join(
        DIAGNOSE_EVIDENCE_LINE.format(
            id=entry.id,
            capability=entry.capability,
            source=entry.source or "unnamed source",
            summary=entry.summary,
            reference=f" ({entry.reference})" if entry.reference else "",
        )
        for entry in shown
    )


__all__ = [
    "NO_CONCLUSION",
    "NO_EVIDENCE",
    "DiagnoseStage",
    "describe_categories",
    "describe_evidence",
]
