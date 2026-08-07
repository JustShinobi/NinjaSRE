"""SC-002 and SC-006: the same scenario twice, and the suite with no tokens spent.

Two properties, and they are the same property seen from different ends. A run
is comparable to another run only if everything that could differ between them
has been pinned; and the strongest way to pin a model is to not call one, which
is what a recorded transcript is for.

Offline mode is not a lesser path. It is the path the pull-request gate uses,
because a suite that spent tokens on every push would be a suite people turned
off — and a regression gate nobody runs gates nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.harness.determinism import (
    DETERMINISTIC,
    DeterministicClient,
    is_deterministic,
)
from tests.harness.loader import Scenario
from tests.harness.offline import (
    Transcript,
    TranscriptExhausted,
    TranscriptPlayer,
    TranscriptRecorder,
    load_transcript,
    write_transcript,
)
from tests.harness.runner import run_scenario
from tests.unit.harness.test_runner import scripted

pytestmark = pytest.mark.unit


# -- determinism --------------------------------------------------------------


def test_the_deterministic_profile_pins_everything_a_request_can_vary_by() -> None:
    assert DETERMINISTIC.temperature == 0.0
    assert DETERMINISTIC.top_p == 1.0
    assert DETERMINISTIC.seed is not None


async def test_a_deterministic_client_disables_the_two_request_fields_that_can_drift(
    runnable_scenario: Scenario,
) -> None:
    """Prompt caching and reasoning effort are the ones this repository can set."""
    inner = scripted(runnable_scenario)
    client = DeterministicClient(inner=inner)

    await run_scenario(runnable_scenario, llm=client)

    assert client.requests
    for request in client.requests:
        assert request.prompt_cache is False
        assert request.reasoning_effort == DETERMINISTIC.reasoning_effort


def test_a_client_that_pins_nothing_is_not_reported_as_deterministic(
    runnable_scenario: Scenario,
) -> None:
    assert not is_deterministic(scripted(runnable_scenario))
    assert is_deterministic(DeterministicClient(inner=scripted(runnable_scenario)))


async def test_the_same_scenario_run_twice_produces_an_identical_trajectory(
    runnable_scenario: Scenario,
) -> None:
    """SC-002, on a deterministic provider configuration."""
    first = await run_scenario(
        runnable_scenario, llm=DeterministicClient(inner=scripted(runnable_scenario))
    )
    second = await run_scenario(
        runnable_scenario, llm=DeterministicClient(inner=scripted(runnable_scenario))
    )

    assert first.trajectory == second.trajectory
    assert first.root_cause_category == second.root_cause_category
    assert first.evidence_sources == second.evidence_sources
    assert [call.url for call in first.boundary.calls] == [
        call.url for call in second.boundary.calls
    ]
    assert first.iterations == second.iterations


# -- offline ------------------------------------------------------------------


async def test_a_transcript_is_recorded_during_a_run_and_reads_back(
    runnable_scenario: Scenario, tmp_path: Path
) -> None:
    """T030: recording is a wrapper on the live path, not a second code path."""
    recorder = TranscriptRecorder(inner=scripted(runnable_scenario))

    await run_scenario(runnable_scenario, llm=recorder)
    path = write_transcript(recorder.transcript(), tmp_path / "transcript.json")

    transcript = load_transcript(path)
    assert [entry.kind for entry in transcript.entries] == [
        "structured",
        "invoke",
        "invoke",
        "structured",
    ]
    assert json.loads(path.read_text(encoding="utf-8"))["entries"]


async def test_replaying_a_transcript_reproduces_the_run_it_was_recorded_from(
    runnable_scenario: Scenario, tmp_path: Path
) -> None:
    """FR-017: the offline path is the same investigation, without the model."""
    recorder = TranscriptRecorder(inner=scripted(runnable_scenario))
    live = await run_scenario(runnable_scenario, llm=recorder)
    path = write_transcript(recorder.transcript(), tmp_path / "transcript.json")

    replayed = await run_scenario(runnable_scenario, llm=TranscriptPlayer(load_transcript(path)))

    assert replayed.trajectory == live.trajectory
    assert replayed.root_cause_category == live.root_cause_category
    assert replayed.answer_text == live.answer_text


async def test_a_replayed_run_spends_no_tokens_at_all(
    runnable_scenario: Scenario, tmp_path: Path
) -> None:
    """SC-006: the pull-request path costs nothing."""
    recorder = TranscriptRecorder(inner=scripted(runnable_scenario))
    live = await run_scenario(runnable_scenario, llm=recorder)
    player = TranscriptPlayer(recorder.transcript())

    replayed = await run_scenario(runnable_scenario, llm=player)

    assert live.tokens > 0
    assert replayed.tokens == 0
    assert player.tokens_spent == 0


def test_a_replay_that_runs_past_its_transcript_says_so_rather_than_inventing_a_turn() -> None:
    """A diverged replay is a harness problem, and must not read as a scenario failure."""
    player = TranscriptPlayer(Transcript(entries=()))

    with pytest.raises(TranscriptExhausted):
        player.next_entry("invoke")


def test_a_transcript_player_is_deterministic_by_construction() -> None:
    assert is_deterministic(TranscriptPlayer(Transcript(entries=())))


async def test_a_recorded_transcript_carries_the_provider_it_came_from(
    runnable_scenario: Scenario,
) -> None:
    recorder = TranscriptRecorder(inner=scripted(runnable_scenario))
    await run_scenario(runnable_scenario, llm=recorder)

    transcript = recorder.transcript()

    assert transcript.provider_id == "scenario"
    assert transcript.model_id == "scenario-1"
    assert TranscriptPlayer(transcript).provider_id == "scenario"
