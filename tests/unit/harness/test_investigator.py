"""The composition root the real-infrastructure suites use, driven end to end.

Chaos and end-to-end investigations have to go through the *real* integrations
rather than through anything the suite built for itself. That is a
claim about a code path, and the way to assert it without a cluster is to point
the same code path at the harness's own vendor boundary: the capability, the
integration client, the transport, and the credential proxy are then all the
production ones, and only the bytes at the far end are recorded.

If this test passes, the only difference between it and a chaos run is which
proxy the transport is pointed at.
"""

from __future__ import annotations

from pathlib import Path

from core.state.types import TeamContext
from tests.harness.backends.base import stand_up
from tests.harness.investigator import PipelineInvestigator
from tests.harness.loader import load_scenario
from tests.harness.offline import TranscriptPlayer, load_transcript
from tests.harness.runner import SCENARIO_CLOCK, SCENARIO_ORG_ID, alert_for

CORPUS = Path(__file__).resolve().parents[3] / "tests" / "synthetic" / "kubernetes"


async def test_the_investigator_reaches_a_vendor_through_the_real_client_path() -> None:
    scenario = load_scenario(CORPUS / "001-oom-kill")
    assert scenario.transcript_path is not None

    stack = await stand_up(
        scenario.integrations,
        scenario.evidence,
        org_id=SCENARIO_ORG_ID,
        team_id=scenario.team_id,
        at=SCENARIO_CLOCK,
    )
    investigator = PipelineInvestigator(
        llm=TranscriptPlayer(load_transcript(scenario.transcript_path)),
        transport=stack.transport,
        org_id=SCENARIO_ORG_ID,
    )

    live = await investigator.investigate(
        alert_for(scenario),
        team=TeamContext(
            team_id=scenario.team_id, integrations=scenario.integrations, destinations=()
        ),
        run_id="live-1",
    )

    # The vendor boundary saw a request, which is only true if the whole client
    # path ran: capability, client, transport, proxy, injection rule.
    assert stack.boundary.calls
    observation = live.observation
    assert "kubernetes" in observation.evidence_sources
    assert observation.root_cause_category == scenario.answer.root_cause_category
    assert observation.trajectory


async def test_the_observation_of_a_live_run_carries_what_every_axis_reads() -> None:
    scenario = load_scenario(CORPUS / "001-oom-kill")
    assert scenario.transcript_path is not None

    stack = await stand_up(
        scenario.integrations,
        scenario.evidence,
        org_id=SCENARIO_ORG_ID,
        team_id=scenario.team_id,
        at=SCENARIO_CLOCK,
    )
    live = await PipelineInvestigator(
        llm=TranscriptPlayer(load_transcript(scenario.transcript_path)),
        transport=stack.transport,
        org_id=SCENARIO_ORG_ID,
    ).investigate(
        alert_for(scenario),
        team=TeamContext(
            team_id=scenario.team_id, integrations=scenario.integrations, destinations=()
        ),
    )

    observation = live.observation
    assert observation.answer_text
    assert observation.held_evidence_ids
    assert observation.iterations >= 1
    assert observation.duration_seconds > 0.0
    assert live.run_id
