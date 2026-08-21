"""A wired gateway, and a real, issued bearer token to drive it with.

Everything here is real: ``FakePersistence`` behind the same
``PersistenceGateway`` protocol Postgres implements, a real ``TokenService``
issuing a real token, and the real ``authorized`` dependency chain. Nothing
about authentication or permission checking is mocked — only the
investigation runtime is, because composing one is a deployment concern
(``gateway/http/services.py``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace

import pytest
from httpx import ASGITransport, AsyncClient

from core.agent.interaction.models import Answer, Interaction, InteractionState
from gateway.http.app import create_app
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.identity_repository import RoleBinding, User
from platform.persistence.ports.transaction import TenantScope

ORG = "acme"
TEAM_PAYMENTS = "payments"
TEAM_PLATFORM = "platform"


@dataclass(slots=True)
class FakeInvestigationRunner:
    """Records what it was asked to do, and answers interactions from a script."""

    started: list[InvestigationStart] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    taken_over: list[str] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    queued: list[tuple[str, str]] = field(default_factory=list)
    interactions: dict[str, Interaction] = field(default_factory=dict)

    async def investigate(self, request: InvestigationStart) -> str:
        self.started.append(request)
        return "done"

    async def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)

    async def take_over(self, run_id: str, *, principal: str) -> None:
        self.taken_over.append(run_id)

    async def resume(self, run_id: str) -> None:
        self.resumed.append(run_id)

    async def queue_message(self, run_id: str, text: str) -> None:
        self.queued.append((run_id, text))

    async def pending_interactions(self, run_id: str) -> tuple[Interaction, ...]:
        return tuple(held for held in self.interactions.values() if held.run_id == run_id)

    async def find_interaction(self, interaction_id: str) -> Interaction | None:
        return self.interactions.get(interaction_id)

    async def answer_interaction(
        self, interaction_id: str, *, text: str, principal: str, selected_option: str = ""
    ) -> Interaction:
        held = self.interactions[interaction_id]
        closed = replace(
            held,
            state=InteractionState.ANSWERED,
            answer=Answer(text=text, principal=principal, selected_option=selected_option),
        )
        self.interactions[interaction_id] = closed
        return closed


@dataclass(slots=True)
class Deployment:
    gateway: FakePersistence
    tokens: TokenService
    state: GatewayState
    runner: FakeInvestigationRunner


async def _seed_org(gateway: FakePersistence) -> None:
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        for team in (TEAM_PAYMENTS, TEAM_PLATFORM):
            await uow.config.upsert(
                ConfigNode(node_id=team, kind=ConfigNodeKind.TEAM, name=team, parent_id=ORG)
            )


async def issue_token(
    gateway: FakePersistence,
    tokens: TokenService,
    *,
    user_id: str,
    role: Role,
    node_id: str | None,
) -> str:
    """Create a user, grant ``role`` at ``node_id``, and return a real bearer secret."""
    scope = TenantScope(org_id=ORG, team_node_id=node_id)
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id=user_id, email=f"{user_id}@acme.test", display_name=user_id)
        )
        await uow.identity.upsert_role_binding(
            RoleBinding(
                binding_id=f"grant-{user_id}", user_id=user_id, role=role.value, node_id=node_id
            )
        )
    issued = await tokens.issue(
        scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=user_id),
        user_id=user_id,
        name=f"{user_id}-token",
        node_id=node_id,
        # This bearer secret stands in for the person just granted `role` —
        # a session-shaped credential, not a narrowly scoped machine token —
        # so it keeps resolving to whatever that person holds.
        unscoped=True,
    )
    return issued.secret


@pytest.fixture
async def deployment() -> Deployment:
    """Return a wired gateway with an organisation already created.

    ``tokens`` carries a recorder, matching the real gateway's own
    composition (`gateway/http/asgi.py`) — without one, every token issuance
    and revocation is silently missing from the audit trail regardless of
    what a route asks it to record.
    """
    gateway = FakePersistence()
    await _seed_org(gateway)
    tokens = TokenService(gateway=gateway, recorder=AuditRecorder(gateway=gateway))
    runner = FakeInvestigationRunner()
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=runner)
    return Deployment(gateway=gateway, tokens=tokens, state=state, runner=runner)


@pytest.fixture
async def client(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    """Return an HTTP client wired directly to the app over ASGI, no network."""
    app = create_app(deployment.state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http


__all__ = [
    "ORG",
    "TEAM_PAYMENTS",
    "TEAM_PLATFORM",
    "Deployment",
    "FakeInvestigationRunner",
    "issue_token",
]
