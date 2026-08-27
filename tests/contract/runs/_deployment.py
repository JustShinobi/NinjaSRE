"""A real ASGI deployment, seeded directly through the recorder, for the report and replay contract.

Self-contained rather than importing another directory's ``conftest.py`` —
the convention this suite already follows (see
``tests/unit/gateway/runtime/conftest.py``'s own docstring) — because a test
module is not a package another directory can import across a boundary.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.asgi import UnconfiguredInvestigator
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditContext
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.identity_repository import RoleBinding, User
from platform.persistence.ports.transaction import TenantScope

ORG = "acme"
TEAM = "sre"


async def _seed_org(gateway: FakePersistence) -> None:
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(node_id=TEAM, kind=ConfigNodeKind.TEAM, name=TEAM, parent_id=ORG)
        )


async def _issue_operator_token(gateway: FakePersistence, tokens: TokenService) -> str:
    """Return a real bearer secret for an admin who can read anything in the org."""
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id="operator-1", email="operator-1@acme.test", display_name="operator-1")
        )
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id="grant-operator-1", user_id="operator-1", role=Role.ADMIN.value)
        )
    issued = await tokens.issue(
        scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id="operator-1"),
        user_id="operator-1",
        name="operator-1-token",
        unscoped=True,
    )
    return issued.secret


@dataclass(slots=True)
class Deployment:
    client: AsyncClient
    gateway: FakePersistence
    operator_secret: str


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
    """A real ASGI app over a real ``FakePersistence``, with an operator token.

    No live investigation runtime — every test in this directory seeds its
    run directly through ``RunRecorder``/``IncidentLifecycle`` and reads it
    back over HTTP, which is the boundary these tests exist to check.
    """
    gateway = FakePersistence()
    await _seed_org(gateway)
    tokens = TokenService(gateway=gateway)
    operator_secret = await _issue_operator_token(gateway, tokens)
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=UnconfiguredInvestigator())
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as client:
        yield Deployment(client=client, gateway=gateway, operator_secret=operator_secret)


def bearer(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}"}


__all__ = ["ORG", "TEAM", "Deployment", "bearer", "deployment"]
