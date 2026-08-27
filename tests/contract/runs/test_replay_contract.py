"""Replay, over the real route: model, tokens, cost when priced, and unpriced turns declared.

Today, against any real run, the replay comes back with no turns at all —
nothing was ever written. This is the contract for what it looks like once
recording is composed: a model and its tokens on every turn, a cost on the
ones a provider priced, and a count of the ones that were not — never a
fabricated zero standing in for "unknown".
"""

from __future__ import annotations

import json

import pytest

from config.constants.runs import (
    MAX_REPLAY_RESULT_BYTES,
    TRIGGER_ALERT,
    TURN_PAYLOAD_STAGE,
)
from core.state.types import StageName
from platform.persistence.ports.run_trace_store import RunStatus
from platform.persistence.ports.transaction import TenantScope
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder
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


async def _seed_run_with_a_call(
    deployment: Deployment, *, run_id: str, result: dict[str, object]
) -> None:
    """Record one run whose single call returned ``result``."""
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    async with deployment.gateway.begin(scope) as uow:
        recorder = RunRecorder(store=uow.run_traces)
        await recorder.start_run(
            trigger=TRIGGER_ALERT, principal_id="alertmanager", team_node_id=TEAM, run_id=run_id
        )
        turn = await recorder.record_turn(RecordedTurn(run_id=run_id, index=0, model="m"))
        await recorder.record_call(
            RecordedCall(
                run_id=run_id,
                turn_id=turn.turn_id,
                name="proxmox_guest_tasks",
                arguments={"kind": "lxc", "vmid": 122},
                result=result,
                duration_ms=31,
            )
        )
        await recorder.complete_run(run_id, status=RunStatus.COMPLETED, summary="done")


class TestReplayCarriesWhatEachCallReturned:
    async def test_a_call_carries_the_result_the_trace_recorded(
        self, deployment: Deployment
    ) -> None:
        # Without this the trace holds what the world said and the API throws
        # it away, so nothing downstream can state what a run actually found.
        await _seed_run_with_a_call(
            deployment,
            run_id="run-1",
            result={"tasks": [{"type": "vzshutdown", "user": "root@pam"}]},
        )

        response = await deployment.client.get(
            "/v1/runs/run-1/replay", headers=bearer(deployment.operator_secret)
        )

        call = response.json()["turns"][0]["calls"][0]
        assert call["result"] == {"tasks": [{"type": "vzshutdown", "user": "root@pam"}]}
        assert call["result_truncated"] is False

    async def test_a_result_the_trace_holds_whole_still_arrives_bounded(
        self, deployment: Deployment
    ) -> None:
        # 36 KB: comfortably inside the recorder's per-row ceiling, so the trace
        # holds all of it, and well outside the reading bound. A replay holds
        # every call of a run at once, so it serves the tighter projection —
        # the statement survives, the bulk does not, and it says so.
        await _seed_run_with_a_call(
            deployment,
            run_id="run-2",
            result={"statement": "the probe failed", "lines": ["x" * 900 for _ in range(40)]},
        )

        response = await deployment.client.get(
            "/v1/runs/run-2/replay", headers=bearer(deployment.operator_secret)
        )

        call = response.json()["turns"][0]["calls"][0]
        assert call["result_truncated"] is True
        assert len(json.dumps(call["result"]).encode("utf-8")) <= MAX_REPLAY_RESULT_BYTES
        assert call["result"]["statement"] == "the probe failed"

    async def test_a_result_the_recorder_dropped_is_not_served_as_an_empty_one(
        self, deployment: Deployment
    ) -> None:
        # Past the recorder's own ceiling the whole result field is shed, so the
        # trace has nothing left of it. Serving that as ``{}`` with nothing said
        # would read as "this capability returned nothing", which is the one
        # thing it did not do.
        await _seed_run_with_a_call(
            deployment,
            run_id="run-3",
            result={"lines": ["x" * 900 for _ in range(400)]},
        )

        response = await deployment.client.get(
            "/v1/runs/run-3/replay", headers=bearer(deployment.operator_secret)
        )

        call = response.json()["turns"][0]["calls"][0]
        assert call["result"] == {}
        assert call["result_truncated"] is True


class TestReplayGroupsTheRunByStage:
    """The six stages, over the route, with the one that turned holding its turns.

    A run's trace used to serve a flat list of loop iterations, which is an
    accurate account of the fourth stage and silence about the other five —
    including the two that each cost a model call and produce no turn at all.
    """

    async def _seed_staged_run(self, deployment: Deployment, *, run_id: str) -> None:
        scope = TenantScope(org_id=ORG, team_node_id=TEAM)
        async with deployment.gateway.begin(scope) as uow:
            recorder = RunRecorder(store=uow.run_traces)
            await recorder.start_run(
                trigger=TRIGGER_ALERT,
                principal_id="alertmanager",
                team_node_id=TEAM,
                run_id=run_id,
            )
            await recorder.record_stage(
                run_id,
                stage=StageName.INTAKE.value,
                finding="A new incident, not a repeat of one already open",
                duration_ms=1_400,
                prompt_tokens=800,
                completion_tokens=90,
                llm_calls=1,
            )
            await recorder.record_turn(
                RecordedTurn(
                    run_id=run_id,
                    index=0,
                    model="claude-opus-5",
                    prompt_tokens=1_200,
                    completion_tokens=340,
                    cost=0.042,
                    payload={TURN_PAYLOAD_STAGE: StageName.GATHER_EVIDENCE.value},
                )
            )
            await recorder.record_stage(
                run_id,
                stage=StageName.GATHER_EVIDENCE.value,
                finding="11 observations gathered",
                duration_ms=28_000,
                prompt_tokens=1_200,
                completion_tokens=340,
                llm_calls=1,
            )
            await recorder.complete_run(run_id, status=RunStatus.COMPLETED, summary="done")

    async def test_the_stages_arrive_in_the_order_the_pipeline_runs_them(
        self, deployment: Deployment
    ) -> None:
        await self._seed_staged_run(deployment, run_id="run-staged")

        response = await deployment.client.get(
            "/v1/runs/run-staged/replay", headers=bearer(deployment.operator_secret)
        )

        assert response.status_code == 200
        stages = response.json()["stages"]
        assert [stage["stage"] for stage in stages] == [
            StageName.INTAKE.value,
            StageName.GATHER_EVIDENCE.value,
        ]
        assert stages[0]["finding"] == "A new incident, not a repeat of one already open"
        assert stages[0]["duration_ms"] == 1_400

    async def test_a_stage_that_produced_no_turn_says_so_rather_than_borrowing_one(
        self, deployment: Deployment
    ) -> None:
        await self._seed_staged_run(deployment, run_id="run-staged")

        response = await deployment.client.get(
            "/v1/runs/run-staged/replay", headers=bearer(deployment.operator_secret)
        )

        stages = {stage["stage"]: stage for stage in response.json()["stages"]}
        assert stages[StageName.INTAKE.value]["turns"] == []
        assert stages[StageName.INTAKE.value]["llm_calls"] == 1
        assert [turn["index"] for turn in stages[StageName.GATHER_EVIDENCE.value]["turns"]] == [0]

    async def test_the_token_total_counts_the_stage_that_left_no_turn(
        self, deployment: Deployment
    ) -> None:
        await self._seed_staged_run(deployment, run_id="run-staged")

        body = (
            await deployment.client.get(
                "/v1/runs/run-staged/replay", headers=bearer(deployment.operator_secret)
            )
        ).json()

        assert body["turn_tokens"] == 1_540
        assert body["total_tokens"] == 2_430
