"""Replay, over the real route: model, tokens, cost when priced, and unpriced turns declared.

Today, against any real run, the replay comes back with no turns at all —
nothing was ever written. This is the contract for what it looks like once
recording is composed: a model and its tokens on every turn, a cost on the
ones a provider priced, and a count of the ones that were not — never a
fabricated zero standing in for "unknown".
"""

from __future__ import annotations

import pytest

from config.constants.runs import TRIGGER_ALERT
from platform.persistence.ports.run_trace_store import RunStatus
from platform.persistence.ports.transaction import TenantScope
from platform.runs.recorder import RecordedTurn, RunRecorder
from tests.contract.runs._deployment import ORG, TEAM, Deployment, bearer

pytestmark = pytest.mark.contract


async def _seed_run_with_turns(deployment: Deployment, *, run_id: str) -> None:
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    async with deployment.gateway.begin(scope) as uow:
        recorder = RunRecorder(store=uow.run_traces)
        await recorder.start_run(
            trigger=TRIGGER_ALERT, principal_id="alertmanager", team_node_id=TEAM, run_id=run_id
        )
        await recorder.record_turn(
            RecordedTurn(
                run_id=run_id,
                index=0,
                model="claude-opus-5",
                prompt_tokens=1_200,
                completion_tokens=340,
                cost=0.042,
            )
        )
        await recorder.record_turn(
            RecordedTurn(
                run_id=run_id,
                index=1,
                model="llama-self-hosted",
                prompt_tokens=500,
                completion_tokens=100,
                cost=None,
            )
        )
        await recorder.complete_run(run_id, status=RunStatus.COMPLETED, summary="done")


class TestReplayCarriesModelTokensAndCost:
    async def test_every_turn_names_a_model_and_its_tokens(self, deployment: Deployment) -> None:
        await _seed_run_with_turns(deployment, run_id="run-1")

        response = await deployment.client.get(
            "/v1/runs/run-1/replay", headers=bearer(deployment.operator_secret)
        )

        assert response.status_code == 200
        turns = response.json()["turns"]
        assert len(turns) == 2
        assert {turn["model"] for turn in turns} == {"claude-opus-5", "llama-self-hosted"}
        for turn in turns:
            assert turn["prompt_tokens"] > 0
            assert turn["completion_tokens"] > 0

    async def test_a_priced_turn_carries_its_cost(self, deployment: Deployment) -> None:
        await _seed_run_with_turns(deployment, run_id="run-1")

        response = await deployment.client.get(
            "/v1/runs/run-1/replay", headers=bearer(deployment.operator_secret)
        )

        priced = next(t for t in response.json()["turns"] if t["model"] == "claude-opus-5")
        assert priced["cost"] == pytest.approx(0.042)

    async def test_an_unpriced_turn_is_declared_rather_than_summed_as_zero(
        self, deployment: Deployment
    ) -> None:
        await _seed_run_with_turns(deployment, run_id="run-1")

        response = await deployment.client.get(
            "/v1/runs/run-1/replay", headers=bearer(deployment.operator_secret)
        )

        body = response.json()
        unpriced = next(t for t in body["turns"] if t["model"] == "llama-self-hosted")
        assert unpriced["cost"] is None
        assert body["total_cost"] == pytest.approx(0.042)
        assert body["unpriced_turns"] == 1
