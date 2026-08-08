"""Graceful shutdown: drains in-flight investigations, refuses new ones while draining,
and loses nothing — a run still going past the grace period is asked to stop rather
than abandoned, and whatever it produced is recorded (SC-008)."""

from __future__ import annotations

import asyncio

import pytest

from gateway.http.lifespan import drain
from gateway.http.orchestration import start_investigation
from gateway.http.services import InvestigationStart
from platform.persistence.ports.run_trace_store import RunStatus
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import Deployment

pytestmark = pytest.mark.asyncio

SCOPE = TenantScope(org_id="acme")


class _BlockingRunner:
    """Stays inside ``investigate`` until released, so a test can hold a run open.

    ``cancel`` is what shutdown calls after the grace period — it does not
    tear anything down itself, it asks, exactly as the protocol documents.
    Releasing here is standing in for a real runtime reaching its next safe
    point and returning.
    """

    def __init__(self, released: asyncio.Event) -> None:
        self.released = released
        self.cancel_requested = False
        self.cancelled: list[str] = []

    async def investigate(self, request: InvestigationStart) -> str:
        await self.released.wait()
        return "stopped at the operator's request" if self.cancel_requested else "done"

    async def cancel(self, run_id: str) -> None:
        self.cancelled.append(run_id)
        self.cancel_requested = True
        self.released.set()

    async def take_over(self, run_id: str, *, principal: str) -> None: ...

    async def resume(self, run_id: str) -> None: ...

    async def queue_message(self, run_id: str, text: str) -> None: ...

    async def pending_interactions(self, run_id: str) -> tuple[object, ...]:
        return ()

    async def find_interaction(self, interaction_id: str) -> object | None:
        return None

    async def answer_interaction(
        self, interaction_id: str, *, text: str, principal: str, selected_option: str = ""
    ) -> object:
        raise NotImplementedError


async def _start(deployment: Deployment) -> str:
    return await start_investigation(
        deployment.state, scope=SCOPE, trigger="interactive", objective="x", principal_id="ada"
    )


async def test_draining_waits_for_in_flight_runs_and_keeps_their_result(
    deployment: Deployment,
) -> None:
    released = asyncio.Event()
    deployment.state.investigator = _BlockingRunner(released)

    run_id = await _start(deployment)
    assert len(deployment.state.background_runs) == 1

    released.set()
    await drain(deployment.state, timeout_seconds=2.0)

    assert deployment.state.draining is True
    assert len(deployment.state.background_runs) == 0

    async with deployment.gateway.begin(SCOPE) as uow:
        run = await uow.run_traces.get_run(run_id)
    assert run is not None
    assert run.status is RunStatus.COMPLETED
    assert run.summary == "done"


async def test_a_run_past_the_grace_period_is_asked_to_stop_and_its_result_is_kept(
    deployment: Deployment,
) -> None:
    """The run never releases on its own — ``drain`` has to reach for ``cancel``
    after the grace period, and what the run produced still has to be there
    afterwards. Nothing accepted before shutdown is abandoned."""
    released = asyncio.Event()
    runner = _BlockingRunner(released)
    deployment.state.investigator = runner

    run_id = await _start(deployment)
    assert len(deployment.state.background_runs) == 1

    await drain(deployment.state, timeout_seconds=0.1)

    assert run_id in runner.cancelled
    assert len(deployment.state.background_runs) == 0

    async with deployment.gateway.begin(SCOPE) as uow:
        run = await uow.run_traces.get_run(run_id)
    assert run is not None
    assert run.status is RunStatus.COMPLETED
    assert run.summary == "stopped at the operator's request"


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
