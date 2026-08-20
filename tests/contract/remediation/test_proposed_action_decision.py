"""What decides a proposed remediation action, and what it refuses to do.

An incident's proposed action is stored as an ``ApprovalRequest`` like any
other queued change, and Article III's two guarantees hold at the store the
decision route calls directly: a decision records who decided and when
*before* anything else happens, and an approval cannot be recorded at all
without a rollback plan already stored. This file proves both — over the
deployment, through the route a reviewer's click actually reaches — and proves
the route's other refusal: a rejection with no reason never reaches the store.

**The claim this file is built to protect is an absence, not a presence.** It
is easy to prove a decision gets recorded; it is the property that nothing
*runs* because of it that this feature exists to keep. Every test below that
touches the deployment also reads the remediation ledger — the table anything
actually executed would have written a row to — and asserts it stayed empty,
before the decision and after it. The route under test never imports anything
from ``platform.remediation.execution`` or a capability's own apply method;
this is what proves that in the running system rather than by inspection.

The capability side of the claim is separate and is proven first: a shipped
remediation capability whose effect is above read declares that a human must
approve it, and the declaration is not a convention an author could forget to
follow — it is a structural check on the metadata itself, run the moment the
capability is registered.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from capabilities.registry.catalogue import build_registry
from core.capability.metadata import SideEffectLevel, ToolMetadata
from gateway.http.app import create_app
from gateway.http.asgi import UnconfiguredInvestigator
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditContext
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PersistenceGateway
from platform.persistence.ports.approval_store import (
    ApprovalRequest,
    ApprovalState,
    RollbackPlan,
    RollbackStep,
)
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.identity_repository import RoleBinding, User
from platform.persistence.ports.remediation_ledger import EffectivenessQuery
from platform.persistence.ports.transaction import TenantScope

pytestmark = pytest.mark.contract

ORG = "northwind"
TEAM = "sre"
EPOCH = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def _pending_request(approval_id: str, *, run_id: str = "run-alert-1") -> ApprovalRequest:
    """Return one proposed remediation, awaiting a decision."""
    return ApprovalRequest(
        approval_id=approval_id,
        run_id=run_id,
        action="estate.restart_workload",
        side_effect_level=SideEffectLevel.WRITE_IRREVERSIBLE.value,
        summary="Restart the workload that stopped answering health checks.",
        requested_at=at(),
        expires_at=at(minutes=90),
        arguments={"resource_id": "checkout-api", "workload": "checkout-api"},
    )


def _rollback_plan(approval_id: str) -> RollbackPlan:
    """Return the plan Article III requires before ``approval_id`` may be approved."""
    return RollbackPlan(
        plan_id=f"{approval_id}-rollback",
        approval_id=approval_id,
        created_at=at(),
        steps=(
            RollbackStep(
                ordinal=1,
                description="Nothing to restore; a restart has no undo beyond waiting.",
                capability="estate.noop",
                arguments={},
            ),
        ),
    )


async def _seed_org(gateway: FakePersistence) -> None:
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Northwind")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(node_id=TEAM, kind=ConfigNodeKind.TEAM, name=TEAM, parent_id=ORG)
        )


async def _issue_token(
    gateway: FakePersistence, tokens: TokenService, *, user_id: str, role: Role
) -> str:
    """Create a user, grant ``role`` at the team, and return a real bearer secret."""
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id=user_id, email=f"{user_id}@northwind.test", display_name=user_id)
        )
        await uow.identity.upsert_role_binding(
            RoleBinding(
                binding_id=f"grant-{user_id}", user_id=user_id, role=role.value, node_id=TEAM
            )
        )
    issued = await tokens.issue(
        scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=user_id),
        user_id=user_id,
        name=f"{user_id}-token",
        node_id=TEAM,
        unscoped=True,
    )
    return issued.secret


@dataclass(slots=True)
class Deployment:
    client: AsyncClient
    gateway: FakePersistence
    secret: str


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
    """Yield a real ASGI client, the store behind it, and a responder's token."""
    store = FakePersistence()
    await _seed_org(store)
    tokens = TokenService(gateway=store)
    state = GatewayState(
        gateway=store,
        tokens=tokens,
        # The investigation runtime is not this file's subject — nothing here
        # starts one — so the stand-in that refuses everything is enough, and
        # it also proves the decision route never reaches through it.
        investigator=UnconfiguredInvestigator(),
    )
    secret = await _issue_token(store, tokens, user_id="responder-1", role=Role.RESPONDER)
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://deployment"
    ) as client:
        yield Deployment(client=client, gateway=store, secret=secret)


def bearer(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}"}


async def _nothing_ran(gateway: PersistenceGateway) -> bool:
    """Return whether the remediation ledger — what an execution would write to
    — holds no row at all, in this tenant."""
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        rows = await uow.remediation.history(EffectivenessQuery())
    return rows == ()


class TestACapabilityAboveReadDeclaresApproval:
    """The capability's own metadata, not a convention a route trusts.

    ``restart_workload`` is read from the real, validated registry — the same
    object the running investigation would be offered — rather than
    constructed by this test, so a change to the shipped declaration is what
    this test is about, not a copy of it.
    """

    def test_a_shipped_capability_above_read_requires_approval(self) -> None:
        found = build_registry().tool("restart_workload")
        assert found is not None
        metadata = found.metadata

        assert metadata.side_effect_level is SideEffectLevel.WRITE_IRREVERSIBLE
        assert metadata.side_effect_level.danger > SideEffectLevel.READ_SENSITIVE.danger
        assert metadata.requires_approval is True

    def test_the_declaration_is_a_structural_check_not_a_convention(self) -> None:
        """Invert the claim: an author who forgets ``requires_approval`` cannot
        register the capability at all — proven by trying, on the metadata
        type itself, not on a fake that merely agrees with the good case."""
        base = build_registry().tool("restart_workload")
        assert base is not None
        good = base.metadata
        assert isinstance(good, ToolMetadata)

        with pytest.raises(ValueError, match="requires_approval must be True"):
            ToolMetadata(
                name=good.name,
                display_name=good.display_name,
                description=good.description,
                evidence_source=good.evidence_source,
                evidence_type=good.evidence_type,
                side_effect_level=SideEffectLevel.WRITE_IRREVERSIBLE,
                parallel_safe=good.parallel_safe,
                requires_approval=False,
            )


class TestApprovingRecordsTheDecisionBeforeAnyEffect:
    async def test_approving_records_decision_decider_and_instant(
        self, deployment: Deployment
    ) -> None:
        approval_id = "apr-restart-1"
        async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
            await uow.approvals.create_request(_pending_request(approval_id))
            await uow.approvals.store_rollback_plan(_rollback_plan(approval_id))

        # Pending, and nothing has run — the state before the decision this
        # test is about to make.
        async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
            before = await uow.approvals.get_request(approval_id)
        assert before is not None
        assert before.state is ApprovalState.PENDING
        assert before.decided_by is None
        assert before.decided_at is None
        assert await _nothing_ran(deployment.gateway)

        response = await deployment.client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={"verdict": "approve"},
            headers=bearer(deployment.secret),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "approved"
        assert body["decided_by"] == "responder-1"
        assert body["decided_at"] != ""

        async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
            after = await uow.approvals.get_request(approval_id)
        assert after is not None
        assert after.state is ApprovalState.APPROVED
        assert after.decided_by == "responder-1"
        assert after.decided_at is not None

        # The claim this file exists for: recording the decision is not the
        # same as carrying it out. Nothing wrote to the ledger an execution
        # would have written to.
        assert await _nothing_ran(deployment.gateway)

    async def test_approving_without_a_stored_rollback_plan_is_refused(
        self, deployment: Deployment
    ) -> None:
        """Article III's 'and', enforced at the store this route calls — proven
        by omitting the plan a well-formed request always carries."""
        approval_id = "apr-no-plan-1"
        async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
            await uow.approvals.create_request(_pending_request(approval_id))
            # Deliberately: no store_rollback_plan call.

        response = await deployment.client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={"verdict": "approve"},
            headers=bearer(deployment.secret),
        )

        # Exactly 400 — a missing precondition, never a missing route. Read
        # loosely (any 4xx), this claim would also pass against a deployment
        # where the route itself does not exist, which proves nothing about
        # the guarantee it is meant to protect.
        assert response.status_code == 400
        assert "rollback plan" in response.json()["error"]["message"]

        async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
            after = await uow.approvals.get_request(approval_id)
        assert after is not None
        assert after.state is ApprovalState.PENDING
        assert after.decided_by is None
        assert await _nothing_ran(deployment.gateway)


class TestRejectingWithoutAReasonIsRefused:
    async def test_a_rejection_with_no_reason_never_reaches_the_store(
        self, deployment: Deployment
    ) -> None:
        approval_id = "apr-reject-1"
        async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
            await uow.approvals.create_request(_pending_request(approval_id))
            await uow.approvals.store_rollback_plan(_rollback_plan(approval_id))

        response = await deployment.client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={"verdict": "reject", "reason": ""},
            headers=bearer(deployment.secret),
        )

        assert response.status_code == 400

        async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
            after = await uow.approvals.get_request(approval_id)
        assert after is not None
        # Still pending: a refused rejection is not a decision, and nothing
        # about this request should read as "decided" because of the attempt.
        assert after.state is ApprovalState.PENDING
        assert after.decided_by is None
        assert after.decided_at is None
        assert await _nothing_ran(deployment.gateway)

    async def test_a_rejection_with_a_reason_is_recorded(self, deployment: Deployment) -> None:
        approval_id = "apr-reject-2"
        async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
            await uow.approvals.create_request(_pending_request(approval_id))
            await uow.approvals.store_rollback_plan(_rollback_plan(approval_id))

        response = await deployment.client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={"verdict": "reject", "reason": "the workload recovered on its own"},
            headers=bearer(deployment.secret),
        )

        assert response.status_code == 200
        assert response.json()["state"] == "rejected"

        async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
            after = await uow.approvals.get_request(approval_id)
        assert after is not None
        assert after.state is ApprovalState.REJECTED
        assert after.reason == "the workload recovered on its own"
        assert await _nothing_ran(deployment.gateway)


class TestTheAuditTrailCarriesBothDecisions:
    """FR-058: both decisions, not just one — a suite that only proved
    approval would leave the rejection path unaudited and nobody would know
    until an auditor asked for it."""

    async def test_an_approval_and_a_rejection_both_reach_the_audit_log(
        self, deployment: Deployment
    ) -> None:
        approved_id = "apr-audit-approve-1"
        rejected_id = "apr-audit-reject-1"
        async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
            for approval_id in (approved_id, rejected_id):
                await uow.approvals.create_request(_pending_request(approval_id))
                await uow.approvals.store_rollback_plan(_rollback_plan(approval_id))

        approve_response = await deployment.client.post(
            f"/v1/approvals/{approved_id}/decision",
            json={"verdict": "approve"},
            headers=bearer(deployment.secret),
        )
        reject_response = await deployment.client.post(
            f"/v1/approvals/{rejected_id}/decision",
            json={"verdict": "reject", "reason": "duplicate of an already-approved fix"},
            headers=bearer(deployment.secret),
        )
        assert approve_response.status_code == 200
        assert reject_response.status_code == 200

        async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
            events = await uow.audit.query(action="approval.decide", limit=50)

        by_resource = {event.resource_id: event for event in events}
        assert approved_id in by_resource
        assert rejected_id in by_resource

        approved_event = by_resource[approved_id]
        assert approved_event.actor_id == "responder-1"
        assert approved_event.action == "approval.decide"
        assert approved_event.outcome.value == "allowed"

        rejected_event = by_resource[rejected_id]
        assert rejected_event.actor_id == "responder-1"
        assert rejected_event.action == "approval.decide"
        assert rejected_event.outcome.value == "denied"


class TestADecisionCannotBeMadeTwice:
    async def test_a_second_decision_on_an_already_decided_approval_is_refused(
        self, deployment: Deployment
    ) -> None:
        approval_id = "apr-twice-1"
        async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
            await uow.approvals.create_request(_pending_request(approval_id))
            await uow.approvals.store_rollback_plan(_rollback_plan(approval_id))

        first = await deployment.client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={"verdict": "approve"},
            headers=bearer(deployment.secret),
        )
        assert first.status_code == 200

        second = await deployment.client.post(
            f"/v1/approvals/{approval_id}/decision",
            json={"verdict": "reject", "reason": "changed my mind"},
            headers=bearer(deployment.secret),
        )
        assert second.status_code == 409

        async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
            after = await uow.approvals.get_request(approval_id)
        assert after is not None
        # The first decision stands. A refused second attempt must not have
        # overwritten it.
        assert after.state is ApprovalState.APPROVED
