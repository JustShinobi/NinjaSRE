"""A served investigation runs the six stages, not a loop standing in for them.

The `/agent` screen has always said an investigation runs six stages, in order,
each consulting something named. Until this file existed a served run ran none
of them: it ran a flat loop of numbered turns, and the six-stage pipeline was
composed only by the corpus harness. A screen describing a shape the deployment
does not have is the same defect as a panel naming a model no call reaches.

So what is asserted here is not "the pipeline can be built" — the pipeline's own
tests prove that. It is that the *serving* path builds it, that everything the
serving path already guaranteed still holds through it (the recorder, the live
registry, the question desk, the run-scoped sources, the two outcome contracts),
and that the two model calls the stages add are the only ones they add.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from capabilities.registry.catalogue import Registry
from config.constants.estate import (
    SUBJECT_CONTEXT_RESOURCE_KIND,
    SUBJECT_CONTEXT_RESOURCE_NAME,
)
from config.constants.investigation import CONTEXT_ALERT_SOURCE, CONTEXT_PLAN_RATIONALE
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunResult, RunStatus
from core.agent.session import Session
from core.llm.types import FinishReason, InvokeRequest, InvokeResult, ToolCall
from core.llm.usage import TokenCounts, UsageRecord
from gateway.http.services import InvestigationStart
from gateway.runtime.investigator import InvestigationDidNotComplete, ReActInvestigationRunner
from platform.guardrails.engine import GuardrailEngine
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.runs.recorder import RunRecorder
from platform.runs.stream import RunEventBroker
from tests.unit.gateway.runtime.conftest import (
    PROVIDER_ID,
    ScriptedLLM,
    failed_turn,
    fixture_tool,
    text_turn,
)

pytestmark = pytest.mark.unit

ORG = "acme"

#: What intake's classification call answers when a test wants the run to go on.
AN_INCIDENT: Mapping[str, Any] = {
    "is_incident": True,
    "confidence": 0.9,
    "reason": "a disk filling up is a production problem",
    "alert_name": "DiskAlmostFull",
    "severity": "critical",
    "summary": "the disk on host-1 is at 98%",
    "components": ["host-1"],
    "error_text": "disk usage 98%",
}

#: And what it answers when the run should stop before the loop is ever driven.
NOT_AN_INCIDENT: Mapping[str, Any] = {**AN_INCIDENT, "is_incident": False, "confidence": 0.95}


def _structured(payload: Mapping[str, Any]) -> InvokeResult:
    """Return the shape a provider hands back for a structured-output call."""
    return InvokeResult(
        provider_id=PROVIDER_ID,
        model_id="scripted-1",
        finish_reason=FinishReason.STOP,
        structured=dict(payload),
        usage=UsageRecord(
            provider_id=PROVIDER_ID,
            model_id="scripted-1",
            tokens=TokenCounts(input_tokens=40, output_tokens=10),
        ),
    )


def _registry(*names: str) -> Registry:
    return Registry(tools={name: fixture_tool(name) for name in names})


def _request(run_id: str = "run-1", **overrides: Any) -> InvestigationStart:
    fields: dict[str, Any] = {
        "run_id": run_id,
        "objective": "disk on host-1 is at 98%",
        "team_node_id": "platform",
        "principal_id": "operator-1",
        "alert_source": "prometheus",
        "org_id": ORG,
    }
    fields.update(overrides)
    return InvestigationStart(**fields)


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


async def _reserve(gateway: PersistenceGateway, scope: TenantScope, run_id: str) -> None:
    """Reserve the run's identity, the way ``start_investigation`` does."""
    async with gateway.begin(scope) as uow:
        await RunRecorder(store=uow.run_traces).start_run(
            trigger="alert",
            principal_id="operator-1",
            team_node_id=scope.team_node_id or "platform",
            run_id=run_id,
        )


class TestTheStagesAreWhatRuns:
    async def test_intake_classifies_before_the_loop_is_driven(self) -> None:
        """Intake's call comes first, and the loop only sees what it let through."""
        llm = ScriptedLLM([text_turn("the disk on host-1 is full")])
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))

        await runner.investigate(_request())

        assert llm.structured_requests, "intake made no classification call"
        first = llm.structured_requests[0]
        assert "98%" in first.messages[0].text

    async def test_a_noise_verdict_ends_the_run_without_driving_the_loop(self) -> None:
        """The leverage intake exists for: the loop is never built a transcript.

        A greeting in a thread cost a whole investigation before the stages
        served a request. Here the classification call is the only model call
        the run makes, and what comes back is the reason rather than an answer
        to a question nobody asked.
        """
        llm = ScriptedLLM([text_turn("this should never be reached")])
        llm.structured = [_structured(NOT_AN_INCIDENT)]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))

        summary = await runner.investigate(_request())

        assert llm.requests == [], "the loop was driven on an input intake rejected"
        assert "not" in summary.lower() or "noise" in summary.lower()

    async def test_the_two_stage_calls_are_the_only_ones_the_stages_add(self) -> None:
        """Intake's classification and diagnosis's structuring, and nothing more.

        The cost of serving the stages was accepted as exactly two calls. A
        third would be a per-investigation cost nobody agreed to, and it is the
        kind of thing a refactor adds without anybody noticing.
        """
        llm = ScriptedLLM([text_turn("the disk on host-1 is full")])
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))

        await runner.investigate(_request())

        assert len(llm.structured_requests) == 2

    async def test_the_plan_the_stage_wrote_reaches_the_loop(self) -> None:
        """Evidence planning is one of the six, and a plan nothing reads is not one.

        The shortlist travels in the run's context, which is where the loop
        turns it into a stated turn. Before the stages served a request the
        loop was handed no plan at all, so the stage that writes one could not
        have been shown to matter.
        """
        llm = ScriptedLLM([text_turn("the disk on host-1 is full")])
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))

        await runner.investigate(_request())

        stated = "\n".join(message.text for message in llm.requests[0].messages)
        assert CONTEXT_PLAN_RATIONALE in stated


class TestWhatServingAlreadyGuaranteedStillHolds:
    async def test_what_the_deployment_established_about_the_subject_still_reaches_the_loop(
        self,
    ) -> None:
        """The subject brief is the correction a live run was diagnosed wrong without.

        A Redis alert resolved to Proxmox container 122 on pve01 was diagnosed
        as container 152 on pve02 because the loop was told the objective in
        prose and left to infer the rest. The stage that drives the loop builds
        its own request, so this is the assertion that the deployment's own
        context is not dropped on the way through it.
        """
        llm = ScriptedLLM([text_turn("the disk on host-1 is full")])
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))

        await runner.investigate(
            _request(
                context={
                    SUBJECT_CONTEXT_RESOURCE_NAME: "pve01",
                    SUBJECT_CONTEXT_RESOURCE_KIND: "node",
                }
            )
        )

        stated = "\n".join(message.text for message in llm.requests[0].messages)
        assert "pve01" in stated
        assert CONTEXT_ALERT_SOURCE in stated, "the stage's own context was dropped instead"

    async def test_the_run_trace_recorder_still_writes_a_turn_and_a_call(
        self, gateway: PersistenceGateway, scope: TenantScope
    ) -> None:
        """One recorder per investigation, still registered on the loop's hooks.

        The stages own the runtime now, and the recorder is a hook on the loop
        rather than on the pipeline — so this is the assertion that composing
        the pipeline did not move the loop out from under it.
        """
        calling = InvokeResult(
            provider_id=PROVIDER_ID,
            model_id="scripted-1",
            tool_calls=(ToolCall(id="call-1", name="fixture_probe", arguments={}),),
            finish_reason=FinishReason.TOOL_CALLS,
            usage=UsageRecord(
                provider_id=PROVIDER_ID,
                model_id="scripted-1",
                tokens=TokenCounts(input_tokens=100, output_tokens=20),
            ),
        )
        llm = ScriptedLLM([calling, text_turn("the disk on host-1 is full")])
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))
        runner.attach_recording(
            gateway=gateway, guardrails=GuardrailEngine(), broker=RunEventBroker()
        )
        await _reserve(gateway, scope, "run-1")

        await runner.investigate(_request("run-1"))

        async with gateway.begin(scope) as uow:
            turns = await uow.run_traces.turns_for_run("run-1")
            calls = await uow.run_traces.tool_calls_for_run("run-1")

        assert len(turns) == 2
        assert [call.tool_name for call in calls] == ["fixture_probe"]

    async def test_the_run_is_steerable_while_the_stages_drive_it(self) -> None:
        """The live registry holds the loop the gather stage is running.

        An operator cancels a run by its id while it is going, and what has to
        be there is the loop instance — put in the registry before the pipeline
        is driven, not after it returns.
        """
        seen: list[ReActLoop] = []

        def _turn(request: InvokeRequest) -> InvokeResult:
            seen.append(runner._live["run-1"].loop)  # noqa: SLF001 — the registry is the subject
            return text_turn("the disk on host-1 is full")

        llm = ScriptedLLM(_turn)
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))

        await runner.investigate(_request("run-1"))

        assert seen, "the loop never ran"
        assert all(isinstance(loop, ReActLoop) for loop in seen)

    async def test_a_team_that_can_execute_nothing_still_ends_before_any_model_call(self) -> None:
        """The cheapest sentence must not cost the run's only call.

        Unchanged by the stages, and asserted here because the stages give the
        same answer a second way — a run that reached intake first would have
        spent a classification call to arrive at it.
        """
        llm = ScriptedLLM([text_turn("x")])
        llm.structured = [_structured(AN_INCIDENT)]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry())

        summary = await runner.investigate(_request())

        assert llm.requests == []
        assert llm.structured_requests == []
        assert "integration" in summary.lower()

    async def test_a_failed_run_raises_and_names_what_the_loop_said_went_wrong(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_drive`` records a run failed only on a raise, and the reason is read."""

        class _FailingRuntime:
            is_canonical = True
            name = "failing-double"

            async def run(self, request: object) -> RunResult:
                return RunResult(
                    session=Session(id="run-1", objective="x"),
                    status=RunStatus.FAILED,
                    failure="no evidence at all",
                )

            async def cancel(self, session_id: str) -> None: ...

        llm = ScriptedLLM([text_turn("x")])
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))
        monkeypatch.setattr(
            ReActInvestigationRunner, "_build_runtime", lambda *_a, **_k: _FailingRuntime()
        )

        with pytest.raises(InvestigationDidNotComplete, match="no evidence at all"):
            await runner.investigate(_request())

    async def test_a_partial_run_is_returned_degraded_rather_than_raised(self) -> None:
        """A completion on less evidence than was asked for, named by its own word."""
        llm = ScriptedLLM([failed_turn()], repeat_last=True)
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))

        summary = await runner.investigate(_request())

        assert isinstance(summary, str)
        assert "degraded" in summary.lower()

    async def test_the_summary_is_still_the_answer_the_agent_wrote(self) -> None:
        """What a caller records as the run's report does not change shape here.

        ``gateway.http.orchestration._drive`` pulls the run's headline out of
        this string and stores the rest as the report body. Returning the
        diagnosis stage's structured account instead would rewrite every
        report a deployment has, which is a separate decision from running the
        stages.
        """
        llm = ScriptedLLM([text_turn("the disk on host-1 is full")])
        llm.structured = [_structured(AN_INCIDENT), _structured({})]
        runner = ReActInvestigationRunner(llm=llm, registry=_registry("fixture_probe"))

        summary = await runner.investigate(_request())

        assert summary == "the disk on host-1 is full"
