"""A wired gateway for the deployment-scoped event channel's contract tests.

Builds the same `Deployment` shape `tests/unit/gateway/http/conftest.py`
does — a real, issued bearer token against `FakePersistence` — by calling
its own seeding helper rather than a second, competing wiring that could
drift from it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditRecorder
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    TEAM_PLATFORM,
    Deployment,
    FakeInvestigationRunner,
    _seed_org,
    issue_token,
)

__all__ = [
    "ORG",
    "TEAM_PAYMENTS",
    "TEAM_PLATFORM",
    "Deployment",
    "FakeInvestigationRunner",
    "app",
    "client",
    "deployment",
    "issue_token",
]


@pytest.fixture
async def deployment() -> Deployment:
    """Return a wired gateway with an organisation already created."""
    gateway = FakePersistence()
    await _seed_org(gateway)
    tokens = TokenService(gateway=gateway, recorder=AuditRecorder(gateway=gateway))
    runner = FakeInvestigationRunner()
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=runner)
    return Deployment(gateway=gateway, tokens=tokens, state=state, runner=runner)


@pytest.fixture
def app(deployment: Deployment) -> Any:
    """Return the raw ASGI application, for a test that drives it directly.

    ``client`` below wraps this in ``httpx.ASGITransport``, which is right
    for every ordinary request — but ``ASGITransport.handle_async_request``
    only returns once the whole ASGI call has *finished*, so it cannot carry
    a response from a body iterator that never completes on its own, which
    is exactly what an open SSE connection is. A test of the deployment
    channel's live delivery drives this fixture directly instead; see
    ``tests/contract/gateway/test_deployment_stream.py`` for the driver.
    """
    return create_app(deployment.state)


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    """Return an HTTP client wired directly to the app over ASGI, no network."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http
