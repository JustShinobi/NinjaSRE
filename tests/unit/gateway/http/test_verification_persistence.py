"""A check that passed stays passed after the page is reloaded.

The defect this exercises was not subtle and was not survivable from a console:
the first run's "check that each of them works" step went green while the tab
was open and reverted to "nobody has checked this one" on refresh, because the
answer lived in the process that produced it. The step was therefore
uncompletable, and so was the checklist it belongs to.

Every test here drives the real routes through the real guard, and then reads
the store directly — because the claim being made is about what was written
down, and a second call to the same route would prove only that the route is
deterministic.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.llm.verification import ModelVerdict
from platform.identity.permissions import Role
from platform.persistence.ports.transaction import TenantScope
from platform.persistence.ports.verification_ledger import (
    VerificationRecord,
    VerificationSubject,
)
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit


def _headers(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
async def operator_token(deployment: Deployment) -> str:
    """A token that may write credentials and ask for a verification."""
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


#: What each thing under test calls its one credential field. Spelled out rather
#: than discovered, so a schema change breaks this file loudly instead of making
#: every test here silently exercise a refusal.
_FIELDS = {"prometheus": "token", "google_gemini": "api_key"}

#: Where each self-hosted thing under test is, for the schemas that ask. Spelled
#: out for the same reason the field names above are: a vendor that gains an
#: address field should break this file rather than quietly start refusing every
#: write it makes.
_ADDRESSES = {"prometheus": "https://prometheus.example.invalid"}


async def _store_credential(client: AsyncClient, token: str, *, integration: str) -> None:
    """Put a credential in the vault through the real route."""
    values = {_FIELDS[integration]: "0f1e2d3c4b5a69788796a5b4c3d2e1f0"}
    if integration in _ADDRESSES:
        values["endpoint"] = _ADDRESSES[integration]
    response = await client.put(
        f"/v1/integrations/{integration}/credential",
        json={"values": values},
        headers=_headers(token),
    )
    assert response.status_code == 200, response.text


async def _recorded(
    deployment: Deployment, *, kind: VerificationSubject, subject: str
) -> VerificationRecord | None:
    """Return what the ledger holds about one thing, read straight from the store."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        return await uow.verifications.latest(kind=kind, subject=subject)


# --- An integration's check --------------------------------------------------------


async def test_a_passing_integration_check_is_written_down(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """The one that matters: the answer outlives the request that produced it."""
    await _store_credential(client, operator_token, integration="prometheus")

    response = await client.post(
        "/v1/integrations/prometheus/verify", headers=_headers(operator_token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["usable"] is True

    held = await _recorded(deployment, kind=VerificationSubject.INTEGRATION, subject="prometheus")
    assert held is not None
    assert held.verified
    assert held.checked_by == "ada"
    assert held.team_node_id == TEAM_PAYMENTS
    assert held.detail


async def test_a_failing_integration_check_is_written_down_too(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """ "Nobody checked" and "checked, and it failed" are different screens."""
    response = await client.post(
        "/v1/integrations/prometheus/verify", headers=_headers(operator_token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["usable"] is False

    held = await _recorded(deployment, kind=VerificationSubject.INTEGRATION, subject="prometheus")
    assert held is not None
    assert not held.verified
    assert held.detail


async def test_the_checklist_reports_an_integration_a_check_reached(
    client: AsyncClient, operator_token: str
) -> None:
    """The step this whole port exists for: green, and still green on the next request."""
    await _store_credential(client, operator_token, integration="prometheus")
    await client.post("/v1/integrations/prometheus/verify", headers=_headers(operator_token))

    response = await client.get("/v1/setup/checklist", headers=_headers(operator_token))

    assert response.status_code == 200, response.text
    readiness = {entry["name"]: entry["readiness"] for entry in response.json()["integrations"]}
    assert readiness["prometheus"] == "verified"


async def test_the_catalogue_reports_an_integration_a_check_reached(
    client: AsyncClient, operator_token: str
) -> None:
    """The same fact, on the screen an operator actually reads it from."""
    await _store_credential(client, operator_token, integration="prometheus")
    await client.post("/v1/integrations/prometheus/verify", headers=_headers(operator_token))

    response = await client.get("/v1/integrations", headers=_headers(operator_token))

    assert response.status_code == 200, response.text
    entries = {entry["name"]: entry for entry in response.json()["integrations"]}
    assert entries["prometheus"]["health"] == "healthy"


async def test_a_configured_integration_nobody_checked_stays_unknown(
    client: AsyncClient, operator_token: str
) -> None:
    """A ledger that answered for everything would report a guess as a measurement.

    Configured first, so this is genuinely the "connected but unchecked" case
    the ledger is being asked not to guess about — not the "nothing is
    connected here" case, which is a different, more basic fact and reads as
    ``unconfigured`` rather than ``unknown``.
    """
    await _store_credential(client, operator_token, integration="prometheus")

    response = await client.get("/v1/integrations", headers=_headers(operator_token))

    entries = {entry["name"]: entry for entry in response.json()["integrations"]}
    assert entries["prometheus"]["health"] == "unknown"


async def test_an_integration_nobody_has_connected_reads_unconfigured_not_unknown(
    client: AsyncClient, operator_token: str
) -> None:
    """The other half of the same distinction: nothing stored is not "unknown"."""
    response = await client.get("/v1/integrations", headers=_headers(operator_token))

    entries = {entry["name"]: entry for entry in response.json()["integrations"]}
    assert entries["prometheus"]["health"] == "unconfigured"


# --- Replacing the credential ------------------------------------------------------


async def test_replacing_the_credential_forgets_the_verdict(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """A green tick earned by the old key says nothing about the new one."""
    await _store_credential(client, operator_token, integration="prometheus")
    await client.post("/v1/integrations/prometheus/verify", headers=_headers(operator_token))

    await _store_credential(client, operator_token, integration="prometheus")

    held = await _recorded(deployment, kind=VerificationSubject.INTEGRATION, subject="prometheus")
    assert held is None


# --- A provider's check ------------------------------------------------------------


async def test_a_provider_check_records_the_model_it_exercised(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """Verifying the registry default and verifying the configured model are different claims."""

    async def verifier(provider_id: str, model_id: str | None) -> ModelVerdict:
        return ModelVerdict(
            provider_id=provider_id,
            model_id=model_id or "gemini-2.5-flash",
            satisfied=True,
            summary_line="gemini-2.5-flash called a tool and returned structure",
        )

    deployment.state.model_verifier = verifier

    response = await client.post(
        "/v1/providers/google_gemini/verify", headers=_headers(operator_token)
    )

    assert response.status_code == 200, response.text

    held = await _recorded(
        deployment, kind=VerificationSubject.MODEL_PROVIDER, subject="google_gemini"
    )
    assert held is not None
    assert held.verified
    assert held.model_id == "gemini-2.5-flash"


async def test_the_provider_listing_reports_what_a_check_found(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """The listing stops saying "nobody has checked" once somebody has."""

    async def verifier(provider_id: str, model_id: str | None) -> ModelVerdict:
        return ModelVerdict(
            provider_id=provider_id,
            model_id="gemini-2.5-flash",
            satisfied=True,
            summary_line="gemini-2.5-flash called a tool and returned structure",
        )

    deployment.state.model_verifier = verifier
    await client.post("/v1/providers/google_gemini/verify", headers=_headers(operator_token))

    response = await client.get("/v1/providers", headers=_headers(operator_token))

    assert response.status_code == 200, response.text
    rows = {row["provider_id"]: row for row in response.json()["providers"]}
    assert rows["google_gemini"]["verified"] is True
    assert "gemini-2.5-flash" in rows["google_gemini"]["detail"]


async def test_a_provider_nobody_checked_says_so_rather_than_failing(
    client: AsyncClient, operator_token: str
) -> None:
    """The middle state has to stay sayable: unchecked is not the same as broken."""
    await _store_credential(client, operator_token, integration="google_gemini")

    response = await client.get("/v1/providers", headers=_headers(operator_token))

    rows = {row["provider_id"]: row for row in response.json()["providers"]}
    assert rows["google_gemini"]["verified"] is False
    assert "no verification has been run" in rows["google_gemini"]["detail"]
    assert rows["google_gemini"]["readiness"] == "configured"


async def test_the_provider_listing_carries_the_same_readiness_word_the_checklist_does(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """FR-003: one record, read by two routes, has to produce one word."""

    async def verifier(provider_id: str, model_id: str | None) -> ModelVerdict:
        return ModelVerdict(
            provider_id=provider_id,
            model_id="gemini-2.5-flash",
            satisfied=True,
            summary_line="gemini-2.5-flash called a tool and returned structure",
        )

    deployment.state.model_verifier = verifier
    await client.post("/v1/providers/google_gemini/verify", headers=_headers(operator_token))

    listing = await client.get("/v1/providers", headers=_headers(operator_token))
    checklist = await client.get("/v1/setup/checklist", headers=_headers(operator_token))

    row = {r["provider_id"]: r for r in listing.json()["providers"]}["google_gemini"]
    assert row["readiness"] == "verified"
    assert row["readiness"] == checklist.json()["provider"]


async def test_a_provider_whose_last_check_failed_reads_as_failing_not_configured(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """The listing must not read the same for a broken key as for an unchecked one."""

    async def verifier(provider_id: str, model_id: str | None) -> ModelVerdict:
        return ModelVerdict(
            provider_id=provider_id,
            model_id="gemini-2.5-flash",
            satisfied=False,
            limitation="gemini-2.5-flash did not call the tool it was given",
            remedy="choose a model that supports tool calling",
        )

    deployment.state.model_verifier = verifier
    await client.post("/v1/providers/google_gemini/verify", headers=_headers(operator_token))

    response = await client.get("/v1/providers", headers=_headers(operator_token))

    row = {r["provider_id"]: r for r in response.json()["providers"]}["google_gemini"]
    assert row["verified"] is False
    assert row["readiness"] == "failing"


# --- Where the vault holds it ------------------------------------------------------


async def test_the_check_is_recorded_against_the_organisation_not_the_team(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """ "Has anybody got this working" is the question, and it is not per team."""
    await _store_credential(client, operator_token, integration="prometheus")
    await client.post("/v1/integrations/prometheus/verify", headers=_headers(operator_token))

    other = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="grace",
        role=Role.OPERATOR,
        node_id="platform",
    )
    response = await client.get("/v1/setup/checklist", headers=_headers(other))

    readiness = {entry["name"]: entry["readiness"] for entry in response.json()["integrations"]}
    assert readiness["prometheus"] == "verified"
