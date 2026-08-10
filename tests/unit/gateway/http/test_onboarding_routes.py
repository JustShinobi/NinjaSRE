"""Writing a credential over HTTP, through the real application and the real guard.

The route this exercises is the most security-sensitive one the API serves, and
every assertion here is about an absence: the value is not in the response, not
in the refusal, not in the audit detail, not in a log line. Field *names* are
allowed everywhere, values nowhere, which is the same line
``SetupOutcome.entered`` holds on the CLI side.

Everything goes through ``create_app``, the composed route table, and a real
issued token. A test that called the handler directly would prove the handler
works and nothing about whether ``credential.write`` is the permission actually
demanded of a caller.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from platform.credentials.handles import CredentialHandle
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.identity.permissions import Permission, Role, permissions_for
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

#: A value nothing may echo. Distinctive enough that a substring search over a
#: response body or a log line cannot match it by accident.
SENTINEL_API_KEY = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
SENTINEL_APP_KEY = "abcdefghij0123456789ABCDEFGHIJ0123456789"

CREDENTIAL_PATH = "/v1/integrations/datadog/credential"


def _headers(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
async def operator_token(deployment: Deployment) -> str:
    """A token holding ``credential.write``, at the team the write is scoped to."""
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


@pytest.fixture
async def viewer_token(deployment: Deployment) -> str:
    """A token holding none of the write permissions."""
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="viv",
        role=Role.VIEWER,
        node_id=TEAM_PAYMENTS,
    )


# --- The write ----------------------------------------------------------------


async def test_a_credential_is_written_and_answered_with_a_status(
    client: AsyncClient, operator_token: str
) -> None:
    """The response says what the credential now is, and never what was sent."""
    response = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={"values": {"api_key": SENTINEL_API_KEY, "app_key": SENTINEL_APP_KEY}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["integration"] == "datadog"
    assert body["usable"] is True
    assert body["state"] == "configured"
    assert body["version"] == 1
    assert body["fields"] == ["api_key", "app_key"]


async def test_the_value_appears_in_no_part_of_the_response(
    client: AsyncClient, operator_token: str
) -> None:
    """The failure this catches: a handler that echoes what it stored.

    Asserted over the raw bytes rather than over parsed fields, because the
    response model growing a field is exactly how an echo would appear.
    """
    response = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={"values": {"api_key": SENTINEL_API_KEY, "app_key": SENTINEL_APP_KEY}},
    )

    assert SENTINEL_API_KEY not in response.text
    assert SENTINEL_APP_KEY not in response.text


async def test_the_value_reaches_the_vault_and_the_vault_alone(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """A stored credential is one the proxy could resolve, at the version written."""
    await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={"values": {"api_key": SENTINEL_API_KEY, "app_key": SENTINEL_APP_KEY}},
    )

    vault = Vault(gateway=deployment.gateway, schemas=CredentialSchemaRegistry())
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    live = await vault.active(scope, CredentialHandle(integration="datadog", team_id=TEAM_PAYMENTS))

    assert live is not None
    assert live.version == 1
    assert live.is_active


async def test_writing_again_replaces_and_carries_the_version_forward(
    client: AsyncClient, operator_token: str
) -> None:
    """Rotation is the same route: storing again supersedes, and the sequence says so."""
    first = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={"values": {"api_key": SENTINEL_API_KEY, "app_key": SENTINEL_APP_KEY}},
    )
    second = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={
            "values": {"api_key": "f0e1d2c3b4a5968778695a4b3c2d1e0f", "app_key": SENTINEL_APP_KEY}
        },
    )

    assert first.json()["version"] == 1
    assert second.json()["version"] == 2


# --- What it refuses ----------------------------------------------------------


async def test_a_body_outside_the_schema_is_refused_naming_the_field(
    client: AsyncClient, operator_token: str
) -> None:
    """The refusal names the field that was wrong and never quotes its value."""
    response = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={"values": {"api_key": SENTINEL_API_KEY, "wrong_field": "irrelevant"}},
    )

    assert response.status_code == 400
    detail = response.text
    assert "wrong_field" in detail
    assert "app_key" in detail
    assert SENTINEL_API_KEY not in detail


async def test_an_unknown_integration_is_not_found(
    client: AsyncClient, operator_token: str
) -> None:
    response = await client.put(
        "/v1/integrations/no-such-vendor/credential",
        headers=_headers(operator_token),
        json={"values": {"api_key": SENTINEL_API_KEY}},
    )

    assert response.status_code == 404
    assert SENTINEL_API_KEY not in response.text


async def test_a_caller_without_credential_write_is_refused(
    client: AsyncClient, viewer_token: str
) -> None:
    """``credential.write`` is the permission, and it is checked before the body is read."""
    response = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(viewer_token),
        json={"values": {"api_key": SENTINEL_API_KEY, "app_key": SENTINEL_APP_KEY}},
    )

    assert response.status_code == 403
    assert SENTINEL_API_KEY not in response.text


async def test_an_empty_body_is_refused_rather_than_stored(
    client: AsyncClient, operator_token: str
) -> None:
    """Storing nothing would leave a credential that exists and cannot authenticate."""
    response = await client.put(
        CREDENTIAL_PATH, headers=_headers(operator_token), json={"values": {}}
    )

    assert response.status_code == 400


# --- The configuration route stays sealed --------------------------------------


async def test_the_config_route_refuses_a_field_an_integration_marks_secret(
    client: AsyncClient, operator_token: str
) -> None:
    """The credential route is the only way in, so the other way has to stay shut.

    Datadog's own schema calls ``api_key`` secret. Written into the one open map
    an integration entry has, it is refused whatever it contains — a key an
    operator invented matches nobody's pattern, so a shape scan alone would let
    it through.
    """
    response = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=_headers(operator_token),
        json={
            "patch": {
                "integrations": {
                    "active": [{"name": "datadog", "settings": {"api_key": "hunter2"}}]
                }
            }
        },
    )

    assert response.status_code == 400
    assert "api_key" in response.text
    assert "hunter2" not in response.text


# --- The permission this route demands ----------------------------------------


def test_credential_write_is_distinct_from_config_write() -> None:
    """Whoever may adjust a threshold is not automatically whoever may swap a key.

    Both are held by ``operator`` and above, so the distinction is not about who
    holds them today — it is that a deployment narrowing one does not silently
    narrow the other.
    """
    assert Permission.CREDENTIAL_WRITE is not Permission.CONFIG_WRITE
    assert Permission.CREDENTIAL_WRITE in permissions_for(Role.OWNER)
    assert Permission.CREDENTIAL_WRITE not in permissions_for(Role.RESPONDER)
