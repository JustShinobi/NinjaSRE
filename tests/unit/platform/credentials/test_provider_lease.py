"""The model provider's own key, taken out of the environment and put in the vault.

``core.llm`` resolves every provider credential through ``CredentialResolver``,
a synchronous port, and vault resolution is asynchronous — so the vault cannot
be a drop-in implementation of it. It does not need to be. The port has a
second implementation, ``StaticCredentialResolver``, whose docstring already
names this caller: *"for a caller that already holds a vault lease"*. This is
the code that holds one.

The lease is taken in ``platform/credentials/proxy/``, which is where
``reveal`` is allowed to be called from, and handed down to ``core.llm``
already resolved. Nothing in ``core.llm`` learns a new import and nothing above
the proxy tier gains the ability to read a credential.
"""

from __future__ import annotations

import pytest

from config.constants.llm import PROVIDER_ANTHROPIC, PROVIDER_OPENAI
from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM
from core.llm.onboarding import credential_schema_for
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.llm import provider_lease
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

pytestmark = pytest.mark.unit

ORG_ID = "acme"
TEAM_ID = "payments"

#: Not a real key, and shaped so a leak into an assertion message is obvious.
STORED_KEY = "sk-ant-stored-in-the-vault-not-the-environment"


async def _vault_with(*, values: dict[str, str] | None = None, team_id: str = TEAM_ID):
    """Return a resolver over a fake datastore holding one Anthropic credential."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    schemas = CredentialSchemaRegistry.from_schemas(
        credential_schema_for(PROVIDER_ANTHROPIC),
        credential_schema_for(PROVIDER_OPENAI),
    )
    if values is not None:
        await Vault(gateway=gateway, schemas=schemas).store(
            TenantScope(org_id=ORG_ID, team_node_id=team_id),
            CredentialHandle(integration=PROVIDER_ANTHROPIC, team_id=team_id),
            values,
        )
    return CredentialResolver(gateway=gateway, schemas=schemas)


async def test_a_key_stored_in_the_vault_reaches_the_provider_adapter() -> None:
    """The whole point: an operator who typed a key at first run gets it used."""
    resolver = await _vault_with(values={"api_key": STORED_KEY})

    lease = await provider_lease(
        resolver,
        TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID),
        team_id=TEAM_ID,
        providers=(PROVIDER_ANTHROPIC,),
    )

    assert lease.resolve(PROVIDER_ANTHROPIC).require("api_key") == STORED_KEY


async def test_a_provider_with_nothing_stored_resolves_empty_rather_than_raising() -> None:
    """A deployment that has not been set up yet is the state every one starts in.

    An empty resolution is what lets the setup checklist report "no provider"
    and the console render the screen that fixes it. Raising here would make
    the absence of a credential indistinguishable from a broken vault.
    """
    resolver = await _vault_with()

    lease = await provider_lease(
        resolver,
        TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID),
        team_id=TEAM_ID,
        providers=(PROVIDER_ANTHROPIC,),
    )

    credentials = lease.resolve(PROVIDER_ANTHROPIC)
    assert credentials.names == ()
    assert not credentials.has("api_key")


async def test_one_unreachable_provider_does_not_deny_the_others() -> None:
    """A lease covers every provider, and providers fail independently."""
    resolver = await _vault_with(values={"api_key": STORED_KEY})

    lease = await provider_lease(
        resolver,
        TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID),
        team_id=TEAM_ID,
        providers=(PROVIDER_ANTHROPIC, PROVIDER_OPENAI),
    )

    assert lease.resolve(PROVIDER_ANTHROPIC).has("api_key")
    assert not lease.resolve(PROVIDER_OPENAI).has("api_key")


async def test_a_team_without_its_own_key_falls_back_to_the_organisations() -> None:
    """The vault's one step of fallback, unchanged by going through the lease."""
    resolver = await _vault_with(values={"api_key": STORED_KEY}, team_id=CREDENTIAL_ORG_WIDE_TEAM)

    lease = await provider_lease(
        resolver,
        TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID),
        team_id=TEAM_ID,
        providers=(PROVIDER_ANTHROPIC,),
    )

    assert lease.resolve(PROVIDER_ANTHROPIC).require("api_key") == STORED_KEY


async def test_the_lease_never_prints_what_it_holds() -> None:
    """``ProviderCredentials`` refuses to print its values, and a lease is no exception.

    A repr reaches tracebacks and pytest failure output, which is exactly where
    a key that leaked once stays.
    """
    resolver = await _vault_with(values={"api_key": STORED_KEY})

    lease = await provider_lease(
        resolver,
        TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID),
        team_id=TEAM_ID,
        providers=(PROVIDER_ANTHROPIC,),
    )

    rendered = repr(lease.resolve(PROVIDER_ANTHROPIC))
    assert STORED_KEY not in rendered
    assert "api_key" in rendered


# -- the route that verifies a provider must test what the operator typed ------


async def test_the_vault_is_preferred_over_the_environment() -> None:
    """The console's "verify" used to exercise the environment's key, not the vault's.

    An operator who pastes a key into the first-run screen and presses verify
    is asking about that key. Answering with whatever the container happened to
    be started with is a different question, and it is the one that says "works"
    for a deployment that is about to fail.
    """
    from gateway.http.routes.providers import provider_credentials

    resolver = await _vault_with(values={"api_key": STORED_KEY})

    credentials = await provider_credentials(
        resolver,
        TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID),
        team_id=TEAM_ID,
        provider_id=PROVIDER_ANTHROPIC,
        environ={"ANTHROPIC_API_KEY": "the-key-from-the-container"},
    )

    assert credentials.require("api_key") == STORED_KEY


async def test_the_environment_still_answers_when_the_vault_holds_nothing() -> None:
    """An operator who set the key in a manifest is not broken by this change."""
    from gateway.http.routes.providers import provider_credentials

    resolver = await _vault_with()

    credentials = await provider_credentials(
        resolver,
        TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID),
        team_id=TEAM_ID,
        provider_id=PROVIDER_ANTHROPIC,
        environ={"ANTHROPIC_API_KEY": "the-key-from-the-container"},
    )

    assert credentials.require("api_key") == "the-key-from-the-container"
