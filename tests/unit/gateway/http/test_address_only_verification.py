"""Testing a vendor that needs no credential must not report a failure.

Alertmanager, Prometheus and Loki ship no authentication of their own. This
deployment reaches them by being told where they are, and nothing is written to
the vault. The write route already knows that — it answers "configured" for an
address-only save — and the verify route beside it did not: it asked the vault
"is a credential present", got the honest "no", and reported it as a failure.

The failure was then *written down*. ``record_check`` persisted it, the
catalogue read it back on the next load, and the card an operator had just
connected went red. So "Save and test" was green and "Test again", with nothing
changed in between, was red — which is the whole reason this file exists.

What must not happen alongside the fix is a blanket amnesty. The relaxation is
for absence, and only where an address makes the vendor reachable: a vendor
nobody has configured is still missing, a required credential that is missing is
still missing, and a stored credential that has expired is still expired.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from gateway.http.credential_state import credential_detail, effective_credential_state
from integrations._base.schema import credential_schema, endpoint, secret
from platform.credentials.health import CredentialHealthState
from platform.credentials.schemas import CredentialSchema
from platform.identity.permissions import Role
from platform.persistence.ports.transaction import TenantScope
from platform.persistence.ports.verification_ledger import (
    VerificationOutcome,
    VerificationRecord,
    VerificationSubject,
)
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

#: The staging Alertmanager this defect was found against.
ADDRESS = "http://10.20.20.36:9093"


def _headers(secret_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret_token}"}


@pytest.fixture
async def operator_token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


async def _recorded(deployment: Deployment, *, subject: str) -> VerificationRecord | None:
    """Return what the ledger holds about one integration, read from the store."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        return await uow.verifications.latest(kind=VerificationSubject.INTEGRATION, subject=subject)


async def _address(client: AsyncClient, token: str, *, integration: str) -> None:
    """Point ``integration`` at a real address through the real route."""
    written = await client.put(
        f"/v1/integrations/{integration}/credential",
        json={"values": {"endpoint": ADDRESS}},
        headers=_headers(token),
    )
    assert written.status_code == 200, written.text


# -- the route -----------------------------------------------------------------


async def test_testing_an_address_only_vendor_reports_it_configured(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    await _address(client, operator_token, integration="alertmanager")

    answer = await client.post(
        "/v1/integrations/alertmanager/verify", headers=_headers(operator_token)
    )

    assert answer.status_code == 200, answer.text
    assert answer.json() == {
        "integration": "alertmanager",
        "state": CredentialHealthState.CONFIGURED.value,
        "usable": True,
    }


async def test_the_ledger_records_a_pass_and_says_why(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """A row is written rather than skipped: skipping would leave the card at
    ``unknown`` for ever, which is exactly what the verify route exists to move
    off."""
    await _address(client, operator_token, integration="alertmanager")
    await client.post("/v1/integrations/alertmanager/verify", headers=_headers(operator_token))

    row = await _recorded(deployment, subject="alertmanager")

    assert row is not None
    assert row.outcome is VerificationOutcome.PASSED
    assert "no credential is stored" not in row.detail


async def test_the_card_survives_a_reload(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """The regression as an operator met it: green on save, red after pressing
    the button beside it, and red for good once the ledger held the failure."""
    await _address(client, operator_token, integration="alertmanager")
    await client.post("/v1/integrations/alertmanager/verify", headers=_headers(operator_token))

    listing = await client.get("/v1/integrations", headers=_headers(operator_token))

    entries = {entry["name"]: entry for entry in listing.json()["integrations"]}
    assert entries["alertmanager"]["health"] == "healthy"


async def test_a_vendor_nobody_pointed_anywhere_is_still_missing(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    """The guard. Alertmanager needs no credential, but a deployment that has
    not been told where it is has nothing to reach — reporting that configured
    would be the same lie in the other direction."""
    answer = await client.post("/v1/integrations/loki/verify", headers=_headers(operator_token))

    assert answer.status_code == 200, answer.text
    assert answer.json()["state"] == CredentialHealthState.MISSING.value
    assert answer.json()["usable"] is False

    row = await _recorded(deployment, subject="loki")
    assert row is not None
    assert row.outcome is VerificationOutcome.FAILED


async def test_a_vendor_that_requires_a_credential_still_fails_without_one(
    client: AsyncClient, deployment: Deployment, operator_token: str
) -> None:
    answer = await client.post("/v1/integrations/redis/verify", headers=_headers(operator_token))

    assert answer.json()["state"] == CredentialHealthState.MISSING.value
    assert answer.json()["usable"] is False

    row = await _recorded(deployment, subject="redis")
    assert row is not None
    assert row.outcome is VerificationOutcome.FAILED


# -- the rule itself ------------------------------------------------------------

#: A vendor shaped like Alertmanager: an address it must be told, and a token
#: only a reverse proxy in front of it would need.
_OPTIONAL = credential_schema(
    "alertmanager",
    endpoint("endpoint", "where your Alertmanager is"),
    secret("token", "only if a proxy fronts it", required=False, min_length=8),
)

#: A vendor that declares an address and nothing else at all, so ``for_vault``
#: answers ``None``. Nothing is shaped this way today, and the fallback to the
#: whole schema would silently stop the rule from firing when one is.
_ADDRESS_ONLY = credential_schema(
    "somewhere",
    endpoint("endpoint", "where it is"),
)

#: A vendor whose credential is the point.
_REQUIRED = credential_schema(
    "redis",
    secret("api_key", "the key", min_length=8),
)


@pytest.mark.parametrize("schema", [_OPTIONAL, _ADDRESS_ONLY])
def test_absence_is_relaxed_for_a_vendor_that_needs_nothing_and_has_an_address(
    schema: CredentialSchema,
) -> None:
    assert (
        effective_credential_state(CredentialHealthState.MISSING, schema=schema, addressed=True)
        is CredentialHealthState.CONFIGURED
    )


@pytest.mark.parametrize("schema", [_OPTIONAL, _ADDRESS_ONLY])
def test_absence_is_not_relaxed_without_an_address(schema: CredentialSchema) -> None:
    assert (
        effective_credential_state(CredentialHealthState.MISSING, schema=schema, addressed=False)
        is CredentialHealthState.MISSING
    )


def test_absence_is_not_relaxed_where_the_credential_is_required() -> None:
    assert (
        effective_credential_state(CredentialHealthState.MISSING, schema=_REQUIRED, addressed=True)
        is CredentialHealthState.MISSING
    )


@pytest.mark.parametrize(
    "stored",
    [CredentialHealthState.EXPIRED, CredentialHealthState.UNDECRYPTABLE],
)
def test_a_credential_that_is_present_and_unusable_is_left_alone(
    stored: CredentialHealthState,
) -> None:
    """The rule is about absence. A token that expired is a token to replace,
    and calling it configured would hide the one state an operator must act on."""
    assert effective_credential_state(stored, schema=_OPTIONAL, addressed=True) is stored


def test_the_sentence_says_the_address_is_the_configuration() -> None:
    said = credential_detail(CredentialHealthState.CONFIGURED, address_only=True)

    assert "credential" in said
    assert "address" in said
    assert "no credential is stored" not in said
