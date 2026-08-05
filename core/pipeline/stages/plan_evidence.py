"""The shortlist the loop starts from, chosen without a model call.

An LLM ranker would score better on any single incident. It is still the wrong
answer here, for the reason the capability layer's scorer gives: trajectory
evaluation compares runs, and if the shortlist varies between two runs of the
same scenario then every downstream difference is unattributable. Deterministic
arithmetic keeps the plan reproducible, which is what makes the loop's
behaviour measurable.

The plan is **advisory**, and that is enforced by the type rather than by
everyone remembering. ``EvidencePlan.binding`` is computed from the scores, so
a shortlist assembled from weak matches cannot be handed to a conclusion policy
that would hold the run open until each entry had been called. When the
incident is not what the alert suggested — which is the case that matters — a
binding plan spends the whole budget confirming that the alert was misleading.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from core.domain.alerts.normalisation import NormalisedAlert
from core.domain.correlation.planning import EvidencePlan, PlannedAction, plan_from
from core.pipeline.ports import UNRANKED, CapabilityRanker, IncidentSignals
from core.state.agent_state import AgentState, StateUpdates
from core.state.types import StageName, unique_names

#: How the written rationale reads when the plan has entries.
PLAN_RATIONALE = (
    "Scored {scored} available capabilities against a {source} alert{components}. "
    "Shortlisted the top {kept} within the team's tool budget of {budget}: {names}. "
    "The plan is advisory — the loop may call anything in the catalogue, and falls back "
    "to its own relevance ranking where this shortlist is weak."
)

#: How it reads when nothing scored above zero.
PLAN_RATIONALE_EMPTY = (
    "No capability in the {scored}-entry catalogue scored above zero against this "
    "{source} alert, so no shortlist was produced. The loop investigates on its own "
    "relevance ranking, which is what an advisory plan means when it is empty."
)

#: Appended when the catalogue itself was empty.
PLAN_RATIONALE_NO_CATALOGUE = (
    "There is nothing to plan over: this team has no capability it can run."
)


@dataclass(frozen=True, slots=True)
class PlanEvidenceStage:
    """Score the resolved catalogue and keep the top ``tool_budget`` entries."""

    ranker: CapabilityRanker = UNRANKED

    @property
    def name(self) -> StageName:
        """Return which of the six stages this is."""
        return StageName.PLAN_EVIDENCE

    async def __call__(self, state: AgentState) -> StateUpdates:
        """Return the shortlist and the written rationale behind it."""
        catalogue = state.investigation.catalogue
        alert = state.investigation.alert

        if not catalogue.metadata:
            return StateUpdates(
                investigation=replace(
                    state.investigation,
                    plan=EvidencePlan(rationale=PLAN_RATIONALE_NO_CATALOGUE),
                )
            )

        ranked = self.ranker.rank(catalogue.metadata, signals_from(alert))
        budget = max(0, state.team.tool_budget)
        # A zero score is the absence of a signal, not a weak one. Keeping those
        # entries would fill the shortlist with whatever happened to sort first
        # and make the plan read as a decision nobody made.
        shortlisted = [entry for entry in ranked if entry.score > 0.0][:budget]

        actions = tuple(
            PlannedAction(
                capability=entry.name, score=entry.score, rationale=tuple(entry.rationale)
            )
            for entry in shortlisted
        )
        return StateUpdates(
            investigation=replace(
                state.investigation,
                plan=plan_from(
                    actions,
                    rationale=_rationale(
                        actions, scored=len(catalogue.metadata), alert=alert, budget=budget
                    ),
                ),
            )
        )


def signals_from(alert: NormalisedAlert | None) -> IncidentSignals:
    """Return what ranking is told about the incident.

    Everything here is already in state before the first model call of the
    gathering stage, which is the constraint ranking is built under.
    """
    if alert is None:
        return IncidentSignals()

    return IncidentSignals(
        alert_source=alert.alert_source.value,
        summary=" ".join(
            part for part in (alert.alert_name, alert.summary, alert.error_text) if part
        ),
        tags=unique_names(
            (
                *alert.components,
                *(value for value in alert.labels.values()),
                *(key for key in alert.labels),
                alert.severity.value,
            )
        ),
    )


def _rationale(
    actions: tuple[PlannedAction, ...],
    *,
    scored: int,
    alert: NormalisedAlert | None,
    budget: int,
) -> str:
    """Return the paragraph an engineer reads after a bad investigation."""
    source = alert.alert_source.value if alert is not None else "unrecognised"
    if not actions:
        return PLAN_RATIONALE_EMPTY.format(scored=scored, source=source)

    components = ""
    if alert is not None and alert.components:
        components = f" on {', '.join(alert.components)}"

    return PLAN_RATIONALE.format(
        scored=scored,
        source=source,
        components=components,
        kept=len(actions),
        budget=budget,
        names=", ".join(action.capability for action in actions),
    )


__all__ = [
    "PLAN_RATIONALE",
    "PLAN_RATIONALE_EMPTY",
    "PLAN_RATIONALE_NO_CATALOGUE",
    "PlanEvidenceStage",
    "signals_from",
]
