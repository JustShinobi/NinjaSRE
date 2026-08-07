"""SC-004: a verdict record explains a failure without anybody re-running it.

The test that matters most here is the last one. Three failures are induced —
the wrong category, a missing keyword, an investigation that never looked at the
evidence — and the assertion is that each record says, on its own, which of the
three happened and what the run did instead. A record that only said ``false``
would send the reader back to the corpus with a stopwatch.

Records are off unless an environment variable names a file (FR-020). A normal
run pays nothing for an artefact nobody asked for, and turning them on is one
variable rather than a flag every caller has to thread through.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.constants.evaluation import NINJASRE_SCENARIO_ARTIFACTS_ENV, VERDICT_AXES
from tests.harness.artifacts import (
    ArtifactWriter,
    Verdict,
    verdict_for,
    writer_from_environment,
)
from tests.harness.loader import Scenario, load_scenario
from tests.harness.runner import run_scenario
from tests.unit.harness.conftest import (
    RUNNABLE_ANSWER,
    RUNNABLE_EVIDENCE,
    RUNNABLE_SCENARIO,
    ScenarioWriter,
)
from tests.unit.harness.test_runner import scripted

pytestmark = pytest.mark.unit


async def _verdict(scenario: Scenario) -> Verdict:
    return verdict_for(await run_scenario(scenario, llm=scripted(scenario)))


# -- what a record says -------------------------------------------------------


async def test_a_passing_attempt_records_every_axis_its_answer_key_asserted(
    runnable_scenario: Scenario,
) -> None:
    verdict = await _verdict(runnable_scenario)

    assert verdict.passed, verdict.failed_axes
    assert {axis.name for axis in verdict.axes} <= set(VERDICT_AXES)
    assert {axis.name for axis in verdict.axes} >= {
        "root_cause_category",
        "required_keywords",
        "required_evidence_sources",
        "investigation_loops",
    }


async def test_a_record_carries_the_scenario_and_the_run_it_describes(
    runnable_scenario: Scenario,
) -> None:
    """FR-018: suite, scenario, attempt, outcome, difficulty, failure mode, root cause."""
    record = (await _verdict(runnable_scenario)).to_record()

    assert record["suite"] == "kubernetes"
    assert record["scenario"] == "001-oom-kill"
    assert record["attempt"] == 1
    assert record["passed"] is True
    assert record["difficulty"] == 1
    assert record["failure_mode"] == "memory_exhaustion"
    assert record["agent_root_cause_category"] == "resource_exhaustion"
    assert record["expected_root_cause_category"] == "resource_exhaustion"
    assert record["axes"]


async def test_a_record_says_what_the_run_did_and_not_only_what_it_should_have(
    runnable_scenario: Scenario,
) -> None:
    """FR-019: reconstructing the failure must not need the run back."""
    record = (await _verdict(runnable_scenario)).to_record()

    assert record["trajectory"] == ["kubernetes_workload_events"]
    assert record["evidence_sources"] == ["kubernetes"]
    assert record["vendor_calls"]
    assert record["iterations"] >= 1
    assert record["determinism"]["temperature"] == 0.0


# -- three induced failures, diagnosed from the record alone -----------------


async def test_a_wrong_category_is_named_with_what_the_agent_said_instead(
    write_scenario: ScenarioWriter,
) -> None:
    answer = dict(RUNNABLE_ANSWER)
    answer["root_cause_category"] = "deployment_regression"
    answer["forbidden_categories"] = ["resource_exhaustion"]
    scenario = load_scenario(
        write_scenario(
            scenario=RUNNABLE_SCENARIO,
            answer=answer,
            evidence={"kubernetes.json": RUNNABLE_EVIDENCE},
        )
    )

    verdict = await _verdict(scenario)
    axis = verdict.axis("root_cause_category")

    assert not verdict.passed
    assert "root_cause_category" in verdict.failed_axes
    assert axis is not None and not axis.passed
    assert axis.observed == ("resource_exhaustion",)
    assert axis.expected == ("deployment_regression",)


async def test_a_missing_keyword_names_the_keyword_rather_than_only_failing(
    write_scenario: ScenarioWriter,
) -> None:
    answer = dict(RUNNABLE_ANSWER)
    answer["required_keywords"] = ["memory", "connection pool"]
    scenario = load_scenario(
        write_scenario(
            scenario=RUNNABLE_SCENARIO,
            answer=answer,
            evidence={"kubernetes.json": RUNNABLE_EVIDENCE},
        )
    )

    axis = (await _verdict(scenario)).axis("required_keywords")

    assert axis is not None and not axis.passed
    assert axis.missing == ("connection pool",)
    assert "memory" in axis.observed


async def test_an_investigation_that_never_reached_the_evidence_says_which_source(
    write_scenario: ScenarioWriter,
) -> None:
    answer = dict(RUNNABLE_ANSWER)
    answer["required_evidence_sources"] = ["kubernetes"]
    scenario = load_scenario(
        write_scenario(
            scenario=RUNNABLE_SCENARIO,
            answer=answer,
            evidence={"kubernetes.json": RUNNABLE_EVIDENCE},
        )
    )
    # A provider that concludes without calling anything: the failure mode a
    # confident model produces, and the one a bare pass/fail explains worst.
    from tests.synthetic.conftest import LoopTurn, ScenarioLLM

    silent = ScenarioLLM(
        structured=[
            {
                "is_incident": True,
                "confidence": 0.9,
                "reason": "an alert is firing",
                "alert_name": "HighErrorRate",
                "severity": "critical",
                "summary": "checkout error rate above 5%",
                "components": ["checkout"],
                "error_text": "",
            },
            {
                "root_cause_category": "resource_exhaustion",
                "summary": "The container hit its memory limit.",
                "confidence": 0.5,
                "contributing_factors": [],
                "recommended_actions": [],
                "claims": [],
            },
        ],
        turns=[LoopTurn(text="The container hit its memory limit.")],
    )

    verdict = verdict_for(await run_scenario(scenario, llm=silent))
    axis = verdict.axis("required_evidence_sources")

    assert not verdict.passed
    assert axis is not None and not axis.passed
    assert axis.missing == ("kubernetes",)
    assert verdict.to_record()["trajectory"] == []
    assert verdict.to_record()["vendor_calls"] == []


# -- writing records ----------------------------------------------------------


async def test_records_are_not_written_unless_the_environment_asks_for_them(
    runnable_scenario: Scenario, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """FR-020: a normal run pays nothing."""
    monkeypatch.delenv(NINJASRE_SCENARIO_ARTIFACTS_ENV, raising=False)

    writer = writer_from_environment()
    writer.write(await _verdict(runnable_scenario))

    assert writer.path is None
    assert writer.written == 0
    assert not list(tmp_path.glob("*.jsonl"))


async def test_the_environment_variable_turns_records_on_and_names_the_file(
    runnable_scenario: Scenario, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "runs" / "verdicts.jsonl"
    monkeypatch.setenv(NINJASRE_SCENARIO_ARTIFACTS_ENV, str(target))

    writer = writer_from_environment()
    writer.write(await _verdict(runnable_scenario))
    writer.write(await _verdict(runnable_scenario))

    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["scenario"] == "001-oom-kill"


async def test_every_record_is_one_json_line_so_a_suite_appends_rather_than_rewrites(
    runnable_scenario: Scenario, tmp_path: Path
) -> None:
    writer = ArtifactWriter(path=tmp_path / "verdicts.jsonl")

    writer.write(await _verdict(runnable_scenario))

    body = (tmp_path / "verdicts.jsonl").read_text(encoding="utf-8")
    assert body.endswith("\n")
    assert "\n" not in body.strip()
