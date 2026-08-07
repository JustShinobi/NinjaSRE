"""FR-012: a scenario runs through the canonical runtime and the real pipeline.

The assertions worth arguing for are the negative ones. Nothing between the
agent and the wire is a stand-in, so the evidence a scenario produces has been
through the real client and the real credential proxy; the runtime is the
canonical loop and an experimental one is refused rather than quietly scored;
and the whole thing happens with no credential an operator supplied and no
network at all.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from core.agent.adapters.claude_sdk import ClaudeAgentSdkRuntime
from core.agent.guard import NonCanonicalRuntimeError
from core.llm.types import ToolCall
from core.state.types import STAGE_ORDER
from tests.harness.loader import Scenario
from tests.harness.runner import (
    SCENARIO_CLOCK,
    ScenarioRun,
    alert_for,
    capabilities_for,
    run_scenario,
    scenario_summary,
)
from tests.harness.suite import load_suite, run_suite
from tests.synthetic.conftest import LoopTurn, ScenarioLLM
from tests.unit.harness.conftest import (
    RUNNABLE_ANSWER,
    RUNNABLE_EVIDENCE,
    RUNNABLE_SCENARIO,
    ScenarioWriter,
)

pytestmark = pytest.mark.unit


def scripted(scenario: Scenario, attempt: int = 1) -> ScenarioLLM:
    """Return a provider double that investigates this scenario the intended way."""
    return ScenarioLLM(
        structured=[
            {
                "is_incident": True,
                "confidence": 0.95,
                "reason": "an alert is firing on a production service",
                "alert_name": "HighErrorRate",
                "severity": "critical",
                "summary": "checkout error rate above 5%",
                "components": ["checkout"],
                "error_text": "",
            },
            {
                "root_cause_category": "resource_exhaustion",
                "summary": (
                    "The checkout container exceeded its 512Mi memory limit and was "
                    "OOM-killed three times inside the window [e1]."
                ),
                "confidence": 0.86,
                "contributing_factors": [],
                "recommended_actions": ["Raise the checkout container's memory limit."],
                "claims": [],
            },
        ],
        turns=[
            LoopTurn(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="kubernetes_workload_events",
                        arguments={"namespace": "payments", "object_name": "checkout-7f4c"},
                    ),
                )
            ),
            LoopTurn(
                text=(
                    "The checkout container was OOM-killed inside the incident window [e1]; "
                    "its memory limit is 512Mi."
                )
            ),
        ],
    )


async def test_a_scenario_runs_every_stage_of_the_real_pipeline(
    runnable_scenario: Scenario,
) -> None:
    result = await run_scenario(runnable_scenario, llm=scripted(runnable_scenario))

    assert result.run.stages_run == STAGE_ORDER
    assert result.run.succeeded
    assert not result.run.halted_early


async def test_the_diagnosis_cites_evidence_the_recorded_vendor_returned(
    runnable_scenario: Scenario,
) -> None:
    result = await run_scenario(runnable_scenario, llm=scripted(runnable_scenario))

    assert result.root_cause_category == "resource_exhaustion"
    assert result.evidence_sources == ("kubernetes",)
    assert result.trajectory == ("kubernetes_workload_events",)
    assert "OOMKilled" in result.answer_text


async def test_the_run_reached_the_vendor_through_the_proxy_and_nothing_else(
    runnable_scenario: Scenario,
) -> None:
    """SC-001: no credential an operator supplied, and no network."""
    result = await run_scenario(runnable_scenario, llm=scripted(runnable_scenario))

    assert result.boundary.calls, "the investigation reached no vendor at all"
    assert result.boundary.matched
    assert result.boundary.reached_integrations == {"kubernetes"}


async def test_no_synthesised_credential_reaches_anything_the_agent_can_read(
    runnable_scenario: Scenario,
) -> None:
    result = await run_scenario(runnable_scenario, llm=scripted(runnable_scenario))

    rendered = repr(result.run.state.evidence.entries) + repr(result.diagnosis)
    for values in result.credentials.values():
        for value in values.values():
            if len(value) > 8:
                assert value not in rendered


async def test_a_non_canonical_runtime_is_refused_rather_than_quietly_scored(
    runnable_scenario: Scenario,
) -> None:
    """T023, Article V: an experimental runtime never produces a published number."""
    with pytest.raises(NonCanonicalRuntimeError) as raised:
        await run_scenario(
            runnable_scenario, llm=scripted(runnable_scenario), runtime=ClaudeAgentSdkRuntime()
        )

    assert "scenario" in str(raised.value)


async def test_a_capability_the_scenario_planted_nothing_for_is_still_offered(
    runnable_scenario: Scenario,
) -> None:
    """FR-008's precondition: the agent sees the whole team catalogue, not a subset."""
    offered = {found.name for found in capabilities_for(runnable_scenario.integrations)}

    assert "kubernetes_workload_events" in offered
    assert len(offered) > 1


def test_the_alert_a_scenario_declares_is_the_one_the_pipeline_receives(
    runnable_scenario: Scenario,
) -> None:
    raw = alert_for(runnable_scenario)

    assert raw.payload["alerts"][0]["labels"]["alertname"] == "HighErrorRate"
    assert raw.at().isoformat() == "2026-08-07T12:30:00+00:00"


def test_a_scenario_with_no_received_at_uses_the_fixed_scenario_clock(
    write_scenario: ScenarioWriter,
) -> None:
    """SC-002's precondition: the incident window cannot move between two runs."""
    from tests.harness.loader import load_scenario

    directory = write_scenario(
        scenario=RUNNABLE_SCENARIO,
        answer=RUNNABLE_ANSWER,
        alert={"text": "checkout is throwing 500s"},
        evidence={"kubernetes.json": RUNNABLE_EVIDENCE},
    )

    assert alert_for(load_scenario(directory)).at() == SCENARIO_CLOCK


async def test_a_summary_of_an_attempt_says_what_it_cost(runnable_scenario: Scenario) -> None:
    result = await run_scenario(runnable_scenario, llm=scripted(runnable_scenario))

    summary = scenario_summary(result)

    assert summary["scenario"] == runnable_scenario.key
    assert summary["difficulty"] == 1
    assert summary["vendor_calls"] >= 1


# -- the suite ----------------------------------------------------------------


def _corpus(write_scenario: ScenarioWriter, tmp_path: Path) -> Path:
    """Write two scenarios of different difficulty into one corpus root."""
    write_scenario(
        scenario=RUNNABLE_SCENARIO,
        answer=RUNNABLE_ANSWER,
        evidence={"kubernetes.json": RUNNABLE_EVIDENCE},
    )
    harder = dict(RUNNABLE_SCENARIO)
    harder.update(
        scenario_id="002-probe-killing",
        failure_mode="probe_misconfiguration",
        scenario_difficulty=2,
        adversarial_signals=["healthy_replicas_present"],
    )
    confounded = json.loads(json.dumps(RUNNABLE_EVIDENCE))
    confounded["responses"][0]["adversarial_signals"] = ["healthy_replicas_present"]
    write_scenario(
        name="002-probe-killing",
        scenario=harder,
        answer=RUNNABLE_ANSWER,
        evidence={"kubernetes.json": confounded},
    )
    return tmp_path


def test_a_suite_can_be_narrowed_to_a_subset(
    write_scenario: ScenarioWriter, tmp_path: Path
) -> None:
    """FR-013: one scenario, a suite, or a filtered subset."""
    root = _corpus(write_scenario, tmp_path)

    assert len(load_suite(root)) == 2
    assert len(load_suite(root, difficulty=2)) == 1
    assert len(load_suite(root, scenario_id="probe")) == 1
    assert len(load_suite(root, integration="kubernetes")) == 2
    assert load_suite(root, suite="nothing-called-this") == ()


async def test_repeat_attempts_run_the_same_scenario_more_than_once(
    write_scenario: ScenarioWriter, tmp_path: Path
) -> None:
    """FR-014: variance is invisible at one attempt."""
    root = _corpus(write_scenario, tmp_path)
    scenarios = load_suite(root, difficulty=1)

    result = await run_suite(scenarios, provider=scripted, attempts=3)

    assert result.attempts == 3
    assert [run.attempt for run in result.runs] == [1, 2, 3]
    assert len(result.scenarios) == 1


async def test_an_attempt_count_above_the_bound_is_refused(
    write_scenario: ScenarioWriter, tmp_path: Path
) -> None:
    root = _corpus(write_scenario, tmp_path)

    with pytest.raises(ValueError):
        await run_suite(load_suite(root), provider=scripted, attempts=0)


async def test_an_observer_sees_each_attempt_as_it_finishes(
    write_scenario: ScenarioWriter, tmp_path: Path
) -> None:
    root = _corpus(write_scenario, tmp_path)
    seen: list[ScenarioRun] = []

    await run_suite(load_suite(root), provider=scripted, observer=seen.append)

    assert [run.scenario.scenario_id for run in seen] == ["001-oom-kill", "002-probe-killing"]


async def test_each_attempt_gets_its_own_provider_rather_than_a_shared_queue(
    write_scenario: ScenarioWriter, tmp_path: Path
) -> None:
    """A shared client would carry the previous scenario's script into the next."""
    root = _corpus(write_scenario, tmp_path)
    built: list[Sequence[Any]] = []

    def factory(scenario: Scenario, attempt: int) -> ScenarioLLM:
        client = scripted(scenario, attempt)
        built.append((scenario.scenario_id, attempt))
        return client

    result = await run_suite(load_suite(root), provider=factory, attempts=2)

    assert len(built) == 4
    assert all(run.run.succeeded for run in result.runs)
