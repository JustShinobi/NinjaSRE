"""One alert, end to end: narrowed catalogue, proposal, approval, change, record.

The corpus does not reach this path. Its harness builds its own loop and hands
it its own catalogue, so a scenario there measures the agent's reasoning and
never touches the composition a route-triggered investigation actually runs on:
the desk, the gate bound to the run, the narrowing by what the team connected,
and the second entrance an approval comes back through. That gap is why this
file exists beside the corpus rather than in it.

The story is one incident, told once:

1. A team has connected one metrics system and not a log store. The
   investigation is offered the capabilities of the first and not of the second,
   and the configuration is read from the tree rather than declared to the
   runner — the same list a catalogue screen counts from.
2. The agent concludes the workload is under-provisioned and asks to scale it.
   The gate turns that into a stored approval with the undo beside it, and the
   run continues and finishes.
3. Nothing has changed. The workload holds the replica count it started with,
   the outcome ledger is empty, and the approval is pending — the deployment
   configured no posture, so silence resolves to proposing.
4. A person with the right to review approves, through the route a console
   button calls. Only now does the workload move, and what happened is
   recorded: not autonomous, with the plan, and with the approval named in the
   audit trail.

The target is a workload this deployment owns, never anything in the estate,
and the control plane here is a double: nothing outside this process is
reached, read or changed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

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
from gateway.http.app import create_app
from gateway.http.remediation import compose_remediation
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from gateway.runtime.investigator import ReActInvestigationRunner
from platform.config_service.service import ConfigService
from platform.guardrails.engine import GuardrailEngine
from platform.identity.audit.recorder import AuditRecorder
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.remediation.execution import ExecutionEnvironment
from platform.remediation.models import RemediationAction, StateSnapshot, SubTargetResult
from platform.runs.stream import RunEventBroker
from tests.unit.gateway.http.conftest import ORG, issue_token

pytestmark = pytest.mark.synthetic

TEAM = "payments"
WORKLOAD = "checkout"
ENVIRONMENT = "staging"
STARTING_REPLICAS = 2
PROPOSED_REPLICAS = 4

SCALE = "scale_workload"
CONNECTED_READ = "prometheus_metric_statistics"
UNCONNECTED_READ = "loki_sample_logs"

#: Where a sandbox would reach the credential proxy. Nothing here sends a
#: packet; the policy type refuses to describe a sandbox with nowhere to
#: authenticate through, so it has to be an address.
PROXY = "http://127.0.0.1:8787"


class _Workload:
    """The one workload this deployment owns, and every read and write of it.

    A double, and the reason it holds a number rather than answering a constant
    is the whole of step three: "nothing was executed before the approval" is
    only worth asserting against something that *could* have moved.
    """

    def __init__(self) -> None:
        self.replicas = STARTING_REPLICAS
        self.changes: list[RemediationAction] = []

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        del action
        return ControlPlaneState(values={"replicas": self.replicas}, sub_targets=(WORKLOAD,))

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> tuple[SubTargetResult, ...]:
        del before
        self.changes.append(action)
        wanted = desired.get("replicas")
        if isinstance(wanted, int):
            self.replicas = wanted
        return (SubTargetResult(identifier=WORKLOAD, changed=True),)


@dataclass(frozen=True, slots=True)
class _NoIsolation:
    """Stands in for the host's own sandbox, and only for it.

    Everything else on this path is the real thing. What is replaced is the one
    collaborator that reaches the machine the suite runs on: provisioning a
    confined subprocess and probing the kernel for namespaces is a property of
    this host rather than of the composition under test.
    """

    @asynccontextmanager
    async def running(self, action: Any) -> AsyncIterator[ExecutionEnvironment]:
        """Yield an environment naming no sandbox, and provision nothing."""
        del action
        yield ExecutionEnvironment(sandbox_id="scenario", profile="none")


@dataclass(slots=True)
class _Agent:
    """The provider, scripted for this incident and keeping what it was offered."""

    requests: list[InvokeRequest] = field(default_factory=list)
    turns: int = 0

    @property
    def provider_id(self) -> str:
        return "scenario"

    @property
    def model_id(self) -> str:
        return "scenario-1"

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        self.requests.append(request)
        self.turns += 1
        if self.turns == 1:
            return self._result(
                "",
                (
                    ToolCall(
                        id="call-1",
                        name=SCALE,
                        arguments={
                            "workload": WORKLOAD,
                            "environment": ENVIRONMENT,
                            "replicas": PROPOSED_REPLICAS,
                        },
                    ),
                ),
            )
        return self._result(
            f"{WORKLOAD} is serving more requests than {STARTING_REPLICAS} replicas can "
            f"absorb; raising the count to {PROPOSED_REPLICAS} is proposed.",
            (),
        )

    def _result(self, text: str, calls: tuple[ToolCall, ...]) -> InvokeResult:
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=text,
            tool_calls=calls,
            finish_reason=FinishReason.TOOL_CALLS if calls else FinishReason.STOP,
            usage=UsageRecord(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tokens=TokenCounts(input_tokens=400, output_tokens=120),
            ),
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        result = await self.invoke(request)
        yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=result.text)
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=result.finish_reason)


@dataclass(slots=True)
class _Deployment:
    """What one run of this scenario was carried out on."""

    store: FakePersistence
    state: GatewayState
    runner: ReActInvestigationRunner
    agent: _Agent
    workload: _Workload


def _catalogue() -> Registry:
    """Return three shipped capabilities: one write, one connected read, one not."""
    shipped = build_registry()
    held = {}
    for name in (SCALE, CONNECTED_READ, UNCONNECTED_READ):
        found = shipped.tool(name)
        assert found is not None, f"{name} is no longer in the shipped catalogue"
        held[name] = found
    return Registry(tools=held)


async def _seed(store: FakePersistence) -> None:
    """Create the organisation, the team, and the one integration it connected."""
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(node_id=TEAM, kind=ConfigNodeKind.TEAM, name=TEAM, parent_id=ORG)
        )
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    await ConfigService(gateway=store, scope=scope).set_settings(
        TEAM,
        {
            "integrations": {
                "active": [
                    {"name": "prometheus", "credential": "prometheus-token", "enabled": True}
                ]
            }
        },
        actor_id="ana",
    )


@pytest.fixture
async def deployment() -> AsyncIterator[_Deployment]:
    """Return a deployment composed the way this product's own roots compose one."""
    workload = _Workload()
    previous = control_plane.bind(workload)
    store = FakePersistence()
    await _seed(store)

    agent = _Agent()
    runner = ReActInvestigationRunner(llm=agent, registry=_catalogue())  # type: ignore[arg-type]
    runner.attach_recording(gateway=store, guardrails=GuardrailEngine(), broker=RunEventBroker())
    state = GatewayState(
        gateway=store,
        tokens=TokenService(gateway=store, recorder=AuditRecorder(gateway=store)),
        investigator=runner,
    )
    desk = await compose_remediation(state, org_id=ORG, proxy_url=PROXY)
    assert desk is not None, "the scenario's deployment could not compose a remediation desk"
    desk.executor.isolation = _NoIsolation()

    try:
        yield _Deployment(store=store, state=state, runner=runner, agent=agent, workload=workload)
    finally:
        control_plane.restore(previous)


def _alert() -> InvestigationStart:
    return InvestigationStart(
        run_id="run-1",
        objective=f"{WORKLOAD} is saturating its replicas in {ENVIRONMENT}",
        team_node_id=TEAM,
        principal_id="ana",
        org_id=ORG,
        alert_source="prometheus",
        context={"environment": ENVIRONMENT},
    )


async def _investigate(deployment: _Deployment) -> str:
    return await deployment.runner.investigate(_alert())


async def _pending(deployment: _Deployment) -> tuple[Any, ...]:
    async with deployment.store.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
        return await uow.approvals.list_pending(limit=20)


async def _approve(deployment: _Deployment, approval_id: str) -> Any:
    """Approve through the route a console button calls, as the person who reviews."""
    secret = await issue_token(
        deployment.store,
        deployment.state.tokens,
        user_id="reviewer",
        role=Role.OPERATOR,
        node_id=TEAM,
    )
    app = create_app(deployment.state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as http:
        return await http.post(
            f"/v1/approvals/{approval_id}/decision",
            json={"verdict": "approve", "reason": ""},
            headers={"Authorization": f"Bearer {secret}"},
        )


# --- 1. The turn is narrowed to what this team connected and this deployment can do ---


async def test_the_turn_is_offered_the_connected_vendor_and_not_the_other(
    deployment: _Deployment,
) -> None:
    """Read from the configuration tree, not declared to the runner.

    The same list a catalogue screen counts from. Two sources for this one fact
    is how a screen comes to say a team has fourteen capabilities while its
    investigations are handed eleven.
    """
    await _investigate(deployment)

    offered = tuple(schema.name for schema in deployment.agent.requests[0].tools)
    assert CONNECTED_READ in offered
    assert UNCONNECTED_READ not in offered, (
        f"the turn was offered {UNCONNECTED_READ}, which needs an integration this team "
        f"has not connected. It would report itself unavailable by name and the turn "
        f"would be spent either way."
    )


async def test_the_write_is_offered_because_this_deployment_can_carry_it(
    deployment: _Deployment,
) -> None:
    await _investigate(deployment)

    offered = tuple(schema.name for schema in deployment.agent.requests[0].tools)
    assert SCALE in offered, (
        "a deployment with a composed desk and registered components withheld the write "
        "it can actually perform, so the investigation could only ever diagnose."
    )


# --- 2. The proposal, with the undo beside it --------------------------------------


async def test_the_investigation_leaves_one_stored_proposal(
    deployment: _Deployment,
) -> None:
    await _investigate(deployment)

    pending = await _pending(deployment)
    assert len(pending) == 1
    proposed = pending[0].arguments.get("proposed", {})
    assert proposed.get("capability") == SCALE
    assert proposed.get("target", {}).get("identifier") == WORKLOAD
    assert proposed.get("requester") == "ana"
    assert proposed.get("run_id") == "run-1"


async def test_the_undo_is_stored_with_it_and_names_the_count_it_read(
    deployment: _Deployment,
) -> None:
    """Derived from the state read before the change, not from an intention."""
    await _investigate(deployment)

    pending = await _pending(deployment)
    async with deployment.store.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
        plan = await uow.approvals.rollback_plan_for(pending[0].approval_id)

    assert plan is not None and plan.steps
    written = str([dict(step.arguments) for step in plan.steps])
    assert str(STARTING_REPLICAS) in written, (
        f"the undo does not carry the replica count the workload held before the "
        f"change: {written}. A plan that cannot say what to go back to is not a plan."
    )


async def test_the_run_continues_past_the_proposal_and_concludes(
    deployment: _Deployment,
) -> None:
    summary = await _investigate(deployment)

    assert "proposed" in summary, (
        f"the run did not reach its conclusion: {summary!r}. An agent that stopped "
        f"because a mitigation needs a person threw away the diagnosis it reached."
    )


# --- 3. Nothing has happened yet ----------------------------------------------------


async def test_the_workload_is_untouched_until_somebody_approves(
    deployment: _Deployment,
) -> None:
    assert deployment.workload.replicas == STARTING_REPLICAS

    await _investigate(deployment)

    assert deployment.workload.changes == [], (
        "the deployment changed a production workload with nobody having approved it. "
        "It configured no posture, and silence resolves to proposing."
    )
    assert deployment.workload.replicas == STARTING_REPLICAS


async def test_nothing_is_recorded_as_done_before_the_approval(
    deployment: _Deployment,
) -> None:
    await _investigate(deployment)

    async with deployment.store.begin(TenantScope(org_id=ORG)) as uow:
        assert await uow.remediation.get("action-1") is None
    pending = await _pending(deployment)
    assert pending[0].state.value == "pending"


# --- 4. A person approves, and only then does anything move -------------------------


async def test_approving_moves_the_workload_and_nothing_else_did(
    deployment: _Deployment,
) -> None:
    await _investigate(deployment)
    pending = await _pending(deployment)
    assert deployment.workload.replicas == STARTING_REPLICAS

    response = await _approve(deployment, pending[0].approval_id)

    assert response.status_code == 200, response.text
    assert len(deployment.workload.changes) == 1, (
        f"the workload was changed {len(deployment.workload.changes)} time(s). One "
        f"approval authorises one action and never generalises to a second."
    )
    assert deployment.workload.replicas == PROPOSED_REPLICAS


async def test_what_the_execution_did_is_recorded_against_the_person_who_allowed_it(
    deployment: _Deployment,
) -> None:
    await _investigate(deployment)
    pending = await _pending(deployment)
    approval_id = pending[0].approval_id

    await _approve(deployment, approval_id)

    async with deployment.store.begin(TenantScope(org_id=ORG)) as uow:
        audited = await uow.audit.query(limit=50)
    named = [event.detail for event in audited if event.detail.get("approval_id") == approval_id]
    assert named, (
        f"no audit row names {approval_id!r} as what authorised the change, so nothing "
        f"ties it to the person who allowed it."
    )
    assert any(detail.get("autonomous") is False for detail in named)


async def test_the_obligation_to_find_out_whether_it_worked_is_written(
    deployment: _Deployment,
) -> None:
    """Pressing the button and reporting that the button was pressed is the gap."""
    await _investigate(deployment)
    pending = await _pending(deployment)

    await _approve(deployment, pending[0].approval_id)

    async with deployment.store.begin(TenantScope(org_id=ORG)) as uow:
        recorded = await uow.remediation.history(_everything())
    assert recorded, "the execution left nothing anybody has to come back and verify"
    outcome = recorded[0]
    assert not outcome.autonomous
    assert outcome.plan_id, (
        "the obligation was written with no plan beside it, so nothing could reverse a "
        "change that turned out to make things worse."
    )


def _everything() -> Any:
    """Return a query over every recorded outcome, however it went."""
    from platform.persistence.ports.remediation_ledger import EffectivenessQuery

    return EffectivenessQuery()
