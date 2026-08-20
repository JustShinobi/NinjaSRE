"""The delivery token Alert intake mints crosses the deployment exactly once.

Feature 050 already built the screen mechanics — the button, the one-time
render, the courier that forwards a session credential and asks for nothing
but the delivery scope (``console/tests/unit/surfaces/delivery-token.test.tsx``)
— and proved, at the console layer, that the component never holds the value
anywhere a reload could recover it from. What that layer cannot prove is the
half of the claim that lives on the other side of the wire: that a screen
visited *after* issuance, reading the real route a real reload would hit,
never gets the value back either.

This file proves that over a real ASGI app and a real store (``FakePersistence``,
the same fake the contract suite runs every backend against), the same pattern
``tests/contract/remediation/test_proposed_action_decision.py`` uses for its
own "acting over the real route" claims. The scan is structural rather than a
single-field check: it walks the entire JSON body a later read returns, so a
future field added to ``TokenView`` that happened to echo something
secret-shaped would still be caught, not only the field this test happened to
think to check.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.asgi import UnconfiguredInvestigator
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditContext
from platform.identity.permissions import Permission, Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.identity_repository import RoleBinding, User
from platform.persistence.ports.transaction import TenantScope

pytestmark = pytest.mark.contract

ORG = "northwind"
TEAM = "sre"

#: The one scope Alert intake's own courier ever asks for
#: (``console/src/app/api/delivery-token/route.ts``'s ``DELIVERY_PERMISSION``).
DELIVERY_PERMISSION = Permission.WEBHOOK_DELIVER.value


def _strings(value: object) -> list[str]:
    """Every string ``value`` carries, at any depth of a JSON-shaped object."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        found: list[str] = []
        for item in value.values():
            found.extend(_strings(item))
        return found
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        found = []
        for item in value:
            found.extend(_strings(item))
        return found
    return []


def _carries(payload: object, needle: str) -> bool:
    """Return whether any string ``payload`` carries, at any depth, contains ``needle``."""
    return any(needle in text for text in _strings(payload))


async def _seed_org(gateway: FakePersistence) -> None:
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Northwind")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(node_id=TEAM, kind=ConfigNodeKind.TEAM, name=TEAM, parent_id=ORG)
        )


async def _issue_operator_token(
    gateway: FakePersistence, tokens: TokenService, *, user_id: str
) -> str:
    """Create an admin holding ``token.manage`` — the permission both
    ``POST /identity/tokens`` and ``GET /identity/tokens`` require — and
    return a real bearer secret for them, unscoped so it resolves to whatever
    the role holds rather than to a fixed list this test would have to keep
    in step with the role table by hand.
    """
    scope = TenantScope(org_id=ORG, team_node_id=TEAM)
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id=user_id, email=f"{user_id}@northwind.test", display_name=user_id)
        )
        await uow.identity.upsert_role_binding(
            RoleBinding(
                binding_id=f"grant-{user_id}",
                user_id=user_id,
                role=Role.ADMIN.value,
                node_id=TEAM,
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
    operator_secret: str


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
    """Yield a real ASGI client and an operator's own real bearer secret."""
    store = FakePersistence()
    await _seed_org(store)
    tokens = TokenService(gateway=store)
    state = GatewayState(
        gateway=store,
        tokens=tokens,
        # This file is not about investigations; the refusing stand-in is
        # enough, and it doubles as proof nothing here reaches through it.
        investigator=UnconfiguredInvestigator(),
    )
    operator_secret = await _issue_operator_token(store, tokens, user_id="operator-1")
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://deployment"
    ) as client:
        yield Deployment(client=client, gateway=store, operator_secret=operator_secret)


def bearer(secret: str) -> dict[str, str]:
    return {"authorization": f"Bearer {secret}"}


async def _issue_delivery_token(deployment: Deployment) -> str:
    """Issue a delivery token through the real route, and return its secret."""
    response = await deployment.client.post(
        "/identity/tokens",
        json={
            "name": "alert-delivery",
            "permissions": [DELIVERY_PERMISSION],
            "node_id": TEAM,
        },
        headers=bearer(deployment.operator_secret),
    )
    assert response.status_code == 201, response.text
    secret = str(response.json()["secret"])
    assert secret != ""
    return secret


class TestTheDeliveryTokensValueCrossesTheDeploymentExactlyOnce:
    async def test_the_issuing_response_is_the_one_place_the_value_appears(
        self, deployment: Deployment
    ) -> None:
        response = await deployment.client.post(
            "/identity/tokens",
            json={
                "name": "alert-delivery",
                "permissions": [DELIVERY_PERMISSION],
                "node_id": TEAM,
            },
            headers=bearer(deployment.operator_secret),
        )
        assert response.status_code == 201
        body = response.json()
        # Real, high-entropy — not vacuous should the scan below find nothing
        # because the fixture accidentally issued an empty or trivial value.
        assert len(body["secret"]) > 20
        assert body["token"]["name"] == "alert-delivery"
        assert body["token"]["scopes"] == [DELIVERY_PERMISSION]

    async def test_no_later_read_returns_the_value(self, deployment: Deployment) -> None:
        secret = await _issue_delivery_token(deployment)

        listed = await deployment.client.get(
            "/identity/tokens", headers=bearer(deployment.operator_secret)
        )
        assert listed.status_code == 200
        payload = listed.json()

        # Not vacuous the other way: the token this issuance made really is
        # in the later read, by name — a read that came back empty, or that
        # never actually reached the token this test just issued, would
        # trivially "not carry the secret" without proving anything about
        # leakage.
        names = [entry["name"] for entry in payload["tokens"]]
        assert "alert-delivery" in names

        assert not _carries(payload, secret), (
            "a later read of /identity/tokens carried the delivery token's own "
            f"secret value somewhere in its body: {payload!r}"
        )

    async def test_a_second_issuance_never_echoes_the_first_tokens_value_either(
        self, deployment: Deployment
    ) -> None:
        """The same claim, proved against the one other route that returns a
        token's own secret at all — a second, unrelated issuance — so "no
        later read" is not quietly narrowed to mean "no later *list* read"."""
        first_secret = await _issue_delivery_token(deployment)

        second = await deployment.client.post(
            "/identity/tokens",
            json={
                "name": "alert-delivery-2",
                "permissions": [DELIVERY_PERMISSION],
                "node_id": TEAM,
            },
            headers=bearer(deployment.operator_secret),
        )
        assert second.status_code == 201
        assert not _carries(second.json(), first_secret)


__all__: list[str] = []
