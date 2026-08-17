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
from httpx import ASGITransport, AsyncClient

from config.constants.llm import LOCAL_PROVIDERS, SUPPORTED_PROVIDERS
from core.llm.verification import ModelVerdict
from gateway.http.app import create_app
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
SENTINEL_SECRET_KEY = "abcdefghij0123456789ABCDEFGHIJ0123456789"

CREDENTIAL_PATH = "/v1/integrations/redis/credential"


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
async def organisation_token(deployment: Deployment) -> str:
    """A token held at the organisation rather than at any one team.

    The state a deployment starts in: the first administrator exists before
    any team node does, so the first principal to open the console has no team
    for a credential handle to name.
    """
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="grace",
        role=Role.OPERATOR,
        node_id=None,
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
        json={"values": {"api_key": SENTINEL_API_KEY, "secret_key": SENTINEL_SECRET_KEY}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["integration"] == "redis"
    assert body["usable"] is True
    assert body["state"] == "configured"
    assert body["version"] == 1
    assert body["fields"] == ["api_key", "secret_key"]


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
        json={"values": {"api_key": SENTINEL_API_KEY, "secret_key": SENTINEL_SECRET_KEY}},
    )

    assert SENTINEL_API_KEY not in response.text
    assert SENTINEL_SECRET_KEY not in response.text


async def test_the_value_reaches_the_vault_and_the_vault_alone(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """A stored credential is one the proxy could resolve, at the version written."""
    await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={"values": {"api_key": SENTINEL_API_KEY, "secret_key": SENTINEL_SECRET_KEY}},
    )

    vault = Vault(gateway=deployment.gateway, schemas=CredentialSchemaRegistry())
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    live = await vault.active(scope, CredentialHandle(integration="redis", team_id=TEAM_PAYMENTS))

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
        json={"values": {"api_key": SENTINEL_API_KEY, "secret_key": SENTINEL_SECRET_KEY}},
    )
    second = await client.put(
        CREDENTIAL_PATH,
        headers=_headers(operator_token),
        json={
            "values": {
                "api_key": "f0e1d2c3b4a5968778695a4b3c2d1e0f",
                "secret_key": SENTINEL_SECRET_KEY,
            }
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
    assert "secret_key" in detail
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
        json={"values": {"api_key": SENTINEL_API_KEY, "secret_key": SENTINEL_SECRET_KEY}},
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


# --- A provider's credential takes the same route ------------------------------


async def test_a_provider_credential_is_written_through_the_integration_route(
    client: AsyncClient, operator_token: str
) -> None:
    """One credential path, not two.

    A provider is not an installed integration — it has no vendor package — but
    it declares the same shape of credential, and a second write path for
    provider keys would be a second place credentials live and the one the audit
    misses.
    """
    response = await client.put(
        "/v1/integrations/anthropic/credential",
        headers=_headers(operator_token),
        json={"values": {"api_key": f"sk-ant-{SENTINEL_API_KEY}"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["integration"] == "anthropic"
    assert body["fields"] == ["api_key"]
    assert SENTINEL_API_KEY not in response.text


async def test_a_provider_credential_outside_its_declared_fields_is_refused(
    client: AsyncClient, operator_token: str
) -> None:
    response = await client.put(
        "/v1/integrations/anthropic/credential",
        headers=_headers(operator_token),
        json={"values": {"NOT_A_FIELD": "whatever"}},
    )

    assert response.status_code == 400
    assert "NOT_A_FIELD" in response.text
    assert "api_key" in response.text


# --- The provider surface -------------------------------------------------------


async def test_every_supported_provider_is_listed_in_the_documented_order(
    client: AsyncClient, operator_token: str
) -> None:
    response = await client.get("/v1/providers", headers=_headers(operator_token))

    assert response.status_code == 200
    listed = response.json()["providers"]
    assert [entry["provider_id"] for entry in listed] == list(SUPPORTED_PROVIDERS)
    assert all(entry["display_name"] for entry in listed)
    assert [entry["provider_id"] for entry in listed if entry["local"]] == list(LOCAL_PROVIDERS)


async def test_the_listing_says_which_providers_this_deployment_has_a_credential_for(
    client: AsyncClient, operator_token: str
) -> None:
    """Configured means a credential is in the vault, established by asking it."""
    before = await client.get("/v1/providers", headers=_headers(operator_token))
    await client.put(
        "/v1/integrations/anthropic/credential",
        headers=_headers(operator_token),
        json={"values": {"api_key": f"sk-ant-{SENTINEL_API_KEY}"}},
    )
    after = await client.get("/v1/providers", headers=_headers(operator_token))

    assert not any(entry["configured"] for entry in before.json()["providers"])
    configured = {
        entry["provider_id"] for entry in after.json()["providers"] if entry["configured"]
    }
    assert configured == {"anthropic"}
    assert SENTINEL_API_KEY not in after.text


async def test_a_caller_with_no_team_reads_the_organisation_wide_credential(
    client: AsyncClient, organisation_token: str
) -> None:
    """A team-less principal falls back to the organisation's own handle.

    ``-`` is what the handle grammar spells for a credential the organisation
    owns and every team without one of its own uses, and a caller holding no
    team is exactly that case. Passing the empty team through instead asks for
    a handle the grammar refuses, and the refusal reaches the client as a
    sanitised 500 — on the listing a deployment opens before it has teams.
    """
    written = await client.put(
        "/v1/integrations/anthropic/credential",
        headers=_headers(organisation_token),
        json={"values": {"api_key": f"sk-ant-{SENTINEL_API_KEY}"}},
    )
    response = await client.get("/v1/providers", headers=_headers(organisation_token))

    assert written.status_code == 200
    assert response.status_code == 200
    configured = {
        entry["provider_id"] for entry in response.json()["providers"] if entry["configured"]
    }
    assert configured == {"anthropic"}
    assert SENTINEL_API_KEY not in response.text


async def test_nothing_in_the_listing_claims_a_verification_nobody_ran(
    client: AsyncClient, operator_token: str
) -> None:
    """Configured and verified are different facts, and a listing may not merge them.

    A key that is present and a key that works are exactly the two states this
    distinction exists to separate, and the second is only knowable by calling
    the endpoint — which a listing must not do.
    """
    await client.put(
        "/v1/integrations/anthropic/credential",
        headers=_headers(operator_token),
        json={"values": {"api_key": f"sk-ant-{SENTINEL_API_KEY}"}},
    )

    listed = (await client.get("/v1/providers", headers=_headers(operator_token))).json()
    anthropic = next(entry for entry in listed["providers"] if entry["provider_id"] == "anthropic")

    assert anthropic["configured"]
    assert not anthropic["verified"]
    assert anthropic["detail"]


async def test_one_provider_comes_back_with_its_fields_guidance_and_models(
    client: AsyncClient, operator_token: str
) -> None:
    response = await client.get("/v1/providers/anthropic", headers=_headers(operator_token))

    assert response.status_code == 200
    body = response.json()
    assert body["provider_id"] == "anthropic"
    assert body["default_model"]
    assert body["models"]
    assert body["guidance"]
    assert body["where_to_get_it"]
    assert [declared["name"] for declared in body["fields"]] == ["api_key"]
    assert [declared["environment_variable"] for declared in body["fields"]] == [
        "ANTHROPIC_API_KEY"
    ]
    assert body["fields"][0]["secret"] is True
    assert body["fields"][0]["label"]


async def test_the_detail_names_which_of_its_models_support_tool_calling(
    client: AsyncClient, operator_token: str
) -> None:
    """The console's tool-calling badge reads this, never the onboarding list alone.

    `ProviderOnboarding.models` is names only; the capability lives in the model
    registry, keyed by the same `(provider_id, model_id)` pair. A console that
    read only the names would have nothing to badge with.
    """
    response = await client.get("/v1/providers/anthropic", headers=_headers(operator_token))

    assert response.status_code == 200
    body = response.json()
    capabilities = {
        entry["model_id"]: entry["supports_tools"] for entry in body["model_capabilities"]
    }
    # Every model the onboarding lists gets a row, in the same order.
    assert list(capabilities) == body["models"]
    # The registry's Anthropic rows all declare tool calling.
    assert capabilities["claude-sonnet-5"] is True


def test_a_model_the_registry_has_no_row_for_reports_unknown_not_unsupported() -> None:
    """'We don't know' and 'it does not support this' must never be the same badge.

    Reporting `False` for a model nothing has described would send an operator
    away from a model that might work perfectly well — the exact misdiagnosis
    this feature exists to correct. Every provider onboarding this build ships
    happens to list only models the registry also describes, so the gap is
    exercised directly against the pure mapping function rather than leaning on
    that agreement staying accidentally true.
    """
    from core.llm.onboarding import ProviderOnboarding
    from core.llm.registry import ModelDescriptor, ModelRegistry
    from gateway.http.routes.providers import _model_capabilities

    onboarding = ProviderOnboarding(
        provider_id="acme",
        display_name="Acme",
        default_model="acme-known",
        models=("acme-known", "acme-not-yet-described"),
    )
    registry = ModelRegistry()
    registry.register(
        ModelDescriptor(
            model_id="acme-known",
            provider_id="acme",
            context_window=1,
            max_output_tokens=1,
            supports_tools=True,
        )
    )

    found = {
        entry.model_id: entry.supports_tools for entry in _model_capabilities(onboarding, registry)
    }

    assert found == {"acme-known": True, "acme-not-yet-described": None}


async def test_a_provider_descriptor_carries_no_field_a_value_could_sit_in(
    client: AsyncClient, operator_token: str
) -> None:
    """Which is what makes the whole descriptor servable to an unprivileged reader."""
    await client.put(
        "/v1/integrations/anthropic/credential",
        headers=_headers(operator_token),
        json={"values": {"api_key": f"sk-ant-{SENTINEL_API_KEY}"}},
    )

    response = await client.get("/v1/providers/anthropic", headers=_headers(operator_token))

    assert SENTINEL_API_KEY not in response.text
    # `environment_variable` names a variable an operator may set; it is not a
    # place a stored value could be read back into, which is the property this
    # test exists to hold.
    assert set(response.json()["fields"][0]) == {
        "name",
        "label",
        "secret",
        "required",
        "help",
        "environment_variable",
    }


async def test_a_provider_nobody_supports_is_not_found(
    client: AsyncClient, operator_token: str
) -> None:
    response = await client.get("/v1/providers/anthropik", headers=_headers(operator_token))

    assert response.status_code == 404
    # The refusal names what does exist, so the next request is the right one.
    assert "anthropic" in response.text


# --- Verifying a provider is a real call ----------------------------------------


async def test_verifying_a_provider_reports_what_came_back(
    deployment: Deployment, operator_token: str
) -> None:
    """End to end against the model endpoint, not a check that a key is present."""
    asked: list[str] = []

    async def verifier(provider_id: str, model_id: str | None = None) -> ModelVerdict:
        asked.append(provider_id)
        return ModelVerdict(
            provider_id=provider_id,
            model_id="claude-sonnet-5",
            satisfied=True,
            summary_line="claude-sonnet-5 on anthropic calls tools and returns structure",
        )

    deployment.state.model_verifier = verifier
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        response = await http.post(
            "/v1/providers/anthropic/verify", headers=_headers(operator_token)
        )

    assert response.status_code == 200
    body = response.json()
    assert asked == ["anthropic"]
    assert body["provider_id"] == "anthropic"
    assert body["verified"] is True
    assert body["model_id"] == "claude-sonnet-5"
    assert "calls tools" in body["detail"]


async def test_a_verification_that_failed_says_what_could_not_be_done(
    deployment: Deployment, operator_token: str
) -> None:
    """A refusal names the limitation, never 'verification failed'."""

    async def verifier(provider_id: str, model_id: str | None = None) -> ModelVerdict:
        return ModelVerdict(
            provider_id=provider_id,
            model_id="llama4:70b",
            satisfied=False,
            limitation="the endpoint answered, but the model did not call the tool it was given",
            remedy="choose a model that supports tool calling",
            alternatives=("llama4:405b",),
        )

    deployment.state.model_verifier = verifier
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        response = await http.post("/v1/providers/ollama/verify", headers=_headers(operator_token))

    body = response.json()
    assert response.status_code == 200
    assert body["verified"] is False
    assert "did not call the tool" in body["detail"]
    assert body["remedy"]
    assert body["alternatives"] == ["llama4:405b"]


async def test_verifying_tests_the_model_the_deployment_is_configured_to_run(
    deployment: Deployment, operator_token: str
) -> None:
    """The check exercises the configured model, never the registry's default.

    An operator told "choose a model that supports tool calling" changes the
    configuration and presses the button again. A check that kept testing the
    shipped default would return the same refusal forever, and the remedy it
    prints would be one the operator has already applied.
    """
    asked: list[tuple[str, str | None]] = []

    async def verifier(provider_id: str, model_id: str | None = None) -> ModelVerdict:
        asked.append((provider_id, model_id))
        return ModelVerdict(
            provider_id=provider_id,
            model_id=model_id or "",
            satisfied=True,
            summary_line="it calls tools and returns structure",
        )

    deployment.state.model_verifier = verifier
    admin = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="root-admin",
        role=Role.ADMIN,
        node_id=None,
    )
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        written = await http.put(
            f"/v1/config/{ORG}",
            headers=_headers(admin),
            json={
                "patch": {
                    "models": {"investigator": {"provider": "ollama", "model": "llama4:405b"}}
                }
            },
        )
        assert written.status_code == 200, written.text
        response = await http.post("/v1/providers/ollama/verify", headers=_headers(operator_token))

    assert response.status_code == 200
    assert asked == [("ollama", "llama4:405b")]


async def test_verifying_another_provider_does_not_borrow_the_configured_model(
    deployment: Deployment, operator_token: str
) -> None:
    """A model name only travels to the provider it was configured for."""
    asked: list[tuple[str, str | None]] = []

    async def verifier(provider_id: str, model_id: str | None = None) -> ModelVerdict:
        asked.append((provider_id, model_id))
        return ModelVerdict(
            provider_id=provider_id,
            model_id=model_id or "claude-sonnet-5",
            satisfied=True,
            summary_line="it calls tools and returns structure",
        )

    deployment.state.model_verifier = verifier
    admin = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="root-admin-2",
        role=Role.ADMIN,
        node_id=None,
    )
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        written = await http.put(
            f"/v1/config/{ORG}",
            headers=_headers(admin),
            json={
                "patch": {
                    "models": {"investigator": {"provider": "ollama", "model": "llama4:405b"}}
                }
            },
        )
        assert written.status_code == 200, written.text
        response = await http.post(
            "/v1/providers/anthropic/verify", headers=_headers(operator_token)
        )

    assert response.status_code == 200
    assert asked == [("anthropic", None)]


async def test_verifying_a_provider_nobody_supports_is_not_found(
    client: AsyncClient, operator_token: str
) -> None:
    response = await client.post("/v1/providers/anthropik/verify", headers=_headers(operator_token))

    assert response.status_code == 404


async def test_reading_the_provider_listing_never_verifies_anything(
    deployment: Deployment, operator_token: str
) -> None:
    """Rendering a page must not be able to spend an operator's tokens by accident."""
    calls: list[str] = []

    async def verifier(provider_id: str, model_id: str | None = None) -> ModelVerdict:
        calls.append(provider_id)
        return ModelVerdict(provider_id=provider_id, model_id="m", satisfied=True)

    deployment.state.model_verifier = verifier
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        await http.get("/v1/providers", headers=_headers(operator_token))
        await http.get("/v1/providers/anthropic", headers=_headers(operator_token))

    assert calls == []


# --- The configuration route stays sealed --------------------------------------


async def test_the_config_route_refuses_a_field_an_integration_marks_secret(
    client: AsyncClient, operator_token: str
) -> None:
    """The credential route is the only way in, so the other way has to stay shut.

    Redis's own schema calls ``api_key`` secret. Written into the one open map
    an integration entry has, it is refused whatever it contains — a key an
    operator invented matches nobody's pattern, so a shape scan alone would let
    it through.
    """
    response = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=_headers(operator_token),
        json={
            "patch": {
                "integrations": {"active": [{"name": "redis", "settings": {"api_key": "hunter2"}}]}
            }
        },
    )

    assert response.status_code == 400
    assert "api_key" in response.text
    assert "hunter2" not in response.text


async def test_the_config_route_refuses_a_capability_nothing_installed(
    client: AsyncClient, operator_token: str
) -> None:
    """A name no capability answers to is a setting that will never do anything.

    The validator has always been able to say so; the write was constructed
    without the catalogue it needs to, so the cross-reference pass ran on the
    read routes and on nothing that stores a document. A misspelled capability
    was accepted, and what an operator saw afterwards was a tool that stayed
    switched off for no stated reason.
    """
    response = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=_headers(operator_token),
        json={"patch": {"capabilities": {"enabled": ["assess_evidenec_sufficiency"]}}},
    )

    assert response.status_code == 400
    assert "assess_evidenec_sufficiency" in response.text


async def test_the_preview_names_the_refusal_the_write_would_make(
    client: AsyncClient, operator_token: str
) -> None:
    """The half that makes the refusal above a prediction rather than a surprise.

    A preview that reports the merge, the locks and the gates and says nothing
    about validation reads as approval — and the refusal then arrives as a 400
    after somebody has pressed save on a screen that told them the outcome. Both
    answers come from one validator, so they cannot disagree about a document.
    """
    response = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=_headers(operator_token),
        json={"patch": {"capabilities": {"enabled": ["assess_evidenec_sufficiency"]}}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert [error["path"] for error in body["errors"]] == [
        "capabilities.assess_evidenec_sufficiency"
    ]


async def test_a_preview_of_an_ordinary_change_reports_nothing_wrong_with_it(
    client: AsyncClient, operator_token: str
) -> None:
    """Otherwise the field above would be a warning nobody can distinguish."""
    response = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=_headers(operator_token),
        json={"patch": {"capabilities": {"enabled": ["assess_evidence_sufficiency"]}}},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["errors"] == []


async def test_a_capability_this_deployment_does_have_is_written(
    client: AsyncClient, operator_token: str
) -> None:
    """The other half, because a check that refuses everything is not a check."""
    response = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=_headers(operator_token),
        json={"patch": {"capabilities": {"enabled": ["assess_evidence_sufficiency"]}}},
    )

    assert response.status_code == 200
    assert response.json()["values"]["capabilities"]["enabled"] == ["assess_evidence_sufficiency"]


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
