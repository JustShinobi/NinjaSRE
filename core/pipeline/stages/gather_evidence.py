"""The expensive stage, deliberately thin.

Everything that makes the loop bounded — the iteration ceiling, the wall clock,
the stagnation breaker, the context budget, the duplicate cache — is the
runtime's, and none of it is repeated here. What this stage owns is the three
things that are the *investigation's* rather than the loop's:

**The request.** What to investigate, from which source, inside which window,
with which shortlist, and under which system prompt. The window travels in the
run's context so the model can see it, and is enforced separately so seeing it
is not required. The system prompt travels here rather than being read from
configuration inside the loop, because the loop is provider-neutral machinery
and which team's prompt this run uses is a composition decision.

**The window guard.** A ``pre_tool_use`` hook clamping time-bounded arguments
clamped to the window. Suggesting it in the prompt is not enforcement: a model asked
to look "around the incident" reliably asks for the last twenty-four hours.

**Provenance.** Every observation the loop made is promoted into the
investigation with the run, the turn, and the specialist it came from attached
attached. The runtime's entry is what a prompt needs; this is what somebody
checking a claim afterwards needs.

The stage never raises on a failed run. The loop returns a partial result
carrying the evidence it did gather, and eleven observations from an
investigation that lost its model are eleven observations the operator would
like.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from config.constants.investigation import (
    CONTEXT_ALERT_NAME,
    CONTEXT_ALERT_SOURCE,
    CONTEXT_COMPONENTS,
    CONTEXT_PLAN,
    CONTEXT_PLAN_RATIONALE,
    CONTEXT_SEVERITY,
    CONTEXT_WINDOW_CONFIDENCE,
    CONTEXT_WINDOW_END,
    CONTEXT_WINDOW_START,
)
from core.agent.runtime_port import RunRequest, RunResult, RunStatus, Runtime
from core.agent.turn import Turn
from core.capability.telemetry import InvocationOutcome
from core.domain.alerts.normalisation import NormalisedAlert
from core.domain.alerts.window import IncidentWindow
from core.pipeline.runtime_bridge import events_for_turns
from core.pipeline.streaming import EventStream, silent_stream
from core.state.agent_state import AgentState, StateUpdates
from core.state.evidence import EvidenceEntry, Provenance
from core.state.slices import AccountingSlice, EvidenceSlice
from core.state.types import InvestigationOutcome, OutcomeKind, StageName

#: How the objective handed to the loop is written.
OBJECTIVE = (
    "Investigate this incident and establish its root cause from evidence.\n\n"
    "Alert: {name}\n"
    "Source: {source}\n"
    "Severity: {severity}\n"
    "Affected: {components}\n"
    "Incident window: {window_start} .. {window_end} ({window_note})\n\n"
    "{summary}\n\n{error_text}"
)

#: What the window note says when the window was defaulted rather than derived.
WINDOW_IS_A_GUESS = (
    "low confidence — nothing in the alert said when this began, so this span is a default"
)
WINDOW_IS_DERIVED = "derived from the alert's own timestamps"

#: Recorded when the run itself failed rather than concluding.
GATHER_FAILED_HEADLINE = "Investigation did not complete"


@dataclass(frozen=True, slots=True)
class GatherEvidenceStage:
    """Run the canonical runtime, and record what it observed with provenance."""

    runtime: Runtime
    stream: EventStream | None = None
    #: The system prompt this team runs under, from the configuration service's
    #: own assembly (``AgentsConfig.system_prompt_for``). Empty means the shipped
    #: default, which is what a deployment that configured nothing gets — and it
    #: is the loop that supplies it, so this stage never names a prompt.
    system_prompt: str = ""

    @property
    def name(self) -> StageName:
        """Return which of the six stages this is."""
        return StageName.GATHER_EVIDENCE

    async def __call__(self, state: AgentState) -> StateUpdates:
        """Return the evidence, the conclusion, and what the run cost."""
        alert = state.investigation.alert
        window = state.investigation.window
        if alert is None:
            raise ValueError(
                f"{state.run_id}: gather_evidence ran with no alert — intake did not "
                "produce one and the pipeline should have stopped"
            )

        result = await self.runtime.run(self._request(state, alert, window))
        await self._bridge(result.turns)

        investigation = replace(state.investigation, conclusion=result.answer)
        if result.status is RunStatus.FAILED:
            investigation = replace(
                investigation,
                outcome=InvestigationOutcome(
                    kind=OutcomeKind.FAILED,
                    headline=GATHER_FAILED_HEADLINE,
                    detail=result.failure,
                ),
            )

        return StateUpdates(
            evidence=EvidenceSlice(entries=self._promote(result, state)),
            investigation=investigation,
            accounting=_accounted(state.accounting, result, runtime=self.runtime.name),
        )

    async def _bridge(self, turns: Sequence[Turn]) -> None:
        """Emit the loop's turns onto the pipeline stream."""
        stream = self.stream if self.stream is not None else silent_stream()
        for event in events_for_turns(turns, stage=self.name):
            await stream.emit(event)

    def _request(
        self, state: AgentState, alert: NormalisedAlert, window: IncidentWindow | None
    ) -> RunRequest:
        """Return the investigation as the runtime is asked for it."""
        return RunRequest(
            objective=_objective(alert, window),
            alert_source=alert.alert_source.value,
            session_id=state.run_id,
            system_prompt=self.system_prompt,
            context=_context(alert, window, state),
        )

    def _promote(self, result: RunResult, state: AgentState) -> tuple[EvidenceEntry, ...]:
        """Return the run's observations as investigation evidence, with provenance."""
        provenance = Provenance(
            stage=self.name,
            runtime=self.runtime.name,
            session_id=result.session.id,
        )
        arguments = _arguments_by_evidence_id(result.turns)
        recorded_at = datetime.now(UTC)

        return (
            *state.evidence.entries,
            *(
                EvidenceEntry.from_runtime(
                    entry,
                    provenance=provenance,
                    arguments=arguments.get(entry.id, {}),
                    recorded_at=recorded_at,
                )
                for entry in result.evidence
            ),
        )


def _accounted(accounting: AccountingSlice, result: RunResult, *, runtime: str) -> AccountingSlice:
    """Return what the run cost, added to what the pipeline had already spent.

    The runtime is recorded by name because Article V turns on it: a number
    produced by an experimental adapter must be identifiable as one, and the
    guard in front of the evaluation suite reads what the run wrote down.
    """
    executions = sum(len(turn.executions) for turn in result.turns)
    return replace(
        accounting,
        tokens=accounting.tokens + result.tokens,
        llm_calls=accounting.llm_calls + len(result.turns),
        capability_executions=accounting.capability_executions + executions,
        iterations=result.iterations,
        runtime=runtime,
        status=result.status.value,
    )


def _arguments_by_evidence_id(turns: Sequence[Turn]) -> Mapping[str, Mapping[str, object]]:
    """Return the arguments each evidence entry was produced by.

    A summary with no query behind it is unfalsifiable: "the error rate was 12%"
    can only be checked by somebody who can re-run what produced it.
    """
    found: dict[str, Mapping[str, object]] = {}
    for turn in turns:
        for execution in turn.executions:
            if execution.outcome is not InvocationOutcome.SUCCESS:
                continue
            for evidence_id in execution.evidence_ids:
                found[evidence_id] = dict(execution.arguments)
    return found


def _objective(alert: NormalisedAlert, window: IncidentWindow | None) -> str:
    """Return what the loop is told to investigate."""
    return OBJECTIVE.format(
        name=alert.alert_name or "unnamed",
        source=alert.alert_source.value,
        severity=alert.severity.value,
        components=", ".join(alert.components) or "not stated",
        window_start=window.start.isoformat() if window else "not derived",
        window_end=window.end.isoformat() if window else "not derived",
        window_note=_window_note(window),
        summary=alert.summary,
        error_text=alert.error_text,
    ).strip()


def _window_note(window: IncidentWindow | None) -> str:
    """Return how much the window is worth relying on."""
    if window is None:
        return "not derived"
    return WINDOW_IS_A_GUESS if window.is_fallback else WINDOW_IS_DERIVED


def _context(
    alert: NormalisedAlert, window: IncidentWindow | None, state: AgentState
) -> dict[str, str]:
    """Return the structured context the run carries alongside its objective."""
    context = {
        CONTEXT_ALERT_NAME: alert.alert_name,
        CONTEXT_ALERT_SOURCE: alert.alert_source.value,
        CONTEXT_SEVERITY: alert.severity.value,
        CONTEXT_COMPONENTS: ", ".join(alert.components),
        CONTEXT_PLAN: ", ".join(state.investigation.plan.capabilities),
        CONTEXT_PLAN_RATIONALE: state.investigation.plan.rationale,
    }
    if window is not None:
        context[CONTEXT_WINDOW_START] = window.start.isoformat()
        context[CONTEXT_WINDOW_END] = window.end.isoformat()
        context[CONTEXT_WINDOW_CONFIDENCE] = f"{window.confidence:.2f}"
    return {key: value for key, value in context.items() if value}


__all__ = [
    "GATHER_FAILED_HEADLINE",
    "OBJECTIVE",
    "WINDOW_IS_A_GUESS",
    "WINDOW_IS_DERIVED",
    "GatherEvidenceStage",
]
