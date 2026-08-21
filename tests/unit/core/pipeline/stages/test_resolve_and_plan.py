"""Resolution answers "what can this team run", and planning answers "with what first".

The property worth the most here is the zero-integration outcome. A team with
nothing configured must
not get an empty report: it must get the name of the integration to connect,
how many capabilities that would unlock, and which of them would have served
the alert that just fired.
"""

from __future__ import annotations

import pytest

from capabilities.registry.planning import CatalogueRanker
from core.capability.metadata import CapabilityKind, ExcludedCapability
from core.domain.alerts.normalisation import NormalisedAlert, RawAlert, Severity
from core.domain.alerts.sources import AlertSource
from core.pipeline.ports import FixedCatalogueResolver, IncidentSignals, StaticCatalogue
from core.pipeline.stages.plan_evidence import PlanEvidenceStage, signals_from
from core.pipeline.stages.resolve_integrations import ResolveIntegrationsStage
from core.pipeline.state_factory import initial_state
from core.state.agent_state import apply_state_updates
from core.state.catalogue import ResolvedCapabilities
from core.state.types import OutcomeKind, StageName
from tests.unit.core.pipeline.conftest import (
    AT,
    ScriptedLLM,
    alertmanager_state,
    incident_classification,
    skill,
    team,
    tool,
)
from tests.unit.core.pipeline.stages.test_intake import _stage as intake_stage

pytestmark = pytest.mark.unit


def _catalogue(*names: str) -> StaticCatalogue:
    tools = tuple(tool(name) for name in names)
    return StaticCatalogue(
        tools=tools,
        declarations=tuple(found.metadata for found in tools),
    )


def _excluded(name: str, *unmet: str) -> ExcludedCapability:
    return ExcludedCapability(name=name, kind=CapabilityKind.TOOL, unmet=unmet)


async def _resolved(catalogue: StaticCatalogue, state: object) -> ResolvedCapabilities:
    stage = ResolveIntegrationsStage(FixedCatalogueResolver(catalogue))
    updates = await stage(state)  # type: ignore[arg-type]
    assert updates.investigation is not None
    return updates.investigation.catalogue


# -- resolution ---------------------------------------------------------------


async def test_the_resolved_catalogue_reaches_state() -> None:
    catalogue = _catalogue("datadog_log_statistics", "kubernetes_pod_events")

    resolved = await _resolved(catalogue, alertmanager_state())

    assert resolved.available == ("datadog_log_statistics", "kubernetes_pod_events")
    assert len(resolved.tools) == 2
    assert resolved


async def test_the_stage_names_itself() -> None:
    assert ResolveIntegrationsStage().name is StageName.RESOLVE_INTEGRATIONS


async def test_a_team_with_capabilities_reaches_no_outcome_yet() -> None:
    stage = ResolveIntegrationsStage(FixedCatalogueResolver(_catalogue("datadog_log_statistics")))

    updates = await stage(alertmanager_state())

    assert updates.investigation is not None
    assert updates.investigation.outcome is None


# -- the zero-integration path ------------------------------------------------


async def test_zero_integrations_ends_the_run_with_something_to_act_on() -> None:
    catalogue = StaticCatalogue(
        excluded=(
            _excluded("datadog_log_statistics", "datadog"),
            _excluded("datadog_metric_query", "datadog"),
            _excluded("datadog_monitor_state", "datadog"),
            _excluded("kubernetes_pod_events", "kubernetes"),
        )
    )
    state = alertmanager_state()
    stage = ResolveIntegrationsStage(FixedCatalogueResolver(catalogue))

    merged = apply_state_updates(state, await stage(state))
    outcome = merged.investigation.outcome

    assert outcome is not None
    assert outcome.kind is OutcomeKind.NO_INTEGRATIONS
    assert outcome.halts
    assert "4 capabilities are declared" in outcome.detail
    assert outcome.next_steps
    assert "Connect datadog" in outcome.next_steps[0]
    assert "3 capability" in outcome.next_steps[0]
    assert "datadog_log_statistics" in outcome.next_steps[0]


async def test_the_integration_matching_the_alert_source_is_suggested_first() -> None:
    """The outcome names what would have served *this* alert source."""
    catalogue = StaticCatalogue(
        excluded=(
            _excluded("kubernetes_pod_events", "kubernetes"),
            _excluded("kubernetes_deployment_history", "kubernetes"),
            _excluded("kubernetes_node_pressure", "kubernetes"),
            _excluded("grafana_log_statistics", "grafana"),
        )
    )
    state = initial_state(
        RawAlert(payload={"ruleName": "high latency", "orgId": "1"}, received_at=AT),
        team(integrations=()),
    )
    stage = ResolveIntegrationsStage(FixedCatalogueResolver(catalogue))

    outcome = (await stage(state)).investigation.outcome  # type: ignore[union-attr]

    assert outcome is not None
    assert "grafana" in outcome.detail
    assert "Connect grafana" in outcome.next_steps[0], (
        "kubernetes blocks more capabilities, but the alert came from Grafana"
    )


async def test_an_empty_catalogue_with_no_exclusions_says_so_rather_than_nothing() -> None:
    stage = ResolveIntegrationsStage(FixedCatalogueResolver(StaticCatalogue()))

    outcome = (await stage(alertmanager_state())).investigation.outcome  # type: ignore[union-attr]

    assert outcome is not None
    assert outcome.next_steps
    assert "nothing to" in outcome.next_steps[0]


# -- planning -----------------------------------------------------------------


async def _planned(state: object) -> object:
    updates = await PlanEvidenceStage(CatalogueRanker())(state)  # type: ignore[arg-type]
    assert updates.investigation is not None
    return updates.investigation.plan


async def test_the_plan_shortlists_within_the_teams_tool_budget() -> None:
    names = [f"datadog_probe_{index}" for index in range(12)]
    catalogue = _catalogue(*names)
    state = alertmanager_state(team=team(tool_budget=3))
    state = apply_state_updates(
        state, await ResolveIntegrationsStage(FixedCatalogueResolver(catalogue))(state)
    )
    state = apply_state_updates(
        state, await intake_stage(ScriptedLLM(structured=[incident_classification()]))(state)
    )

    plan = await _planned(state)

    assert len(plan.actions) == 3  # type: ignore[attr-defined]
    assert plan.rationale  # type: ignore[attr-defined]
    assert "tool budget of 3" in plan.rationale  # type: ignore[attr-defined]


async def test_the_plan_records_a_written_rationale() -> None:
    """An engineer reading the trace after a bad investigation wants a
    paragraph saying what the plan was trying to establish."""
    catalogue = _catalogue("datadog_log_statistics")
    state = alertmanager_state()
    state = apply_state_updates(
        state, await ResolveIntegrationsStage(FixedCatalogueResolver(catalogue))(state)
    )
    state = apply_state_updates(
        state, await intake_stage(ScriptedLLM(structured=[incident_classification()]))(state)
    )

    plan = await _planned(state)

    assert "alertmanager alert" in plan.rationale  # type: ignore[attr-defined]
    assert "checkout" in plan.rationale  # type: ignore[attr-defined]
    assert "advisory" in plan.rationale  # type: ignore[attr-defined]


async def test_an_empty_plan_does_not_block_the_loop() -> None:
    """A plan with nothing in it is advice nobody has to take."""
    catalogue = _catalogue("unrelated_thing")
    state = alertmanager_state()
    state = apply_state_updates(
        state, await ResolveIntegrationsStage(FixedCatalogueResolver(catalogue))(state)
    )

    plan = await _planned(state)

    assert plan.actions == ()  # type: ignore[attr-defined]
    assert not plan.binding  # type: ignore[attr-defined]
    assert "advisory" in plan.rationale or "own relevance" in plan.rationale  # type: ignore[attr-defined]


async def test_a_low_confidence_plan_is_not_binding() -> None:
    from core.domain.correlation.planning import EvidencePlan, PlannedAction

    weak = EvidencePlan(actions=(PlannedAction(capability="anything", score=0.2),))
    strong = EvidencePlan(actions=(PlannedAction(capability="anything", score=4.0),))

    assert not weak.binding
    assert strong.binding


async def test_planning_over_an_empty_catalogue_says_there_is_nothing_to_plan() -> None:
    state = alertmanager_state()

    plan = await _planned(state)

    assert plan.actions == ()  # type: ignore[attr-defined]
    assert "nothing to plan" in plan.rationale  # type: ignore[attr-defined]


async def test_the_plan_is_reproducible() -> None:
    """Two runs of the same scenario must produce the same shortlist, or a
    trajectory comparison is reading noise."""
    catalogue = _catalogue("datadog_log_statistics", "datadog_metric_query", "datadog_traces")
    state = alertmanager_state()
    state = apply_state_updates(
        state, await ResolveIntegrationsStage(FixedCatalogueResolver(catalogue))(state)
    )
    state = apply_state_updates(
        state, await intake_stage(ScriptedLLM(structured=[incident_classification()]))(state)
    )

    first = await _planned(state)
    second = await _planned(state)

    assert first == second


def test_the_ranking_signals_carry_the_source_the_summary_and_the_components() -> None:
    alert = NormalisedAlert(
        alert_source=AlertSource.GRAFANA,
        alert_name="HighErrorRate",
        summary="checkout error rate above 5%",
        error_text="502 from the payment gateway",
        components=("checkout",),
        severity=Severity.CRITICAL,
        labels={"env": "production"},
    )

    signals = signals_from(alert)

    assert signals.alert_source == "grafana"
    assert "HighErrorRate" in signals.summary
    assert "payment gateway" in signals.summary
    assert "checkout" in signals.tags
    assert "production" in signals.tags


def test_ranking_signals_from_no_alert_are_empty_rather_than_invented() -> None:
    assert signals_from(None) == IncidentSignals()


async def test_a_skill_is_scored_alongside_the_tools() -> None:
    found = tool("datadog_log_statistics")
    catalogue = StaticCatalogue(
        tools=(found,), declarations=(found.metadata, skill("error-rate-triage"))
    )
    state = alertmanager_state()
    state = apply_state_updates(
        state, await ResolveIntegrationsStage(FixedCatalogueResolver(catalogue))(state)
    )
    state = apply_state_updates(
        state, await intake_stage(ScriptedLLM(structured=[incident_classification()]))(state)
    )

    plan = await _planned(state)

    assert "error-rate-triage" in plan.capabilities  # type: ignore[attr-defined]
