"""SC-005: no error response contains exception detail, across routes.

A secret-looking string is planted in an unexpected exception's own message —
the shape a library's own error routinely takes. The response must carry only
the exception's type name; the secret must never cross the boundary, and must
still land in the server-side log for whoever has to debug it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from platform.identity.permissions import Role
from tests.unit.gateway.http.conftest import TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.asyncio

SENTINEL_SECRET = "sk-super-secret-do-not-leak-9f8e7d6c5b"


async def _auth_header(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    return {"Authorization": f"Bearer {secret}"}


async def test_an_unexpected_exception_is_sanitised_to_a_type_name(deployment: Deployment) -> None:
    headers = await _auth_header(deployment)
    app = create_app(deployment.state)

    # ``raise_app_exceptions=False``: Starlette's ``ServerErrorMiddleware`` sends
    # the sanitised response and then re-raises the original exception so the
    # ASGI *server* can log it — real servers deliver the response regardless,
    # but httpx's default transport surfaces the re-raise to the caller too.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        with patch(
            "gateway.http.orchestration.RunRecorder.start_run",
            new=AsyncMock(side_effect=RuntimeError(f"connection string leaked: {SENTINEL_SECRET}")),
        ):
            response = await client.post(
                "/v1/investigations", json={"objective": "x"}, headers=headers
            )

    assert response.status_code == 500
    body = response.text
    assert SENTINEL_SECRET not in body
    document = response.json()
    assert document["error"]["type"] == "internal_error"
    assert "RuntimeError" in document["error"]["message"]
    assert SENTINEL_SECRET not in document["error"]["message"]
    assert "correlation_id" in document["error"]


async def test_a_permission_denial_carries_no_stack_trace(
    client: AsyncClient, deployment: Deployment
) -> None:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="viewer",
        role=Role.VIEWER,
        node_id=TEAM_PAYMENTS,
    )
    response = await client.post(
        "/v1/investigations", json={"objective": "x"}, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 403
    assert "Traceback" not in response.text
    assert response.json()["error"]["type"] == "permission_denied"


async def test_a_malformed_bearer_token_is_refused_without_detail(client: AsyncClient) -> None:
    response = await client.get(
        "/v1/investigations", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
    assert "Traceback" not in response.text


async def test_a_validation_error_names_no_internal_detail(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _auth_header(deployment)
    response = await client.post("/v1/investigations", json={"objective": ""}, headers=headers)
    assert response.status_code == 422
    assert "Traceback" not in response.text
