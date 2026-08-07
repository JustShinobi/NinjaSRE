"""The seed corpus, run end to end, offline, on every commit.

This is the gate the whole evaluation half stands on, and it is deliberately
the cheap one: every scenario ships a recorded transcript, so the suite runs
with no credential, no network, and no tokens (SC-001, SC-006). The expensive
run — a real provider against the same fixtures — is the same code with a
different client.

Seven properties are asserted here and each is a success criterion:

* the corpus loads, which means every fixture validates (SC-003 in anger);
* it runs with nothing configured (SC-001);
* twice, identically (SC-002);
* for nothing (SC-006);
* it is reportable by difficulty, and the ladder is populated (SC-007);
* it finishes inside the pull-request budget (SC-008);
* and a scenario for an integration the harness has never heard of runs on
  fixtures alone (SC-005).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from config.constants.evaluation import (
    SCENARIO_ADVERSARIAL_FROM_DIFFICULTY,
    SCENARIO_DIFFICULTY_MAX,
    SCENARIO_DIFFICULTY_MIN,
    TIER_ONE_SUITE_BUDGET_SECONDS,
)
from tests.harness.artifacts import verdict_for
from tests.harness.determinism import is_deterministic
from tests.harness.loader import Scenario, load_scenario
from tests.harness.offline import TranscriptPlayer, load_transcript
from tests.harness.runner import run_scenario
from tests.harness.suite import load_suite, report_for, run_suite

pytestmark = pytest.mark.synthetic

#: Where the corpus lives. Scenarios are directories beside this file, which is
#: what makes contributing one a matter of adding fixtures (SC-005).
CORPUS_ROOT = Path(__file__).parent


def replayed(scenario: Scenario, attempt: int = 1) -> TranscriptPlayer:
    """Return the recorded provider for ``scenario``.

    Raises:
        AssertionError: the scenario ships no transcript, so it cannot run on
            the pull-request path at all.
    """
    assert scenario.transcript_path is not None, (
        f"{scenario.key} ships no transcript, so the offline gate cannot run it; "
        f"record one rather than letting the corpus quietly shrink"
    )
    return TranscriptPlayer(load_transcript(scenario.transcript_path))


def corpus() -> tuple[Scenario, ...]:
    """Return every scenario in the repository, loaded and validated."""
    return load_suite(CORPUS_ROOT)


# -- the corpus itself --------------------------------------------------------


def test_every_scenario_in_the_repository_loads() -> None:
    """A malformed fixture is a load error, and this is where it surfaces."""
    scenarios = corpus()

    assert len(scenarios) >= 7
    assert len({found.key for found in scenarios}) == len(scenarios)


def test_the_curriculum_is_populated_at_every_level() -> None:
    """FR-021: a ladder with a rung missing cannot show a gradient."""
    levels = {found.difficulty for found in corpus()}

    assert levels == set(range(SCENARIO_DIFFICULTY_MIN, SCENARIO_DIFFICULTY_MAX + 1))


def test_every_confounded_scenario_plants_its_confounders_in_the_evidence() -> None:
    """FR-022, T042: resistance is only measurable against evidence the agent saw."""
    for scenario in corpus():
        if scenario.difficulty < SCENARIO_ADVERSARIAL_FROM_DIFFICULTY:
            continue
        carried = {
            signal for fixture in scenario.evidence for signal in fixture.adversarial_signals
        }
        assert set(scenario.adversarial_signals) <= carried, scenario.key
        assert scenario.answer.ruling_out_keywords, (
            f"{scenario.key} plants confounders and asserts nothing about ruling them out, "
            f"so the suite cannot report resistance separately from accuracy"
        )


def test_every_scenario_ships_a_transcript_so_the_gate_stays_free() -> None:
    """SC-006's precondition: the pull-request path must never need a provider."""
    for scenario in corpus():
        assert scenario.offline_ready, scenario.key


# -- running it ---------------------------------------------------------------


async def test_the_whole_corpus_runs_with_no_credentials_and_no_cloud_access() -> None:
    """SC-001."""
    result = await run_suite(corpus(), provider=replayed)
    report = report_for(result)

    assert report.attempts == len(corpus())
    assert not report.permanently_unsolved, [found.key for found in report.permanently_unsolved]
    for run in result.runs:
        assert run.run.succeeded, (run.scenario.key, run.run.failure)
        assert run.boundary.calls, f"{run.scenario.key} reached no vendor at all"


async def test_every_recorded_fixture_is_actually_reached_by_its_scenario() -> None:
    """A scenario whose fixtures never match is measuring the empty fallback."""
    result = await run_suite(corpus(), provider=replayed)

    for run in result.runs:
        assert not run.boundary.unmatched, (
            run.scenario.key,
            [call.url for call in run.boundary.unmatched],
        )


async def test_the_whole_corpus_spends_no_tokens() -> None:
    """SC-006."""
    result = await run_suite(corpus(), provider=replayed)

    assert sum(run.tokens for run in result.runs) == 0


async def test_a_scenario_produces_an_identical_trajectory_across_two_runs() -> None:
    """SC-002, on the configuration the gate actually uses."""
    scenario = load_suite(CORPUS_ROOT, scenario_id="002-liveness")[0]
    assert is_deterministic(replayed(scenario))

    first = await run_scenario(scenario, llm=replayed(scenario))
    second = await run_scenario(scenario, llm=replayed(scenario))

    assert first.trajectory == second.trajectory
    assert first.root_cause_category == second.root_cause_category
    assert first.evidence_sources == second.evidence_sources
    assert [call.url for call in first.boundary.calls] == [
        call.url for call in second.boundary.calls
    ]


async def test_results_are_reportable_by_difficulty_level() -> None:
    """SC-007: an improvement that only helped the easy cases has to be visible."""
    report = report_for(await run_suite(corpus(), provider=replayed))

    levels = report.by_difficulty()
    assert [level.difficulty for level in levels] == [1, 2, 3, 4]
    for level in levels:
        assert level.description
        assert level.attempts >= 1
    assert report.to_record()["by_difficulty"][0]["solve_rate"] >= 0.0


async def test_the_suite_reports_a_solve_rate_per_scenario() -> None:
    """T043: permanently-unsolved and trivially-solved scenarios must be visible."""
    report = report_for(await run_suite(corpus(), provider=replayed, attempts=2))

    for found in report.scenarios:
        assert found.attempts == 2
        assert 0.0 <= found.solve_rate <= 1.0
    assert len(report.trivially_solved) + len(report.permanently_unsolved) <= len(report.scenarios)


async def test_the_offline_corpus_finishes_inside_the_pull_request_budget() -> None:
    """SC-008."""
    result = await run_suite(corpus(), provider=replayed)

    assert result.duration_seconds < TIER_ONE_SUITE_BUDGET_SECONDS


async def test_a_verdict_record_is_written_for_every_attempt_when_asked_for(
    tmp_path: Path,
) -> None:
    """FR-018 across the whole corpus, not only against a synthetic fixture."""
    from tests.harness.artifacts import ArtifactWriter, read_records

    writer = ArtifactWriter(path=tmp_path / "verdicts.jsonl")
    report_for(await run_suite(corpus(), provider=replayed), writer=writer)

    records = read_records(tmp_path / "verdicts.jsonl")
    assert len(records) == len(corpus())
    for record in records:
        assert record["suite"] and record["scenario"]
        assert record["axes"]


# -- SC-005: a new integration needs fixtures and an answer key, and no code --


def _sentry_scenario(root: Path) -> Path:
    """Write a scenario for an integration the harness has no backend module for."""
    directory = root / "incidents" / "008-unresolved-error-spike"
    directory.mkdir(parents=True)

    (directory / "scenario.yml").write_text(
        "schema_version: '1'\n"
        "scenario_id: 008-unresolved-error-spike\n"
        "title: an unresolved out-of-memory issue dominates the error stream\n"
        "failure_mode: memory_exhaustion\n"
        "severity: critical\n"
        "scenario_difficulty: 1\n"
        "adversarial_signals: []\n"
        "available_evidence: [sentry]\n"
        "integrations: [sentry]\n"
        "team_id: payments\n",
        encoding="utf-8",
    )
    (directory / "alert.json").write_text(
        json.dumps(
            {
                "text": "checkout is throwing OutOfMemory errors",
                "received_at": "2026-08-07T12:30:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (directory / "sentry.json").write_text(
        json.dumps(
            {
                "integration": "sentry",
                "responses": [
                    {
                        "match": {"method": "GET", "path_contains": "/issues/"},
                        "status": 200,
                        "content_type": "application/json",
                        "body": [
                            {"id": "1", "title": "OutOfMemory", "level": "error", "count": "412"},
                            {"id": "2", "title": "TimeoutError", "level": "error", "count": "38"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (directory / "answer.yml").write_text(
        "root_cause_category: resource_exhaustion\n"
        "required_keywords: [OutOfMemory, unresolved]\n"
        "required_evidence_sources: [sentry]\n"
        "optimal_trajectory: [sentry_log_statistics]\n"
        "max_investigation_loops: 4\n"
        "model_response: |\n"
        "  ROOT_CAUSE: checkout is running out of memory.\n",
        encoding="utf-8",
    )
    (directory / "transcript.json").write_text(
        json.dumps(
            {
                "provider_id": "recorded",
                "model_id": "recorded-transcript",
                "entries": [
                    {
                        "kind": "structured",
                        "structured": {
                            "is_incident": True,
                            "confidence": 0.93,
                            "reason": "an error class is dominating the stream",
                            "alert_name": "OutOfMemory",
                            "severity": "critical",
                            "summary": "checkout is throwing OutOfMemory errors",
                            "components": ["checkout"],
                            "error_text": "OutOfMemory",
                        },
                    },
                    {
                        "kind": "invoke",
                        "finish_reason": "tool_calls",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "name": "sentry_log_statistics",
                                "arguments": {
                                    "query": "is:unresolved",
                                    "start": "",
                                    "end": "",
                                    "group_by": "level",
                                },
                            }
                        ],
                    },
                    {
                        "kind": "invoke",
                        "finish_reason": "stop",
                        "text": (
                            "The unresolved issue stream is dominated by OutOfMemory with 412 "
                            "occurrences [e1]."
                        ),
                    },
                    {
                        "kind": "structured",
                        "structured": {
                            "root_cause": "checkout is running out of memory",
                            "root_cause_category": "resource_exhaustion",
                            "summary": (
                                "412 unresolved OutOfMemory events dominate the error stream [e1]."
                            ),
                            "causal_chain": ["memory use grew", "the process died"],
                            "claims": [],
                            "remediation_steps": ["raise the memory limit"],
                            "recommended_actions": ["raise the memory limit"],
                            "contributing_factors": [],
                            "confidence": 0.81,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory


async def test_a_scenario_for_an_integration_with_no_backend_module_runs_on_fixtures_alone(
    tmp_path: Path,
) -> None:
    """SC-005: fixtures and an answer key, and not one line of harness code."""
    from tests.harness.backends import registry

    assert "sentry" not in registry(), (
        "this test is only meaningful while nothing declares a backend for sentry"
    )
    directory = _sentry_scenario(tmp_path)

    scenario = load_scenario(directory, root=tmp_path)
    run = await run_scenario(scenario, llm=replayed(scenario))
    verdict = verdict_for(run)

    assert run.run.succeeded
    assert run.trajectory == ("sentry_log_statistics",)
    assert run.evidence_sources == ("sentry",)
    assert verdict.passed, verdict.failed_axes


def test_the_corpus_directory_is_discovered_rather_than_listed(tmp_path: Path) -> None:
    """Adding a directory adds a scenario; nothing registers anything."""
    before = len(load_suite(CORPUS_ROOT))
    _sentry_scenario(tmp_path)

    assert len(load_suite(tmp_path)) == 1
    assert len(load_suite(CORPUS_ROOT)) == before


def test_a_report_serialises_to_something_a_ci_job_can_publish() -> None:
    from tests.harness.suite import SuiteReport

    record: dict[str, Any] = SuiteReport().to_record()

    assert record["attempts"] == 0
    assert record["by_difficulty"] == []
