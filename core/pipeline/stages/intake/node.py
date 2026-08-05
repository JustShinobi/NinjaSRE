"""One model call that decides whether anything happens at all.

This is the cheapest stage and the one with the most leverage. The most common
input to a deployed SRE agent is not an incident — it is a greeting in a thread,
an acknowledgement, a test webhook — and every one of those that reaches the
loop costs a full investigation. Rejecting them here costs one call.

Three decisions are worth stating.

**The parsed fields lead and the model fills gaps.** An adapter that read
``service: checkout`` from a label read a fact. Asking the model to rediscover
it invites it to disagree, and a component name that came from a guess will be
queried as though somebody had measured it.

**A provider failure means "incident", not "noise".** The classification call
failing must not silently turn every alert into nothing. The run continues with
zero confidence recorded, which is the expensive mistake made deliberately
rather than the cheap one made invisibly.

**Deduplication runs after classification, not before.** A duplicate has to be
an incident first: linking a greeting to an open incident would attach chatter
to an investigation, and fingerprinting an unclassified input costs a lookup on
the most common input there is.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Final

from config.constants.investigation import NOISE_CLASSIFICATION_THRESHOLD
from config.prompts.investigation import (
    INTAKE_DUPLICATE_DETAIL,
    INTAKE_DUPLICATE_HEADLINE,
    INTAKE_NOISE_DETAIL,
    INTAKE_NOISE_HEADLINE,
    INTAKE_REQUEST,
    INTAKE_SYSTEM_PROMPT,
    INTAKE_UNAVAILABLE,
)
from core.domain.alerts.normalisation import NormalisedAlert, Severity, normalise
from core.domain.alerts.window import as_utc
from core.llm.types import InvokeRequest, InvokeResult, LLMClient, Message, Role
from core.pipeline.accounting import account_for
from core.pipeline.ports import NO_RECENT_INCIDENTS, IncidentIndex
from core.pipeline.stages.intake.dedup import deduplicate
from core.pipeline.stages.intake.window import derive_window
from core.state.agent_state import AgentState, StateUpdates
from core.state.types import (
    ChatMessage,
    IntakeClassification,
    InvestigationOutcome,
    OutcomeKind,
    StageName,
    unique_names,
)

#: The structured shape the classification call must return. Every field is
#: required: an optional field is one the model omits on the input where it
#: mattered, and an empty string is a clearer "nothing here" than an absence.
INTAKE_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "is_incident": {
            "type": "boolean",
            "description": "Whether this describes a production problem worth investigating.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "How sure you are of that verdict.",
        },
        "reason": {
            "type": "string",
            "description": "One sentence explaining the verdict.",
        },
        "alert_name": {
            "type": "string",
            "description": "A short identifier for what fired. Empty if the input has none.",
        },
        "severity": {
            "type": "string",
            "enum": [member.value for member in Severity],
            "description": "How bad the input says it is. 'unknown' if it does not say.",
        },
        "summary": {
            "type": "string",
            "description": "One line stating the problem, as the input describes it.",
        },
        "components": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Services, hosts, or namespaces the input names. Do not infer any.",
        },
        "error_text": {
            "type": "string",
            "description": "The error message or symptom text, quoted from the input.",
        },
    },
    "required": [
        "is_incident",
        "confidence",
        "reason",
        "alert_name",
        "severity",
        "summary",
        "components",
        "error_text",
    ],
}

#: How many messages of prior conversation the call is shown. Enough for
#: "deploy going out in five minutes" three messages back to reach the model,
#: and bounded because this is the cheap stage and must stay cheap.
MAX_CONVERSATION_MESSAGES: Final[int] = 8


@dataclass(frozen=True, slots=True)
class IntakeResult:
    """What the classification call produced, already merged over the parsed fields."""

    alert: NormalisedAlert
    classification: IntakeClassification


@dataclass(frozen=True, slots=True)
class IntakeStage:
    """Classify the input, extract its fields, bound it in time, and deduplicate it."""

    llm: LLMClient
    index: IncidentIndex = NO_RECENT_INCIDENTS
    clock: Callable[[], datetime] | None = None

    @property
    def name(self) -> StageName:
        """Return which of the six stages this is."""
        return StageName.INTAKE

    def _now(self) -> datetime:
        return as_utc(self.clock()) if self.clock is not None else datetime.now(UTC)

    async def __call__(self, state: AgentState) -> StateUpdates:
        """Return the alert, the window, the verdict, and any link this input produced."""
        now = self._now()
        parsed = normalise(state.raw)
        result = await self.llm.invoke_structured(self._request(state, parsed), INTAKE_SCHEMA)
        accounting = account_for(state.accounting, result)
        intake = _merge(parsed, result)

        investigation = replace(
            state.investigation,
            alert=intake.alert,
            classification=intake.classification,
        )
        chat = state.chat.with_message(
            ChatMessage(author=self.name.value, text=intake.classification.reason, at=now)
        )

        if _is_noise(intake.classification):
            return StateUpdates(
                chat=chat,
                accounting=accounting,
                investigation=replace(
                    investigation,
                    outcome=InvestigationOutcome(
                        kind=OutcomeKind.NOISE,
                        headline=INTAKE_NOISE_HEADLINE,
                        detail=INTAKE_NOISE_DETAIL.format(
                            confidence=intake.classification.confidence,
                            reason=intake.classification.reason or "no reason was given.",
                        ),
                    ),
                ),
            )

        investigation = replace(investigation, window=derive_window(intake.alert, now=now))
        deduplicated = await deduplicate(
            intake.alert, index=self.index, run_id=state.run_id, now=now
        )

        if deduplicated.link is not None:
            link = deduplicated.link
            investigation = replace(
                investigation,
                link=link,
                outcome=InvestigationOutcome(
                    kind=OutcomeKind.DUPLICATE,
                    headline=INTAKE_DUPLICATE_HEADLINE.format(incident_id=link.incident_id),
                    detail=INTAKE_DUPLICATE_DETAIL.format(reason=link.reason),
                ),
            )

        return StateUpdates(chat=chat, accounting=accounting, investigation=investigation)

    def _request(self, state: AgentState, parsed: NormalisedAlert) -> InvokeRequest:
        """Return the single call this stage makes."""
        return InvokeRequest(
            messages=(
                Message(
                    role=Role.USER,
                    text=INTAKE_REQUEST.format(
                        source=parsed.alert_source.value,
                        parsed=_describe(parsed),
                        conversation=_conversation(state.chat.messages),
                        raw=_raw_text(state),
                    ),
                ),
            ),
            system=INTAKE_SYSTEM_PROMPT,
        )


def _is_noise(classification: IntakeClassification) -> bool:
    """Return whether this verdict is confident enough to stop the run.

    Both halves matter. A "not an incident" verdict the model was unsure of is
    not enough to drop an alert, and the threshold is a constant so it can be
    tuned against the corpus rather than by intuition.
    """
    return (
        not classification.is_incident
        and classification.confidence >= NOISE_CLASSIFICATION_THRESHOLD
    )


def _merge(parsed: NormalisedAlert, result: InvokeResult) -> IntakeResult:
    """Return the parsed alert completed by the model, and the verdict."""
    if not result.succeeded or result.structured is None:
        return IntakeResult(
            alert=parsed,
            classification=IntakeClassification(
                is_incident=True,
                confidence=0.0,
                reason=INTAKE_UNAVAILABLE.format(
                    failure=result.failure_message or (result.failure or "no structured output")
                ),
            ),
        )

    structured = result.structured
    severity = _severity(structured.get("severity"))
    components = tuple(str(item) for item in structured.get("components") or ())

    return IntakeResult(
        alert=replace(
            parsed,
            alert_name=parsed.alert_name or str(structured.get("alert_name", "")).strip(),
            severity=parsed.severity if parsed.severity is not Severity.UNKNOWN else severity,
            summary=parsed.summary or str(structured.get("summary", "")).strip(),
            components=unique_names((*parsed.components, *components)),
            error_text=parsed.error_text or str(structured.get("error_text", "")).strip(),
        ),
        classification=IntakeClassification(
            is_incident=bool(structured.get("is_incident", True)),
            confidence=_confidence(structured.get("confidence")),
            reason=str(structured.get("reason", "")).strip(),
        ),
    )


def _confidence(value: object) -> float:
    """Return ``value`` as a confidence, clamped rather than rejected.

    A model that answered 1.4 meant "certain". Raising here would turn a
    formatting quirk into a failed investigation.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0
    try:
        number = float(value)
    except ValueError:
        return 0.0
    return min(1.0, max(0.0, number))


def _severity(value: object) -> Severity:
    """Return the severity ``value`` names, or ``UNKNOWN``."""
    try:
        return Severity(str(value).strip().lower())
    except ValueError:
        return Severity.UNKNOWN


def _describe(alert: NormalisedAlert) -> str:
    """Return the already-parsed fields as the model is shown them."""
    fields = {
        key: value
        for key, value in alert.to_record().items()
        if value not in ("", [], {}, None, False)
    }
    return json.dumps(fields, indent=2, sort_keys=True, default=str)


def _conversation(messages: Sequence[ChatMessage]) -> str:
    """Return the recent conversation, oldest first, bounded."""
    recent = messages[-MAX_CONVERSATION_MESSAGES:]
    return "\n".join(f"{message.author}: {message.text}" for message in recent)


def _raw_text(state: AgentState) -> str:
    """Return the raw input as text, whichever form it arrived in."""
    if state.raw.text.strip():
        return state.raw.text.strip()
    if state.raw.payload:
        return json.dumps(dict(state.raw.payload), indent=2, sort_keys=True, default=str)
    return ""


__all__ = [
    "INTAKE_SCHEMA",
    "MAX_CONVERSATION_MESSAGES",
    "IntakeResult",
    "IntakeStage",
]
