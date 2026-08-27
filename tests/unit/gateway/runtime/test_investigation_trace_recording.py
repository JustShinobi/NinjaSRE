"""A real run, given somewhere to write, leaves what it did in the store.

``ReActInvestigationRunner`` composes exactly one runtime per investigation
(see ``test_react_investigation_runner.py``). This file proves the other
half: once ``attach_recording`` has given it a gateway to write through, a
run that made N capability calls leaves N turn records and N call records —
read back from the store, after the run has finished, not asserted against
anything the process still holds in memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from capabilities.registry.catalogue import Registry
from core.llm.types import FinishReason, InvokeResult, ToolCall
from core.llm.usage import TokenCounts, UsageRecord
from gateway.http.services import InvestigationStart
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.runs.stream import RunEventBroker
from tests.unit.gateway.runtime.conftest import PROVIDER_ID, ScriptedLLM, fixture_tool, text_turn

pytestmark = pytest.mark.unit

ORG = "acme"


def _registry(*names: str) -> Registry:
    return Registry(tools={name: fixture_tool(name) for name in names})


def _request(run_id: str = "run-1") -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="disk on host-1 is at 98%",
        team_node_id="platform",
        principal_id="operator-1",
        alert_source="prometheus",
        org_id=ORG,
    )


def _one_tool_call_then_conclude() -> ScriptedLLM:
    """Return a scripted model that calls one capability, then answers in prose."""
    calling = InvokeResult(
        provider_id=PROVIDER_ID,
        model_id="scripted-1",
        tool_calls=(ToolCall(id="call-1", name="fixture_probe", arguments={}),),
        finish_reason=FinishReason.TOOL_CALLS,
        usage=UsageRecord(
            provider_id=PROVIDER_ID,
            model_id="scripted-1",
            tokens=TokenCounts(input_tokens=100, output_tokens=20),
            cost_usd=0.001,
        ),
    )
    return ScriptedLLM([calling, text_turn("the disk on host-1 is full")])


@pytest.fixture
async def gateway() -> AsyncIterator[PersistenceGateway]:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, name="Acme")
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    return TenantScope(org_id=ORG, team_node_id="platform")


class TestARunWithSomewhereToWriteRecordsWhatItDid:
    async def test_one_iteration_with_one_call_leaves_one_turn_and_one_call_record(
        self, gateway: PersistenceGateway, scope: TenantScope
    ) -> None:
        runner = ReActInvestigationRunner(
            llm=_one_tool_call_then_conclude(), registry=_registry("fixture_probe")
        )
        runner.attach_recording(
            gateway=gateway, guardrails=GuardrailEngine(), broker=RunEventBroker()
        )

        async with gateway.begin(scope) as uow:
            from platform.runs.recorder import RunRecorder

            await RunRecorder(store=uow.run_traces).start_run(
                trigger="alert", principal_id="operator-1", team_node_id="platform", run_id="run-1"
            )

        await runner.investigate(_request("run-1"))

        async with gateway.begin(scope) as uow:
            turns = await uow.run_traces.turns_for_run("run-1")
            calls = await uow.run_traces.tool_calls_for_run("run-1")

        # Two iterations happened: the call, then the concluding turn with no calls.
        assert len(turns) == 2
        assert len(calls) == 1
        assert calls[0].tool_name == "fixture_probe"

    async def test_without_attach_recording_nothing_is_written_and_the_run_still_completes(
        self, gateway: PersistenceGateway, scope: TenantScope
    ) -> None:
        """The composed-nothing case: today's default, and still a valid one."""
        runner = ReActInvestigationRunner(
            llm=_one_tool_call_then_conclude(), registry=_registry("fixture_probe")
        )

        async with gateway.begin(scope) as uow:
            from platform.runs.recorder import RunRecorder

            await RunRecorder(store=uow.run_traces).start_run(
                trigger="alert", principal_id="operator-1", team_node_id="platform", run_id="run-1"
            )

        summary = await runner.investigate(_request("run-1"))

        async with gateway.begin(scope) as uow:
            turns = await uow.run_traces.turns_for_run("run-1")

        assert turns == ()
        assert "disk on host-1 is full" in summary
