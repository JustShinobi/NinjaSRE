"""Single sign-on cannot go live until a test has passed on the same document.

The one requirement these four routes exist for. SSO is the path every human
uses, so a misconfiguration is not a degraded feature — it is every operator
locked out of the tool they would use to fix it. So activation is refused until
a test has passed, and the test is bound to the settings that passed it: editing
anything invalidates it, and the invalidation is a property of the data rather
than a rule anybody has to apply.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from platform.identity.permissions import Role
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio

#: A configuration that is valid in every way this deployment can check.
GOOD: dict[str, Any] = {
    "provider": "keycloak",
    "issuer": "https://id.example.invalid/realms/main",
    "client_id": "ninjasre",
    "authorisation_endpoint": "https://id.example.invalid/auth",
    "token_endpoint": "https://id.example.invalid/token",
    "jwks_uri": "https://id.example.invalid/certs",
    "redirect_uri": "https://ninjasre.example.invalid/auth/callback",
    "scopes": ["openid", "email", "profile"],
    "group_to_node": {"sre": "team-platform"},
    "default_node_id": "org-northwind",
}

#: What the provider returns for a test user.
CLAIMS: dict[str, Any] = {
    "iss": GOOD["issuer"],
    "sub": "f81d4fae",
    "email": "avery@example.invalid",
    "name": "Avery Lockhart",
    "groups": ["sre"],
}


async def _owner(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def _configured(client: AsyncClient, headers: dict[str, str], **over: Any) -> None:
    written = await client.put("/identity/sso", headers=headers, json={**GOOD, **over})
    assert written.status_code == 200, written.text


# --- What is configured -------------------------------------------------------


async def test_a_deployment_that_configured_nothing_says_what_is_missing(
    client: AsyncClient, deployment: Deployment
) -> None:
    answer = await client.get("/identity/sso", headers=await _owner(deployment))

    assert answer.status_code == 200
    body = answer.json()
    assert body["is_active"] is False
    assert body["verified"] is False
    # In operator language, and every problem at once rather than the first.
    assert any("issuer" in problem for problem in body["problems"])


async def test_what_was_written_is_what_comes_back(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)

    body = (await client.get("/identity/sso", headers=headers)).json()
    assert body["issuer"] == GOOD["issuer"]
    assert body["group_to_node"] == {"sre": "team-platform"}
    assert body["problems"] == []


async def test_a_provider_reachable_over_plain_http_is_reported_as_unusable(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers, issuer=["http:", "//id.example.invalid"][0] + "//x")

    body = (await client.get("/identity/sso", headers=headers)).json()
    assert any("https" in problem for problem in body["problems"])


# --- The test, and what it binds ----------------------------------------------


async def test_a_passing_test_reports_where_the_claims_land(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)

    answer = await client.post("/identity/sso/test", headers=headers, json={"claims": CLAIMS})

    assert answer.status_code == 200
    body = answer.json()
    assert body["succeeded"] is True
    assert body["email"] == "avery@example.invalid"
    assert body["mapped_node_id"] == "team-platform"
    assert body["used_default"] is False


async def test_a_passing_test_marks_the_configuration_verified(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)

    await client.post("/identity/sso/test", headers=headers, json={"claims": CLAIMS})

    assert (await client.get("/identity/sso", headers=headers)).json()["verified"] is True


async def test_claims_from_another_issuer_fail_the_test_and_verify_nothing(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)

    answer = await client.post(
        "/identity/sso/test",
        headers=headers,
        json={"claims": {**CLAIMS, "iss": "https://someone-else.example.invalid"}},
    )

    assert answer.json()["succeeded"] is False
    assert (await client.get("/identity/sso", headers=headers)).json()["verified"] is False


async def test_a_claim_set_missing_the_email_fails_naming_the_claim(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)

    answer = await client.post(
        "/identity/sso/test",
        headers=headers,
        json={"claims": {key: value for key, value in CLAIMS.items() if key != "email"}},
    )

    body = answer.json()
    assert body["succeeded"] is False
    assert any("email" in problem for problem in body["problems"])


# --- Activation ---------------------------------------------------------------


async def test_an_untested_configuration_cannot_be_activated(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)

    answer = await client.post("/identity/sso/activate", headers=headers)

    assert answer.status_code == 400
    assert (await client.get("/identity/sso", headers=headers)).json()["is_active"] is False


async def test_a_tested_configuration_can_be_activated(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)
    await client.post("/identity/sso/test", headers=headers, json={"claims": CLAIMS})

    answer = await client.post("/identity/sso/activate", headers=headers)

    assert answer.status_code == 200
    assert answer.json()["is_active"] is True


async def test_activating_does_not_invalidate_the_test_that_permitted_it(
    client: AsyncClient, deployment: Deployment
) -> None:
    # ``is_active`` is not in the fingerprint. If it were, activation would
    # invalidate its own permission and nothing could ever stay active.
    headers = await _owner(deployment)
    await _configured(client, headers)
    await client.post("/identity/sso/test", headers=headers, json={"claims": CLAIMS})
    await client.post("/identity/sso/activate", headers=headers)

    body = (await client.get("/identity/sso", headers=headers)).json()
    assert body["is_active"] is True
    assert body["verified"] is True


async def test_editing_the_configuration_invalidates_the_test_and_deactivates_it(
    client: AsyncClient, deployment: Deployment
) -> None:
    # The lockout the whole flow exists to prevent: a provider that was tested,
    # then edited, then still activatable on the strength of the old result.
    headers = await _owner(deployment)
    await _configured(client, headers)
    await client.post("/identity/sso/test", headers=headers, json={"claims": CLAIMS})
    await client.post("/identity/sso/activate", headers=headers)

    await _configured(client, headers, client_id="a-different-client")

    body = (await client.get("/identity/sso", headers=headers)).json()
    assert body["verified"] is False
    assert body["is_active"] is False
    assert (await client.post("/identity/sso/activate", headers=headers)).status_code == 400


async def test_an_unusable_configuration_cannot_be_activated_however_it_was_tested(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)
    await client.post("/identity/sso/test", headers=headers, json={"claims": CLAIMS})
    await _configured(client, headers, default_node_id="")

    answer = await client.post("/identity/sso/activate", headers=headers)

    assert answer.status_code == 400


async def test_activation_is_recorded_in_the_audit_trail(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    await _configured(client, headers)
    await client.post("/identity/sso/test", headers=headers, json={"claims": CLAIMS})

    await client.post("/identity/sso/activate", headers=headers)

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    activation = [
        event for event in events if event.detail.get("field") == "policies.sso.is_active"
    ]
    assert activation, [event.detail for event in events]
    # Most recent first: the activation is the latest change to this field,
    # after the earlier save that first set it to `False`.
    assert activation[0].detail["new_value"] is True


async def test_a_viewer_cannot_read_or_change_the_identity_provider(
    client: AsyncClient, deployment: Deployment
) -> None:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="vera", role=Role.VIEWER, node_id=None
    )
    headers = {"authorization": f"Bearer {secret}"}

    assert (await client.get("/identity/sso", headers=headers)).status_code == 403
    assert (await client.put("/identity/sso", headers=headers, json=GOOD)).status_code == 403
    assert (await client.post("/identity/sso/activate", headers=headers)).status_code == 403
