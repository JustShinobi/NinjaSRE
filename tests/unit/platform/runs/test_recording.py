"""The adapter that turns the canonical loop's own vocabulary into the recorder's.

``RunTraceRecordingHook`` is what the loop's ``on_turn_end`` point calls once
a turn is over. It does not invent anything the loop did not already produce:
a turn's usage, a turn's calls, and the evidence those calls produced are all
read off ``Turn`` and ``Session`` exactly as the loop built them.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from conftest import PRINCIPAL, TEAM

from config.constants.runs import TRIGGER_ALERT
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import HookPoint
from core.agent.session import EvidenceEntry, Session
from core.agent.turn import ToolExecution, Turn
from core.capability.metadata import EvidenceType
from core.capability.result import CapabilityErrorClass
from core.capability.telemetry import InvocationOutcome
from core.llm.usage import TokenCounts, UsageRecord
from platform.persistence.ports import PersistenceGateway, TenantScope, ToolCallStatus
from platform.runs.recorder import RunRecorder
from platform.runs.recording import RunTraceRecordingHook
from platform.runs.replay import replay_trace

pytestmark = pytest.mark.unit


async def _seed_run(
    gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime], run_id: str
) -> None:
    async with gateway.begin(scope) as uow:
        await RunRecorder(store=uow.run_traces, clock=clock).start_run(
            trigger=TRIGGER_ALERT, principal_id=PRINCIPAL, team_node_id=TEAM, run_id=run_id
        )


class TestTheAdapterWritesATurn:
    async def test_a_turn_is_translated_preserving_model_tokens_duration_and_capabilities(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        session = Session(id="run-1", objective="disk is full", system_prompt="x")
        turn = Turn(
            index=0,
            offered_capabilities=("kubernetes.list_pods", "loki.query"),
            provider_id="anthropic",
            model_id="claude-opus-5",
            rationale="the alert names a Kubernetes workload",
            duration_seconds=1.8,
            usage=UsageRecord(
                provider_id="anthropic",
                model_id="claude-opus-5",
                tokens=TokenCounts(input_tokens=1_200, output_tokens=340),
                cost_usd=0.042,
            ),
        )

        await hook.on_turn_end(session, turn)

        async with gateway.begin(scope) as uow:
            stored = await uow.run_traces.turns_for_run("run-1")

        assert len(stored) == 1
        assert stored[0].usage["model"] == "claude-opus-5"
        assert stored[0].usage["prompt_tokens"] == 1_200
        assert stored[0].usage["completion_tokens"] == 340
        assert stored[0].usage["cost"] == pytest.approx(0.042)
        assert stored[0].usage["duration_ms"] == 1_800
        assert stored[0].payload["offered_capabilities"] == [
            "kubernetes.list_pods",
            "loki.query",
        ]
        assert stored[0].payload["selection_rationale"] == "the alert names a Kubernetes workload"

    async def test_one_iteration_produces_exactly_one_turn_record(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        session = Session(id="run-1", objective="x", system_prompt="x")

        await hook.on_turn_end(session, Turn(index=0))
        await hook.on_turn_end(session, Turn(index=1))

        async with gateway.begin(scope) as uow:
            stored = await uow.run_traces.turns_for_run("run-1")

        assert len(stored) == 2
        assert sorted(turn.index for turn in stored) == [0, 1]

    async def test_a_sub_agents_turn_is_not_absorbed_into_the_parents_trace(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        """The parent's record must not gain the child's turns (edge case: sub-agents)."""
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        child_session = Session(
            id="run-1/disk-specialist-1",
            objective="check disk",
            system_prompt="x",
            parent_id="run-1",
            subagent="disk-specialist",
        )

        await hook.on_turn_end(child_session, Turn(index=0))

        async with gateway.begin(scope) as uow:
            stored = await uow.run_traces.turns_for_run("run-1")

        assert stored == ()


class TestUnpricedCostIsNeverFabricated:
    async def test_a_turn_with_no_published_price_is_recorded_without_cost(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        session = Session(id="run-1", objective="x", system_prompt="x")
        turn = Turn(
            index=0,
            provider_id="ollama",
            model_id="llama-self-hosted",
            usage=UsageRecord(
                provider_id="ollama",
                model_id="llama-self-hosted",
                tokens=TokenCounts(input_tokens=500, output_tokens=100),
                cost_usd=None,
            ),
        )

        await hook.on_turn_end(session, turn)

        async with gateway.begin(scope) as uow:
            trace = await uow.run_traces.replay("run-1")
        replayed = replay_trace(trace)

        assert len(replayed.turns) == 1
        assert replayed.turns[0].cost is None

    async def test_the_runs_total_never_counts_an_unpriced_turn_as_zero(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        session = Session(id="run-1", objective="x", system_prompt="x")
        priced = Turn(
            index=0,
            provider_id="anthropic",
            model_id="claude-opus-5",
            usage=UsageRecord(
                provider_id="anthropic",
                model_id="claude-opus-5",
                tokens=TokenCounts(input_tokens=100, output_tokens=20),
                cost_usd=0.01,
            ),
        )
        unpriced = Turn(
            index=1,
            provider_id="ollama",
            model_id="llama-self-hosted",
            usage=UsageRecord(
                provider_id="ollama",
                model_id="llama-self-hosted",
                tokens=TokenCounts(input_tokens=500, output_tokens=100),
                cost_usd=None,
            ),
        )

        await hook.on_turn_end(session, priced)
        await hook.on_turn_end(session, unpriced)

        async with gateway.begin(scope) as uow:
            trace = await uow.run_traces.replay("run-1")
        replayed = replay_trace(trace)

        assert replayed.total_cost == pytest.approx(0.01)
        assert replayed.unpriced_turn_count == 1


class TestCallsAreRecordedByOutcome:
    async def test_a_failed_call_and_a_denied_call_are_both_recorded_not_omitted(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        session = Session(id="run-1", objective="x", system_prompt="x")
        turn = Turn(
            index=0,
            executions=(
                ToolExecution(
                    call_id="c1",
                    capability="kubernetes.list_pods",
                    outcome=InvocationOutcome.FAILURE,
                    error_class=CapabilityErrorClass.TIMEOUT,
                    error_message="the API server timed out",
                ),
                ToolExecution(
                    call_id="c2",
                    capability="proxmox.snapshot_delete",
                    outcome=InvocationOutcome.FAILURE,
                    denied=True,
                    error_class=CapabilityErrorClass.APPROVAL_REQUIRED,
                    error_message="deleting a snapshot needs approval",
                ),
            ),
        )

        await hook.on_turn_end(session, turn)

        async with gateway.begin(scope) as uow:
            calls = await uow.run_traces.tool_calls_for_run("run-1")

        by_name = {call.tool_name: call for call in calls}
        assert len(calls) == 2
        assert by_name["kubernetes.list_pods"].status is ToolCallStatus.FAILED
        assert by_name["kubernetes.list_pods"].error == "the API server timed out"
        assert by_name["proxmox.snapshot_delete"].status is ToolCallStatus.DENIED
        assert by_name["proxmox.snapshot_delete"].error == "deleting a snapshot needs approval"

    async def test_a_calls_evidence_is_recorded_and_linked_back_to_it(
        self, gateway: PersistenceGateway, scope: TenantScope, clock: Callable[[], datetime]
    ) -> None:
        await _seed_run(gateway, scope, clock, "run-1")
        hook = RunTraceRecordingHook(gateway=gateway, scope=scope, run_id="run-1")
        session = Session(id="run-1", objective="x", system_prompt="x")
        session.record_evidence(
            EvidenceEntry(
                id="",
                capability="kubernetes.list_pods",
                summary="12 pods running in payments",
                evidence_type=EvidenceType.EVENT,
                source="kubernetes",
                content='{"pods": 12}',
                call_id="c1",
                iteration=0,
            )
        )
        turn = Turn(
            index=0,
            executions=(
                ToolExecution(
                    call_id="c1",
                    capability="kubernetes.list_pods",
                    outcome=InvocationOutcome.SUCCESS,
                    evidence_ids=(session.evidence[0].id,),
                ),
            ),
        )

        await hook.on_turn_end(session, turn)

        async with gateway.begin(scope) as uow:
            calls = await uow.run_traces.tool_calls_for_run("run-1")
            evidence = await uow.run_traces.evidence_for_run("run-1")

        assert len(evidence) == 1
        assert evidence[0].evidence_id == session.evidence[0].id
        assert evidence[0].source == "kubernetes"
        assert calls[0].evidence_ids == (session.evidence[0].id,)


class TestAWriteFailureDoesNotInterruptTheInvestigation:
    async def test_the_failure_is_swallowed_and_recorded_as_a_hook_failure(self) -> None:
        class _UnreachableGateway:
            def begin(self, scope: TenantScope) -> object:
                raise RuntimeError("the store is unreachable")

        hook = RunTraceRecordingHook(
            gateway=_UnreachableGateway(),  # type: ignore[arg-type]
            scope=TenantScope(org_id="acme"),
            run_id="run-1",
        )
        registry = HookRegistry()
        registry.register(HookPoint.ON_TURN_END, hook.on_turn_end, name="run_trace_recorder")
        session = Session(id="run-1", objective="x", system_prompt="x")

        failures = await registry.run_turn_end(session, Turn(index=0))

        assert len(failures) == 1
        assert failures[0].hook == "run_trace_recorder"
        assert "unreachable" in failures[0].error
