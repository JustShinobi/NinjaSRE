"""A real miss becomes a synthetic scenario that reproduces the miss.

This is the feedback loop the whole feature exists for, and it is asserted the
only way that means anything: by doing it. A live investigation is driven through
the real client path with a recording transport and a recording provider, it
reaches the wrong conclusion, the run is captured, and the captured directory is
then loaded by the ordinary scenario loader and run by the ordinary scenario
runner with no provider at all — and it fails the same way.

If any link in that chain were a stand-in, the test would prove that capture
writes files. As written, it proves that what capture writes is a scenario.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.constants.chaos import CAPTURE_REVIEW_MARKER
from core.state.types import TeamContext
from tests.e2e.capture import (
    CapturedRun,
    CaptureError,
    Exchange,
    RecordingTransport,
    capture,
    verify_scrubbed,
)
from tests.harness.backends.base import stand_up
from tests.harness.investigator import PipelineInvestigator
from tests.harness.loader import load_scenario
from tests.harness.offline import TranscriptPlayer, TranscriptRecorder, load_transcript
from tests.harness.realruns import RealRunExpectation, RunValidity, score_real_run
from tests.harness.runner import SCENARIO_CLOCK, SCENARIO_ORG_ID, alert_for, run_scenario
from tests.harness.scoring.composite import score_run

CORPUS = Path(__file__).resolve().parents[3] / "tests" / "synthetic" / "kubernetes"

#: What the run this test captures is scored against. Deliberately the OOM
#: scenario's own truth, driven by a provider that concludes something else — so
#: the miss is a real scoring failure rather than a contrived one.
MISSED = RealRunExpectation(
    key="chaos/memory-stress",
    suite="chaos",
    scenario_id="memory-stress",
    failure_mode="memory_exhaustion",
    severity="critical",
    difficulty=2,
    root_cause_category="resource_exhaustion",
    required_keywords=("memory", "limit", "oomkilled"),
    forbidden_categories=("healthy", "unknown"),
    required_evidence_sources=("kubernetes",),
    integrations=("kubernetes",),
    available_evidence=("kubernetes",),
    title="checkout is driven past its memory limit",
)


class WrongConclusion:
    """A provider that reads the evidence and then concludes something else.

    Wraps the recorded transcript rather than replacing it, so the tool calls —
    and therefore the vendor exchanges the capture is made of — are the real
    ones. Only the final structured answer differs, which is what an agent
    getting it wrong actually looks like.
    """

    def __init__(self, inner: TranscriptPlayer) -> None:
        self._inner = inner

    @property
    def provider_id(self) -> str:
        return "recorded"

    @property
    def model_id(self) -> str:
        return "recorded-transcript"

    async def invoke(self, request: object) -> object:
        return await self._inner.invoke(request)  # type: ignore[arg-type]

    async def invoke_structured(self, request: object, schema: object) -> object:
        result = await self._inner.invoke_structured(request, schema)  # type: ignore[arg-type]
        structured = dict(result.structured or {})
        if "root_cause_category" in structured:
            structured["root_cause_category"] = "unknown"
            structured["root_cause"] = "nothing conclusive was established"
            structured["summary"] = "the investigation did not settle on a cause"
            structured["causal_chain"] = []
            from dataclasses import replace

            return replace(result, structured=structured)
        return result

    def count_tokens(self, request: object) -> object:
        return self._inner.count_tokens(request)  # type: ignore[arg-type]

    async def stream(self, request: object) -> object:  # pragma: no cover - unused
        raise NotImplementedError


async def _a_real_miss() -> CapturedRun:
    """Return a genuine investigation that went through the real path and was wrong."""
    scenario = load_scenario(CORPUS / "001-oom-kill")
    assert scenario.transcript_path is not None

    stack = await stand_up(
        scenario.integrations,
        scenario.evidence,
        org_id=SCENARIO_ORG_ID,
        team_id=scenario.team_id,
        at=SCENARIO_CLOCK,
    )
    transport = RecordingTransport(inner=stack.transport)
    llm = TranscriptRecorder(
        inner=WrongConclusion(TranscriptPlayer(load_transcript(scenario.transcript_path))),
        scenario=MISSED.key,
    )

    alert = alert_for(scenario)
    live = await PipelineInvestigator(
        llm=llm, transport=transport, org_id=SCENARIO_ORG_ID
    ).investigate(
        alert,
        team=TeamContext(
            team_id=scenario.team_id, integrations=scenario.integrations, destinations=()
        ),
        run_id="captured-1",
    )

    return CapturedRun(
        expectation=MISSED,
        alert=alert,
        observation=live.observation,
        exchanges=tuple(transport.exchanges),
        transcript=llm.transcript(),
    )


async def test_the_run_being_captured_is_a_real_scored_miss() -> None:
    """The premise. Without it the rest of this file captures a passing run."""
    run = await _a_real_miss()

    score = score_real_run(MISSED, run.observation, validity=RunValidity.VALID)

    assert score.agent_failure
    assert "accuracy" in (score.score.failed_axes if score.score is not None else ())


async def test_a_real_miss_becomes_a_synthetic_scenario_that_reproduces_it(
    tmp_path: Path,
) -> None:
    run = await _a_real_miss()

    result = capture(run, root=tmp_path, scenario_id="001-captured-memory-stress")

    # It loads as an ordinary scenario, with no knowledge that it was captured.
    captured = load_scenario(result.directory, root=tmp_path)
    assert captured.offline_ready
    assert captured.evidence

    # And it runs, offline, and misses in the same way the real run did.
    assert captured.transcript_path is not None
    replayed = await run_scenario(
        captured, llm=TranscriptPlayer(load_transcript(captured.transcript_path))
    )
    score = score_run(replayed)

    assert not score.passed
    assert "accuracy" in score.failed_axes


async def test_nothing_detectable_is_written_into_a_captured_scenario(
    tmp_path: Path,
) -> None:
    """A file in version control is not un-committed by deleting it later."""
    run = await _a_real_miss()

    result = capture(run, root=tmp_path, scenario_id="001-captured-memory-stress")

    assert verify_scrubbed(result.directory) == ()


async def test_the_drafted_answer_key_says_it_is_a_draft(tmp_path: Path) -> None:
    run = await _a_real_miss()

    result = capture(run, root=tmp_path, scenario_id="001-captured-memory-stress")

    answer = (result.directory / "answer.yml").read_text(encoding="utf-8")
    assert CAPTURE_REVIEW_MARKER in answer
    assert result.review
    assert any("golden trajectory" in note for note in result.review)


async def test_a_run_that_recorded_nothing_is_refused(tmp_path: Path) -> None:
    """A scenario with no evidence would offer the agent nothing to read."""
    from core.domain.alerts.normalisation import RawAlert

    run = CapturedRun(
        expectation=MISSED,
        alert=RawAlert(text="nothing"),
        observation=(await _a_real_miss()).observation,
        exchanges=(),
    )

    with pytest.raises(CaptureError, match="no vendor exchanges"):
        capture(run, root=tmp_path)


def test_an_exchange_knows_the_path_a_fixture_matches_it_by() -> None:
    exchange = Exchange(
        integration="kubernetes",
        method="GET",
        url="https://cluster.example/api/v1/namespaces/payments/events?limit=10",
    )

    assert exchange.path == "/api/v1/namespaces/payments/events"
