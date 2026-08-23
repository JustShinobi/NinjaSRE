"""The gate meets the run: one per investigation, carrying that run's context.

The serving runner composed a loop with one hook — the incident-window guard —
so a write proposed inside an investigation reached the capability body, which
refused it. Safe, and indistinguishable from a product that does not know how to
act. This is about the other half existing.

Per investigation rather than per process, and that is the whole of why these
tests run two at once. The run context carries who asked and for which team; a
gate built once at boot would carry whichever run happened to build it, and the
second concurrent investigation would propose changes attributed to the first
person. During an incident that is not a cosmetic error — it is the audit trail
naming the wrong human.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from capabilities.registry import build_registry
from capabilities.registry.catalogue import Registry
from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.control_plane import ControlPlaneState
from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    StreamEvent,
    StreamEventKind,
    ToolCall,
)
from core.llm.usage import TokenCounts, UsageRecord
from gateway.http.remediation import compose_remediation
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.remediation.models import RemediationAction, StateSnapshot, SubTargetResult

pytestmark = pytest.mark.unit

ORG = "acme"
TEAM = "acme/payments"
SCALE = "scale_workload"


class _Plane:
    """A control plane that reads a replica count and records every change."""

    def __init__(self) -> None:
        self.changes: list[RemediationAction] = []

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        del action
        return ControlPlaneState(values={"replicas": 2}, sub_targets=("checkout",))

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> tuple[SubTargetResult, ...]:
        del desired, before
        self.changes.append(action)
        return (SubTargetResult(identifier="checkout", changed=True),)


@dataclass(slots=True)
class _ScriptedLLM:
    """Returns the scripted turns, and keeps every request it was handed."""

    turns: list[tuple[str, tuple[ToolCall, ...]]] = field(default_factory=list)
    requests: list[InvokeRequest] = field(default_factory=list)

    @property
    def provider_id(self) -> str:
        return "scripted"

    @property
    def model_id(self) -> str:
        return "scripted-1"

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        text, calls = self.turns.pop(0) if self.turns else ("Nothing further.", ())
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=text,
            tool_calls=calls,
            finish_reason=FinishReason.TOOL_CALLS if calls else FinishReason.STOP,
            usage=UsageRecord(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tokens=TokenCounts(input_tokens=100, output_tokens=20),
            ),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=result.finish_reason)


@pytest.fixture
def plane() -> Any:
    """Bind a control plane, so this deployment can carry a write."""
    bound = _Plane()
    previous = control_plane.bind(bound)
    yield bound
    control_plane.restore(previous)


def _scaling_llm() -> _ScriptedLLM:
    """Return a provider that proposes one scale and then concludes."""
    return _ScriptedLLM(
        turns=[
            (
                "",
                (
                    ToolCall(
                        id="call-1",
                        name=SCALE,
                        arguments={
                            "workload": "checkout",
                            "environment": "production",
                            "replicas": 4,
                        },
                    ),
                ),
            ),
            ("Checkout is under-provisioned; a scale is proposed.", ()),
        ]
    )


def _registry() -> Registry:
    """Return a catalogue holding exactly the one write these tests propose."""
    shipped = build_registry()
    found = shipped.tool(SCALE)
    assert found is not None
    return Registry(tools={SCALE: found})


async def _runner(
    store: FakePersistence, llm: _ScriptedLLM
) -> tuple[ReActInvestigationRunner, GatewayState]:
    """Return a runner composed the way the deployment's own roots compose one."""
    runner = ReActInvestigationRunner(llm=llm, registry=_registry())  # type: ignore[arg-type]
    state = GatewayState(gateway=store, tokens=TokenService(gateway=store), investigator=runner)
    desk = await compose_remediation(state, org_id=ORG)
    assert desk is not None, "the test deployment could not compose a remediation desk"
    return runner, state


def _everything_the_model_read(llm: _ScriptedLLM) -> str:
    """Return every message handed back to the model, text and tool results alike."""
    return " ".join(repr(message) for request in llm.requests for message in request.messages)


def _start(run_id: str, *, principal: str) -> InvestigationStart:
    return InvestigationStart(
        run_id=run_id,
        objective="checkout is saturating its replicas",
        team_node_id=TEAM,
        principal_id=principal,
        org_id=ORG,
        alert_source="alertmanager",
    )


async def _approvals(store: FakePersistence) -> list[Any]:
    async with store.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
        return list(await uow.approvals.list_pending(limit=50))


async def test_a_write_inside_an_investigation_becomes_a_stored_proposal(plane: _Plane) -> None:
    """The property the whole feature exists for, asserted on the store."""
    store = FakePersistence()
    runner, _ = await _runner(store, _scaling_llm())

    await runner.investigate(_start("run-1", principal="ana"))

    pending = await _approvals(store)
    assert len(pending) == 1, (
        f"the investigation proposed a write and {len(pending)} approvals were stored. "
        f"A write that reached no queue is one nobody can answer."
    )
    assert SCALE in pending[0].action


async def test_the_proposal_carries_the_plan_that_would_undo_it(plane: _Plane) -> None:
    store = FakePersistence()
    runner, _ = await _runner(store, _scaling_llm())

    await runner.investigate(_start("run-1", principal="ana"))

    pending = await _approvals(store)
    async with store.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
        plan = await uow.approvals.rollback_plan_for(pending[0].approval_id)
    assert plan is not None, (
        "the approval was stored with no rollback plan beside it. A reviewer with no "
        "undo in front of them is approving on the assumption that one exists."
    )
    assert plan.steps


async def test_the_proposal_names_the_person_who_started_the_run(plane: _Plane) -> None:
    store = FakePersistence()
    runner, _ = await _runner(store, _scaling_llm())

    await runner.investigate(_start("run-1", principal="ana"))

    pending = await _approvals(store)
    assert "ana" in str(pending[0].arguments) or "ana" in pending[0].summary


async def test_nothing_is_changed_while_the_deployment_only_proposes(plane: _Plane) -> None:
    store = FakePersistence()
    runner, _ = await _runner(store, _scaling_llm())

    await runner.investigate(_start("run-1", principal="ana"))

    assert plane.changes == [], (
        "a deployment that has configured no autonomy policy changed something. "
        "Silence resolves to proposing, and proposing performs nothing."
    )


async def test_the_model_is_told_a_person_has_to_decide(plane: _Plane) -> None:
    """The sentence the model reads, so it records the gap instead of retrying."""
    store = FakePersistence()
    llm = _scaling_llm()
    runner, _ = await _runner(store, llm)

    await runner.investigate(_start("run-1", principal="ana"))

    said = _everything_the_model_read(llm)
    assert "waiting on a human" in said, (
        "the model was not told the action is waiting on a person. Without that "
        "sentence it either retries the call or reports the change as made."
    )


async def test_the_refusal_says_the_policy_decided(plane: _Plane) -> None:
    store = FakePersistence()
    llm = _scaling_llm()
    runner, _ = await _runner(store, llm)

    await runner.investigate(_start("run-1", principal="ana"))

    said = _everything_the_model_read(llm)
    assert "propose" in said.lower(), (
        "the explanation handed back never names the posture that decided. 'Something "
        "is missing' and 'this deployment proposes rather than acts' are opposite facts."
    )


async def test_the_investigation_continues_after_the_proposal(plane: _Plane) -> None:
    store = FakePersistence()
    runner, _ = await _runner(store, _scaling_llm())

    summary = await runner.investigate(_start("run-1", principal="ana"))

    assert "under-provisioned" in summary, (
        "the run ended at the proposal instead of continuing. An agent that stopped "
        "because a mitigation needs a person threw away the diagnosis it had reached."
    )


async def test_two_concurrent_runs_do_not_share_a_requester(plane: _Plane) -> None:
    """A process-wide gate would attribute one person's proposal to the other."""
    store = FakePersistence()
    first, _ = await _runner(store, _scaling_llm())
    second, _ = await _runner(store, _scaling_llm())

    await asyncio.gather(
        first.investigate(_start("run-1", principal="ana")),
        second.investigate(_start("run-2", principal="bruno")),
    )

    pending = await _approvals(store)
    assert len(pending) == 2
    requesters = {change.arguments.get("proposed", {}).get("requester") for change in pending}
    assert requesters == {"ana", "bruno"}, (
        f"two concurrent investigations produced proposals attributed to {requesters}. "
        f"A gate shared between runs carries the context of whichever built it."
    )


async def test_two_concurrent_runs_do_not_share_a_run_identity(plane: _Plane) -> None:
    store = FakePersistence()
    first, _ = await _runner(store, _scaling_llm())
    second, _ = await _runner(store, _scaling_llm())

    await asyncio.gather(
        first.investigate(_start("run-1", principal="ana")),
        second.investigate(_start("run-2", principal="bruno")),
    )

    pending = await _approvals(store)
    runs = {change.arguments.get("proposed", {}).get("run_id") for change in pending}
    assert runs == {"run-1", "run-2"}, (
        f"the two proposals name {runs} as the runs that raised them. A proposal that "
        f"cannot be traced to its investigation is one nobody can review the evidence for."
    )


async def test_a_deployment_with_no_desk_proposes_nothing_and_still_investigates(
    plane: _Plane,
) -> None:
    """Composed nothing is a working deployment, exactly as it was before."""
    store = FakePersistence()
    runner = ReActInvestigationRunner(llm=_scaling_llm(), registry=_registry())  # type: ignore[arg-type]

    summary = await runner.investigate(_start("run-1", principal="ana"))

    assert summary
    assert await _approvals(store) == []
    assert plane.changes == []
