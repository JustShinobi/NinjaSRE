"""Intake is where an investigation is decided against, and it costs one call.

The three properties this suite is here for: a non-incident stops the run
before a capability can execute, a window is always produced even when
nothing named one, and an alert storm produces one investigation rather than N.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.investigation import (
    DEDUPLICATION_WINDOW_MINUTES,
    DEFAULT_INCIDENT_WINDOW_MINUTES,
    INCIDENT_WINDOW_LEAD_MINUTES,
    NOISE_CLASSIFICATION_THRESHOLD,
)
from core.domain.alerts.normalisation import NormalisedAlert, RawAlert, Severity
from core.domain.alerts.sources import AlertSource
from core.llm.failures import FailureClass
from core.pipeline.ports import InMemoryIncidentIndex
from core.pipeline.stages.intake.node import IntakeStage
from core.pipeline.stages.intake.window import derive_window
from core.pipeline.state_factory import initial_state
from core.state.agent_state import apply_state_updates
from core.state.types import OutcomeKind, StageName
from tests.unit.core.pipeline.conftest import (
    AT,
    ScriptedLLM,
    alertmanager_state,
    fixed_clock,
    incident_classification,
    noise_classification,
    team,
)

pytestmark = pytest.mark.unit


def _stage(llm: ScriptedLLM, index: InMemoryIncidentIndex | None = None) -> IntakeStage:
    return IntakeStage(
        llm=llm,
        index=index if index is not None else InMemoryIncidentIndex(),
        clock=fixed_clock(),
    )


# -- classification -----------------------------------------------------------


async def test_a_real_alert_is_classified_as_an_incident_and_its_fields_extracted() -> None:
    llm = ScriptedLLM(structured=[incident_classification()])

    updates = await _stage(llm)(alertmanager_state())

    investigation = updates.investigation
    assert investigation is not None
    assert investigation.classification is not None
    assert investigation.classification.is_incident
    assert investigation.outcome is None
    assert investigation.alert is not None
    assert investigation.alert.alert_name == "HighErrorRate"
    assert investigation.alert.severity is Severity.CRITICAL
    assert investigation.alert.components == ("checkout",)
    assert investigation.window is not None


async def test_a_greeting_stops_the_run_after_exactly_one_model_call() -> None:
    """A non-incident costs zero capability executions and exactly one call."""
    llm = ScriptedLLM(structured=[noise_classification()])
    state = initial_state(RawAlert(text="morning all!", received_at=AT), team())

    updates = await _stage(llm)(state)
    merged = apply_state_updates(state, updates)

    assert llm.calls == 1
    assert merged.investigation.outcome is not None
    assert merged.investigation.outcome.kind is OutcomeKind.NOISE
    assert merged.investigation.halted
    assert len(merged.evidence) == 0
    assert merged.accounting.capability_executions == 0


async def test_the_noise_verdict_records_its_confidence_and_reason() -> None:
    """A false negative is only auditable if the run wrote down how sure it was."""
    llm = ScriptedLLM(structured=[noise_classification(confidence=0.91)])

    updates = await _stage(llm)(initial_state(RawAlert(text="thanks!"), team()))

    investigation = updates.investigation
    assert investigation is not None
    assert investigation.classification is not None
    assert investigation.classification.confidence == pytest.approx(0.91)
    assert "greeting" in investigation.classification.reason
    assert investigation.outcome is not None
    assert "0.91" in investigation.outcome.detail


async def test_an_unconfident_noise_verdict_does_not_stop_the_run() -> None:
    """Dismissing a real incident costs an outage nobody looked at, so the
    threshold has to be cleared before the run is dropped."""
    below = NOISE_CLASSIFICATION_THRESHOLD - 0.05
    llm = ScriptedLLM(structured=[noise_classification(confidence=below)])

    updates = await _stage(llm)(initial_state(RawAlert(text="is this thing on?"), team()))

    assert updates.investigation is not None
    assert updates.investigation.outcome is None
    assert updates.investigation.window is not None


async def test_a_provider_failure_is_treated_as_an_incident_with_no_confidence() -> None:
    """A provider outage must not silently turn every alert into noise."""
    llm = ScriptedLLM(
        structured=[None],
        failure=FailureClass.MODEL_UNAVAILABLE,
        failure_message="503 from the endpoint",
    )

    updates = await _stage(llm)(alertmanager_state())

    investigation = updates.investigation
    assert investigation is not None
    assert investigation.outcome is None
    assert investigation.classification is not None
    assert investigation.classification.is_incident
    assert investigation.classification.confidence == 0.0
    assert "503" in investigation.classification.reason


async def test_the_parsed_fields_win_over_the_models_answer() -> None:
    """A label the adapter read is a fact; the model's version of it is not."""
    llm = ScriptedLLM(
        structured=[
            incident_classification(
                alert_name="SomethingElse", severity="low", components=["billing"]
            )
        ]
    )

    updates = await _stage(llm)(alertmanager_state())

    alert = updates.investigation.alert  # type: ignore[union-attr]
    assert alert is not None
    assert alert.alert_name == "HighErrorRate"
    assert alert.severity is Severity.CRITICAL
    assert alert.components == ("checkout", "billing"), "the model may add, never overwrite"


async def test_the_model_fills_what_the_payload_did_not_carry() -> None:
    llm = ScriptedLLM(structured=[incident_classification()])
    state = initial_state(RawAlert(text="checkout is throwing 500s", received_at=AT), team())

    updates = await _stage(llm)(state)

    alert = updates.investigation.alert  # type: ignore[union-attr]
    assert alert is not None
    assert alert.alert_source is AlertSource.PLAIN_TEXT
    assert alert.alert_name == "checkout is throwing 500s"
    assert alert.severity is Severity.CRITICAL
    assert alert.components == ("checkout",)


async def test_the_call_is_accounted_for() -> None:
    llm = ScriptedLLM(structured=[incident_classification()])

    updates = await _stage(llm)(alertmanager_state())

    assert updates.accounting is not None
    assert updates.accounting.llm_calls == 1
    assert updates.accounting.tokens.total_tokens > 0


# -- the incident window ------------------------------------------------------


def test_the_window_starts_before_the_alert_fired() -> None:
    """The change that caused the alert happened before the threshold was crossed."""
    started = AT - timedelta(minutes=10)
    alert = NormalisedAlert(alert_source=AlertSource.ALERTMANAGER, started_at=started)

    window = derive_window(alert, now=AT)

    assert window.start == started - timedelta(minutes=INCIDENT_WINDOW_LEAD_MINUTES)
    assert window.end == AT
    assert not window.is_fallback


def test_a_resolved_alert_bounds_the_window_at_its_end() -> None:
    started = AT - timedelta(minutes=30)
    ended = AT - timedelta(minutes=5)
    alert = NormalisedAlert(
        alert_source=AlertSource.ALERTMANAGER, started_at=started, ended_at=ended, resolved=True
    )

    assert derive_window(alert, now=AT).end == ended


def test_a_window_that_cannot_be_derived_falls_back_and_says_so() -> None:
    alert = NormalisedAlert(alert_source=AlertSource.PLAIN_TEXT)

    window = derive_window(alert, now=AT)

    assert window.end == AT
    assert window.start == AT - timedelta(minutes=DEFAULT_INCIDENT_WINDOW_MINUTES)
    assert window.is_fallback
    assert "default" in window.derivation


def test_a_start_time_in_the_future_falls_back_rather_than_producing_a_dead_window() -> None:
    """Clock skew between a vendor and this deployment is common, and a window
    that has not happened yet returns nothing from every downstream query."""
    alert = NormalisedAlert(alert_source=AlertSource.GRAFANA, started_at=AT + timedelta(hours=2))

    window = derive_window(alert, now=AT)

    assert window.is_fallback
    assert window.end == AT
    assert "future" in window.derivation


async def test_the_stage_records_the_window_it_derived() -> None:
    llm = ScriptedLLM(structured=[incident_classification()])

    updates = await _stage(llm)(alertmanager_state())

    window = updates.investigation.window  # type: ignore[union-attr]
    assert window is not None
    assert window.contains(AT - timedelta(minutes=5))


# -- deduplication ------------------------------------------------------------


async def test_an_alert_storm_produces_one_investigation_and_the_rest_are_links() -> None:
    """The normal case in production. Investigating the sixth copy costs a full
    run to reach the conclusion the first one reached."""
    index = InMemoryIncidentIndex()
    storm = 6
    outcomes = []

    for number in range(storm):
        llm = ScriptedLLM(structured=[incident_classification()])
        stage = IntakeStage(llm=llm, index=index, clock=fixed_clock())
        updates = await stage(alertmanager_state(run_id=f"run-{number}"))
        outcomes.append(updates.investigation)

    investigated = [found for found in outcomes if found is not None and found.link is None]
    linked = [found for found in outcomes if found is not None and found.link is not None]

    assert len(investigated) == 1
    assert len(linked) == storm - 1
    assert {found.link.incident_id for found in linked if found.link} == {"run-0"}
    assert all(found.outcome is not None for found in linked)
    assert all(found.outcome.kind is OutcomeKind.DUPLICATE for found in linked if found.outcome)


async def test_a_link_is_recorded_rather_than_the_alert_being_discarded() -> None:
    """Linking is non-destructive: the second alert is attached, never dropped."""
    index = InMemoryIncidentIndex()
    first = ScriptedLLM(structured=[incident_classification()])
    await IntakeStage(llm=first, index=index, clock=fixed_clock())(
        alertmanager_state(run_id="run-a")
    )

    second = ScriptedLLM(structured=[incident_classification()])
    updates = await IntakeStage(llm=second, index=index, clock=fixed_clock())(
        alertmanager_state(run_id="run-b")
    )

    investigation = updates.investigation
    assert investigation is not None
    assert investigation.alert is not None, "the duplicate alert is still recorded"
    assert investigation.link is not None
    assert investigation.link.incident_id == "run-a"
    assert investigation.halted


async def test_an_incident_outside_the_deduplication_window_is_investigated_again() -> None:
    index = InMemoryIncidentIndex()
    earlier = AT - timedelta(minutes=DEDUPLICATION_WINDOW_MINUTES + 5)

    first = ScriptedLLM(structured=[incident_classification()])
    await IntakeStage(llm=first, index=index, clock=fixed_clock(earlier))(
        alertmanager_state(run_id="run-a", at=earlier)
    )

    second = ScriptedLLM(structured=[incident_classification()])
    updates = await IntakeStage(llm=second, index=index, clock=fixed_clock())(
        alertmanager_state(run_id="run-b")
    )

    assert updates.investigation is not None
    assert updates.investigation.link is None


async def test_a_different_alert_is_not_linked_to_an_open_incident() -> None:
    index = InMemoryIncidentIndex()
    first = ScriptedLLM(structured=[incident_classification()])
    await IntakeStage(llm=first, index=index, clock=fixed_clock())(
        alertmanager_state(run_id="run-a")
    )

    other = alertmanager_state(run_id="run-b")
    other.raw.payload["alerts"][0]["labels"]["alertname"] = "DiskFilling"  # type: ignore[index]
    second = ScriptedLLM(structured=[incident_classification(alert_name="DiskFilling")])
    updates = await IntakeStage(llm=second, index=index, clock=fixed_clock())(other)

    assert updates.investigation is not None
    assert updates.investigation.link is None


async def test_a_greeting_is_never_linked_to_an_open_incident() -> None:
    """A duplicate has to be an incident first; attaching chatter to an
    investigation is worse than starting a second one."""
    index = InMemoryIncidentIndex()
    first = ScriptedLLM(structured=[incident_classification()])
    await IntakeStage(llm=first, index=index, clock=fixed_clock())(
        alertmanager_state(run_id="run-a")
    )

    chatter = ScriptedLLM(structured=[noise_classification()])
    updates = await IntakeStage(llm=chatter, index=index, clock=fixed_clock())(
        initial_state(RawAlert(text="morning all!", received_at=AT), team())
    )

    assert updates.investigation is not None
    assert updates.investigation.link is None
    assert updates.investigation.outcome is not None
    assert updates.investigation.outcome.kind is OutcomeKind.NOISE
    assert len(index.incidents) == 1, "a greeting must not open an incident either"


# -- what the stage is allowed to write ---------------------------------------


async def test_the_stage_names_itself() -> None:
    assert _stage(ScriptedLLM()).name is StageName.INTAKE


async def test_the_verdict_reaches_the_conversation() -> None:
    llm = ScriptedLLM(structured=[incident_classification()])
    state = alertmanager_state()

    updates = await _stage(llm)(state)

    assert updates.chat is not None
    assert updates.chat.messages[-1].author == StageName.INTAKE.value
    assert updates.chat.messages[-1].text == "an alert is firing on the checkout service"


def test_the_clock_defaults_to_now() -> None:
    stage = IntakeStage(llm=ScriptedLLM())

    assert stage.clock is None
    assert datetime.now(UTC) is not None
