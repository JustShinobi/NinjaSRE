"""Which team's handle an integration resolves to — one function, three callers.

Verification and tool binding used to answer this question two different,
disagreeing ways: a caller's own team for an authenticated HTTP request, and
the literal organisation-wide handle, unconditionally, for a tool binding or
a provider lease composed with no caller in sight. A credential stored under
a team's own handle was invisible to every investigation that team started,
because nothing at composition time ever asked the vault which team actually
held it — it only ever asked for the organisation's.

``resolve_credential_handle`` is the one path both questions go through now.
A caller with a team of its own gets that team back, unconditionally and
without touching the vault — this is what a verification is, and it has to
keep meaning exactly what it already meant. A caller with none — a
composition root, with no HTTP request behind it — gets the team that
actually holds a credential for the integration, discovered from the vault's
own metadata, never a value.
"""

from __future__ import annotations

import pytest

from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from gateway.http.credential_handles import ResolvedHandle, resolve_credential_handle
from platform.credentials.handles import CredentialHandle
from platform.credentials.schemas import CredentialField, CredentialSchema, CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.fakes.gateway import FakePersistence
from platform.persistence.ports import TenantScope

pytestmark = pytest.mark.unit

ORG_ID = "acme"
INTEGRATION = "datadog"
OTHER_INTEGRATION = "pagerduty"
TEAM_PAYMENTS = "payments"
TEAM_SEARCH = "search"

SCOPE = TenantScope(org_id=ORG_ID)


def _schema(integration: str) -> CredentialSchema:
    return CredentialSchema(
        integration=integration,
        fields=(CredentialField(name="api_key", description="The key."),),
    )


async def _organisation() -> FakePersistence:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")
    return gateway


async def _stored_under(gateway: FakePersistence, *, integration: str, team_id: str) -> None:
    """Store a credential for ``integration`` under ``team_id``, values aside."""
    vault = Vault(
        gateway=gateway, schemas=CredentialSchemaRegistry.from_schemas(_schema(integration))
    )
    handle = CredentialHandle(integration=integration, team_id=team_id)
    await vault.store(SCOPE, handle, {"api_key": "does-not-matter-for-this-test"})


# --- T014: a team that holds one, and nobody holding one at all ----------------


async def test_a_credential_stored_under_one_team_resolves_to_that_team() -> None:
    gateway = await _organisation()
    await _stored_under(gateway, integration=INTEGRATION, team_id=TEAM_PAYMENTS)

    resolved = await resolve_credential_handle(gateway, SCOPE, integration=INTEGRATION)

    assert resolved == ResolvedHandle(integration=INTEGRATION, team_id=TEAM_PAYMENTS)
    assert not resolved.is_ambiguous


async def test_nobody_holding_one_by_team_resolves_to_the_organisation() -> None:
    gateway = await _organisation()
    # Nothing stored at all for this integration.

    resolved = await resolve_credential_handle(gateway, SCOPE, integration=INTEGRATION)

    assert resolved == ResolvedHandle(integration=INTEGRATION, team_id=CREDENTIAL_ORG_WIDE_TEAM)
    assert not resolved.is_ambiguous


async def test_a_credential_stored_only_at_the_organisation_handle_still_resolves_there() -> None:
    gateway = await _organisation()
    await _stored_under(gateway, integration=INTEGRATION, team_id=CREDENTIAL_ORG_WIDE_TEAM)

    resolved = await resolve_credential_handle(gateway, SCOPE, integration=INTEGRATION)

    assert resolved.team_id == CREDENTIAL_ORG_WIDE_TEAM
    assert not resolved.is_ambiguous


# --- T015: two teams, the same integration --------------------------------------


async def test_two_teams_holding_the_same_integration_resolve_organisation_wide_and_ambiguous() -> (
    None
):
    gateway = await _organisation()
    await _stored_under(gateway, integration=INTEGRATION, team_id=TEAM_PAYMENTS)
    await _stored_under(gateway, integration=INTEGRATION, team_id=TEAM_SEARCH)

    resolved = await resolve_credential_handle(gateway, SCOPE, integration=INTEGRATION)

    assert resolved.team_id == CREDENTIAL_ORG_WIDE_TEAM
    assert resolved.is_ambiguous
    assert resolved.ambiguous_teams == (TEAM_PAYMENTS, TEAM_SEARCH)


async def test_the_ambiguity_names_the_integration_it_belongs_to() -> None:
    gateway = await _organisation()
    await _stored_under(gateway, integration=INTEGRATION, team_id=TEAM_PAYMENTS)
    await _stored_under(gateway, integration=INTEGRATION, team_id=TEAM_SEARCH)

    resolved = await resolve_credential_handle(gateway, SCOPE, integration=INTEGRATION)

    assert resolved.integration == INTEGRATION


async def test_two_teams_on_different_integrations_is_not_ambiguous_for_either() -> None:
    """Ambiguity is per integration — a second team elsewhere is not this integration's problem."""
    gateway = await _organisation()
    await _stored_under(gateway, integration=INTEGRATION, team_id=TEAM_PAYMENTS)
    await _stored_under(gateway, integration=OTHER_INTEGRATION, team_id=TEAM_SEARCH)

    datadog = await resolve_credential_handle(gateway, SCOPE, integration=INTEGRATION)
    pagerduty = await resolve_credential_handle(gateway, SCOPE, integration=OTHER_INTEGRATION)

    assert datadog == ResolvedHandle(integration=INTEGRATION, team_id=TEAM_PAYMENTS)
    assert pagerduty == ResolvedHandle(integration=OTHER_INTEGRATION, team_id=TEAM_SEARCH)


# --- The verification fast path: a caller's own team, no vault read ------------


async def test_a_preferred_team_is_returned_outright_without_reading_the_vault() -> None:
    # A gateway for an organisation that was never created: any attempt to open
    # a transaction against it raises. The preferred-team path must never try.
    gateway = FakePersistence()
    unknown_org_scope = TenantScope(org_id="an-organisation-nobody-created")

    resolved = await resolve_credential_handle(
        gateway, unknown_org_scope, integration=INTEGRATION, preferred_team=TEAM_PAYMENTS
    )

    assert resolved == ResolvedHandle(integration=INTEGRATION, team_id=TEAM_PAYMENTS)


async def test_a_caller_with_no_team_of_its_own_prefers_the_organisation() -> None:
    gateway = FakePersistence()
    unknown_org_scope = TenantScope(org_id="an-organisation-nobody-created")

    resolved = await resolve_credential_handle(
        gateway, unknown_org_scope, integration=INTEGRATION, preferred_team=""
    )

    assert resolved.team_id == CREDENTIAL_ORG_WIDE_TEAM
    assert not resolved.is_ambiguous


# --- T016: verification and discovery agree, walking a small catalogue ---------


@pytest.mark.parametrize(
    ("integration", "holder"),
    [
        (INTEGRATION, TEAM_PAYMENTS),
        (OTHER_INTEGRATION, TEAM_SEARCH),
        ("no-credential-anywhere", None),
    ],
)
async def test_verification_and_discovery_name_the_same_handle_across_the_catalogue(
    integration: str, holder: str | None
) -> None:
    """The invariant the plan states: for every integration, the handle
    verification resolves is the handle the tool binding resolves.

    Exercised as the two call shapes this function actually has: a
    verification asking as the team that holds the credential (``preferred_
    team``), and a composition root discovering it from the vault with no
    caller at all. Before this function existed, one of the two was always
    ``CREDENTIAL_ORG_WIDE_TEAM`` regardless of who actually held the key.
    """
    gateway = await _organisation()
    if holder is not None:
        await _stored_under(gateway, integration=integration, team_id=holder)

    verification = await resolve_credential_handle(
        gateway, SCOPE, integration=integration, preferred_team=holder or ""
    )
    binding = await resolve_credential_handle(gateway, SCOPE, integration=integration)

    assert verification.team_id == binding.team_id
    expected = holder if holder is not None else CREDENTIAL_ORG_WIDE_TEAM
    assert verification.team_id == expected
