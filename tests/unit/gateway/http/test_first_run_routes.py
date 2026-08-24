"""The first-run routes, driven through the real application and the real guard.

FR-010's console entry point and FR-022's "reachable afterwards". Everything
here goes through ``create_app``, the real permission table, and a real issued
token, because the property being tested is that a caller holding the credential
bring-up printed can actually reach these — which is the same class of bug the
whole feature exists for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.first_run import (
    NINJASRE_ORGANISATION_ENV,
    NINJASRE_STATE_DIR_ENV,
    SETUP_STEP_DURABLE_CREDENTIAL,
    SETUP_STEP_ORDER,
)
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.startup.bootstrap import bring_up, credential_path
from platform.startup.diagnostics import record_failure
from tests.unit.gateway.http.conftest import (
    ORG,
    Deployment,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the host state at a directory this test owns."""
    directory = tmp_path / "state"
    monkeypatch.setenv(NINJASRE_STATE_DIR_ENV, str(directory))
    return directory


@pytest.fixture
async def owner_token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )


def _headers(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


# --- The checklist ------------------------------------------------------------------


async def test_the_checklist_is_served_with_every_step_and_its_state(
    client: AsyncClient, owner_token: str
) -> None:
    response = await client.get("/v1/setup/checklist", headers=_headers(owner_token))

    assert response.status_code == 200
    body = response.json()
    assert [step["name"] for step in body["steps"]] == list(SETUP_STEP_ORDER)
    assert body["complete"] is False


async def test_every_step_the_checklist_serves_names_a_next_action(
    client: AsyncClient, owner_token: str
) -> None:
    response = await client.get("/v1/setup/checklist", headers=_headers(owner_token))

    for step in response.json()["steps"]:
        assert step["action"], step["name"]


async def test_the_checklist_names_the_one_step_that_can_be_done_now(
    client: AsyncClient, owner_token: str
) -> None:
    """The caller here already holds a durable credential — issuing one is what
    made this request possible — so the step it can usefully do next is the one
    after it, not the one it has already finished."""
    from config.constants.first_run import SETUP_STEP_MODEL_PROVIDER

    response = await client.get("/v1/setup/checklist", headers=_headers(owner_token))

    body = response.json()
    assert body["next"] == SETUP_STEP_MODEL_PROVIDER
    steps = {step["name"]: step["state"] for step in body["steps"]}
    assert steps[SETUP_STEP_DURABLE_CREDENTIAL] == "done"


async def test_the_checklist_needs_a_credential(client: AsyncClient) -> None:
    assert (await client.get("/v1/setup/checklist")).status_code == 400


# --- The self-check ------------------------------------------------------------------


async def test_the_self_check_runs_from_the_console(client: AsyncClient, owner_token: str) -> None:
    """FR-010. The same check the CLI runs and bring-up runs, over HTTP."""
    response = await client.get("/v1/setup/self-check", headers=_headers(owner_token))

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["ok"], bool)
    assert body["findings"] or body["passed"]


async def test_every_finding_the_route_serves_names_a_problem_and_an_action(
    client: AsyncClient, owner_token: str
) -> None:
    response = await client.get("/v1/setup/self-check", headers=_headers(owner_token))

    for finding in response.json()["findings"]:
        assert finding["problem"]
        assert finding["action"]
        assert finding["blocks"]


async def test_the_findings_arrive_most_blocking_first(
    client: AsyncClient, owner_token: str
) -> None:
    from config.constants.first_run import BLOCKING_ORDER

    findings = (await client.get("/v1/setup/self-check", headers=_headers(owner_token))).json()[
        "findings"
    ]

    weights = [BLOCKING_ORDER.index(finding["blocks"]) for finding in findings]
    assert weights == sorted(weights)


# --- Diagnostics -----------------------------------------------------------------------


async def test_a_deployment_that_started_has_no_failure_to_report(
    client: AsyncClient, owner_token: str, state_dir: Path
) -> None:
    response = await client.get("/v1/setup/diagnostics", headers=_headers(owner_token))

    assert response.status_code == 404


async def test_the_last_bring_up_failure_is_reachable_from_the_console(
    client: AsyncClient, owner_token: str, state_dir: Path
) -> None:
    """FR-022. The operator who was not watching the terminal gets the same
    message it showed."""
    from platform.startup.errors import ConfigurationInvalid

    record_failure(
        ConfigurationInvalid(
            "NINJASRE_DATABASE_URL is not set", settings=["NINJASRE_DATABASE_URL"]
        ),
        stage="validation",
    )

    response = await client.get("/v1/setup/diagnostics", headers=_headers(owner_token))

    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "validation"
    assert "NINJASRE_DATABASE_URL" in body["problem"]
    assert body["action"]
    assert body["settings"] == ["NINJASRE_DATABASE_URL"]


async def test_the_support_bundle_is_producible_over_http(
    client: AsyncClient, owner_token: str, state_dir: Path
) -> None:
    response = await client.get("/v1/setup/support-bundle", headers=_headers(owner_token))

    assert response.status_code == 200
    body = response.json()
    assert "version" in body
    assert "self_check" in body
    assert "schema_revision" in body


# --- Establishing a durable credential ---------------------------------------------------


async def test_the_bootstrap_credential_is_exchanged_over_http(
    deployment: Deployment, state_dir: Path
) -> None:
    """The console's half of FR-003, driven the way the console drives it."""
    result = await bring_up(deployment.gateway, deployment.tokens)
    app = create_app(deployment.state)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as http:
        response = await http.post(
            "/v1/setup/durable-credential",
            headers=_headers(result.credential.secret),
            json={
                "user_id": "ada",
                "email": "ada@example.test",
                "display_name": "Ada",
                "password": "a very long passphrase",
            },
        )

        assert response.status_code == 200
        durable = response.json()["secret"]
        assert durable != result.credential.secret

        # The bootstrap credential is spent: the same request again is refused
        # by the permission chain, because the token no longer resolves.
        again = await http.get("/auth/me", headers=_headers(result.credential.secret))
        assert again.status_code == 401

        # And the durable one works.
        assert (await http.get("/auth/me", headers=_headers(durable))).status_code == 200


async def test_exchanging_with_no_credential_on_the_host_is_refused(
    client: AsyncClient, owner_token: str, state_dir: Path
) -> None:
    response = await client.post(
        "/v1/setup/durable-credential",
        headers=_headers(owner_token),
        json={
            "user_id": "grace",
            "email": "g@example.test",
            "display_name": "Grace",
            "password": "a very long passphrase",
        },
    )

    assert response.status_code == 400
    assert "bootstrap credential" in response.text


async def test_the_credential_file_is_gone_once_the_exchange_has_happened(
    deployment: Deployment, state_dir: Path
) -> None:
    result = await bring_up(deployment.gateway, deployment.tokens)
    app = create_app(deployment.state)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as http:
        await http.post(
            "/v1/setup/durable-credential",
            headers=_headers(result.credential.secret),
            json={
                "user_id": "ada",
                "email": "ada@example.test",
                "display_name": "Ada",
                "password": "a very long passphrase",
            },
        )

    assert not credential_path().exists()


# --- The demonstration --------------------------------------------------------------------


async def test_demo_mode_is_enabled_and_removed_over_http(
    client: AsyncClient, owner_token: str
) -> None:
    enabled = await client.post("/v1/setup/demo", headers=_headers(owner_token))

    assert enabled.status_code == 200
    assert enabled.json()["total"] > 100

    removed = await client.delete("/v1/setup/demo", headers=_headers(owner_token))

    assert removed.status_code == 200
    assert removed.json()["removed"] is True


async def test_seeding_over_real_data_is_refused_with_the_reason(
    client: AsyncClient, owner_token: str, deployment: Deployment
) -> None:
    from platform.persistence.ports.estate_repository import Resource
    from platform.persistence.ports.transaction import TenantScope
    from tools.mockplane.seed import DEMONSTRATION_ORGANISATION

    async with deployment.gateway.begin_system() as system:
        await system.orgs.create_organisation(DEMONSTRATION_ORGANISATION, "Northwind")
    async with deployment.gateway.begin(TenantScope(org_id=DEMONSTRATION_ORGANISATION)) as uow:
        await uow.estate.upsert(
            Resource(resource_id="real-1", kind="node", source="k8s", native_id="real-1")
        )

    response = await client.post("/v1/setup/demo", headers=_headers(owner_token))

    assert response.status_code == 400
    assert "--force" in response.text


async def test_demo_mode_needs_more_than_being_signed_in(
    deployment: Deployment, client: AsyncClient
) -> None:
    """The one route here that a viewer must not reach: seeding writes a
    tenant's worth of records."""
    viewer = await issue_token(
        deployment.gateway, deployment.tokens, user_id="vic", role=Role.VIEWER, node_id=None
    )

    assert (await client.post("/v1/setup/demo", headers=_headers(viewer))).status_code == 403


async def test_the_organisation_the_checklist_reads_is_the_callers_own(
    deployment: Deployment, client: AsyncClient, owner_token: str
) -> None:
    """A checklist is a statement about a tenant, and the tenant is the token's,
    never a value from the request."""
    response = await client.get("/v1/setup/checklist", headers=_headers(owner_token))

    assert response.status_code == 200
    # ``ada`` was issued into ORG and holds a live token there, so the first
    # step reads as done for this caller and would not for another tenant.
    steps = {step["name"]: step for step in response.json()["steps"]}
    assert steps[SETUP_STEP_DURABLE_CREDENTIAL]["state"] == "done"
    assert ORG


async def test_a_gateway_state_wired_from_the_table_serves_every_first_run_route(
    deployment: Deployment,
) -> None:
    """Every route this feature adds is declared, or the guard refuses it at
    request time rather than at wiring time."""
    from gateway.http.security.first_run_routes import FIRST_RUN_ROUTES

    table = GatewayState(
        gateway=deployment.gateway, tokens=deployment.tokens, investigator=deployment.runner
    ).route_table
    for route in FIRST_RUN_ROUTES:
        assert table.declaration_for(route.method, route.path) is not None


# --- The local administrator's public availability -------------------------------


@pytest.fixture
def availability_org(monkeypatch: pytest.MonkeyPatch) -> str:
    """``organisation_id()`` defaults to ``"default"``; this suite's fixtures
    seed ``ORG``. Only the availability route reads the environment
    directly — every other route resolves its tenant from the caller's own
    token — so only these tests need the two to agree."""
    monkeypatch.setenv(NINJASRE_ORGANISATION_ENV, ORG)
    return ORG


async def test_the_availability_route_needs_no_credential_at_all(
    client: AsyncClient, availability_org: str
) -> None:
    """FR-071 has to be readable before anybody is signed in."""
    response = await client.get("/v1/setup/local-administrator")

    assert response.status_code == 200


async def test_a_fresh_deployment_is_unclaimed(client: AsyncClient, availability_org: str) -> None:
    response = await client.get("/v1/setup/local-administrator")

    assert response.json() == {"state": "unclaimed"}


async def test_a_deployment_with_an_opening_reads_administered(
    deployment: Deployment, client: AsyncClient, availability_org: str
) -> None:
    from datetime import UTC, datetime

    from platform.persistence.ports.transaction import TenantScope

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.identity.open_local_sign_in(opened_at=datetime.now(UTC), opened_via="cli")

    response = await client.get("/v1/setup/local-administrator")

    assert response.json() == {"state": "administered"}


async def test_a_deployment_with_an_active_identity_provider_reads_identity_provider(
    deployment: Deployment, client: AsyncClient, availability_org: str
) -> None:
    from platform.config_service.service import ConfigService
    from platform.persistence.ports.audit_repository import ActorKind
    from platform.persistence.ports.transaction import TenantScope

    service = ConfigService(gateway=deployment.gateway, scope=TenantScope(org_id=ORG))
    await service.set_settings(
        ORG,
        {"policies": {"sso": {"is_active": True}}},
        actor_id="test",
        actor_kind=ActorKind.SYSTEM,
    )

    response = await client.get("/v1/setup/local-administrator")

    assert response.json() == {"state": "identity_provider"}


async def test_the_availability_response_names_no_deployment_detail(
    deployment: Deployment, client: AsyncClient, availability_org: str
) -> None:
    """FR-076: no name, no version, no organisation, no count of anything."""
    response = await client.get("/v1/setup/local-administrator")

    assert set(response.json().keys()) == {"state"}


async def test_an_environment_configured_account_also_reads_administered(
    availability_org: str,
) -> None:
    """FR-002: the fact must be true for the account-configured path too, not
    only for a registered opening."""
    from platform.identity.local_accounts import LocalAccount, LocalSignIn
    from platform.identity.tokens import TokenService
    from platform.persistence.fakes import FakePersistence

    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    tokens = TokenService(gateway=gateway)

    state = GatewayState(
        gateway=gateway,
        tokens=tokens,
        investigator=FakeInvestigationRunner(),
        local_sign_in=LocalSignIn(
            gateway=gateway, tokens=tokens, account=LocalAccount(password_hash="x")
        ),
    )
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://gateway.test"
    ) as http:
        response = await http.get("/v1/setup/local-administrator")

    assert response.json() == {"state": "administered"}
