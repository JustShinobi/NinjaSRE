"""Graceful shutdown: drains in-flight investigations, refuses new ones while draining (SC-008)."""

from __future__ import annotations

import asyncio

import pytest

from gateway.http.lifespan import drain
from gateway.http.services import InvestigationStart
from tests.unit.gateway.http.conftest import Deployment

pytestmark = pytest.mark.asyncio


class _BlockingRunner:
    """Stays inside ``investigate`` until released, so a test can hold a run open."""

    def __init__(self, released: asyncio.Event) -> None:
        self.released = released
        self.cancelled: list[str] = []

    async def investigate(self, request: InvestigationStart) -> str:
        await self.released.wait()
        return "done"

    async def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)
        self.released.set()

    async def queue_message(self, run_id: str, text: str) -> None: ...

    async def pending_interactions(self, run_id: str) -> tuple[object, ...]:
        return ()

    async def find_interaction(self, interaction_id: str) -> object | None:
        return None

    async def answer_interaction(
        self, interaction_id: str, *, text: str, principal: str, selected_option: str = ""
    ) -> object:
        raise NotImplementedError


async def test_draining_waits_for_in_flight_runs_to_finish(deployment: Deployment) -> None:
    released = asyncio.Event()
    deployment.state.investigator = _BlockingRunner(released)

    async def start() -> None:
        from gateway.http.orchestration import start_investigation
        from platform.persistence.ports.transaction import TenantScope

        await start_investigation(
            deployment.state,
            scope=TenantScope(org_id="acme"),
            trigger="interactive",
            objective="x",
            principal_id="ada",
        )

    await start()
    assert len(deployment.state.background_runs) == 1

    released.set()
    await drain(deployment.state, timeout_seconds=2.0)

    assert deployment.state.draining is True
    assert len(deployment.state.background_runs) == 0


async def test_a_request_while_draining_is_refused(deployment: Deployment) -> None:
    from httpx import ASGITransport, AsyncClient

    from gateway.http.app import create_app
    from platform.identity.permissions import Role
    from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, issue_token

    deployment.state.draining = True
    app = create_app(deployment.state)
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as client:
        response = await client.post(
            "/v1/investigations",
            json={"objective": "x"},
            headers={"Authorization": f"Bearer {secret}"},
        )
    assert response.status_code == 400
    assert "shutting down" in response.json()["error"]["message"]
