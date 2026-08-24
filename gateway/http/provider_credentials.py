"""Giving the model factory the keys the console wrote, not the ones the container was started with.

``core.llm``'s factory defaults to ``EnvironmentCredentialResolver`` and expects
a composition root to replace it — ``reset_factory(credentials=…)`` exists for
nothing else. Nothing ever did. So an operator pasted a provider key into the
first-run screen, watched it verify against the real endpoint (the verify route
resolves through the vault, one request at a time), and then had every
investigation call that same provider with whatever the process environment
held, which in a vault-configured deployment is nothing.

``platform/credentials/proxy/llm.py::provider_lease`` was written for exactly
this and says so in its own module docstring: *"Nothing here is imported by
``core.llm``; the composition root calls this and hands the result down."* Only
the per-request verify route ever called it.

**The environment keeps its place, underneath.** Naming a key in a deployment
manifest is a supported shape and a deployment already running one must not stop
working because the vault holds nothing for that provider. The order is the same
one the verify route already applies by hand: the vault first, because it is
what the operator most recently chose, and the environment second.

**A lease is taken once, at boot.** ``CredentialResolver.resolve`` is
synchronous and vault resolution is not, which is why the lease exists at all.
The cost is that a key rotated afterwards is not seen until the lease is taken
again — so the write route refreshes it, the same way an address written there
refreshes the vendor binding beside it.
"""

from __future__ import annotations

from typing import Any

from config.constants.llm import SUPPORTED_PROVIDERS
from core.llm.credentials import (
    CredentialResolver,
    EnvironmentCredentialResolver,
    ProviderCredentials,
    StaticCredentialResolver,
)
from core.llm.factory import reset_factory
from gateway.http.credential_handles import resolve_credential_handle
from gateway.http.credential_schemas import schema_for
from platform.credentials.errors import CredentialNotConfigured
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.resolution import CredentialResolver as VaultCredentialResolver
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope

logger = get_logger(__name__)


class VaultFirstCredentials:
    """Answers from the vault where it can, and from the environment where it cannot.

    Holds two resolvers rather than merging their answers: a provider is
    configured in one place or the other, and a credential assembled half from
    each would be a key from the vault with a base URL from a manifest nobody
    meant to combine.
    """

    __slots__ = ("_environment", "_vault")

    def __init__(self, *, vault: CredentialResolver, environment: CredentialResolver) -> None:
        self._vault = vault
        self._environment = environment

    def resolve(self, provider_id: str) -> ProviderCredentials:
        """Return the vault's credentials for ``provider_id``, or the environment's."""
        stored = self._vault.resolve(provider_id)
        return stored if stored.names else self._environment.resolve(provider_id)


def _schemas() -> CredentialSchemaRegistry:
    """Return the registry the vault validates provider credentials against."""
    return CredentialSchemaRegistry.from_schemas(
        *(schema_for(provider) for provider in SUPPORTED_PROVIDERS)
    )


async def compose_provider_credentials(state: Any, *, org_id: str) -> None:
    """Point the model factory at this organisation's stored provider keys.

    Each provider is leased by the handle it actually resolves to
    (``resolve_credential_handle``), not the organisation-wide handle
    unconditionally. A key an operator wrote under their own team's handle
    used to verify green and then be invisible to every investigation,
    because the boot-time lease never asked the vault which team held it —
    it only ever asked for the organisation's. A failure to read the vault
    leaves the environment resolver in place and says so. Refusing to boot
    over it would take away the console somebody would fix the vault from,
    and the deployment that names its key in a manifest is unaffected
    either way.
    """
    scope = TenantScope(org_id=org_id)
    resolver = VaultCredentialResolver(gateway=state.gateway, schemas=_schemas())

    leased: dict[str, dict[str, str]] = {}
    origin_team: dict[str, str] = {}
    try:
        for provider_id in SUPPORTED_PROVIDERS:
            resolved = await resolve_credential_handle(
                state.gateway, scope, integration=provider_id
            )
            if resolved.is_ambiguous:
                logger.warning(
                    "providers.lease_team_ambiguous",
                    provider_id=provider_id,
                    teams=list(resolved.ambiguous_teams),
                )
            handle = CredentialHandle(integration=provider_id, team_id=resolved.team_id)
            try:
                found = await resolver.resolve(scope, handle)
            except CredentialNotConfigured:
                continue
            leased[provider_id] = dict(found.values)
            origin_team[provider_id] = resolved.team_id
    except Exception as unreadable:  # noqa: BLE001 — the environment still answers
        logger.warning("providers.lease_unavailable", error=str(unreadable))
        return

    environment = EnvironmentCredentialResolver()
    reset_factory(
        credentials=VaultFirstCredentials(
            vault=StaticCredentialResolver(leased), environment=environment
        )
    )

    # Names and origins only, never a value: which provider this deployment
    # holds a key for, and where it came from — the vault, under which team,
    # or the environment — is the fact an operator reading a boot log is
    # looking for.
    origins: dict[str, str] = {
        provider_id: f"vault:{team_id}" for provider_id, team_id in origin_team.items()
    }
    for provider_id in SUPPORTED_PROVIDERS:
        if provider_id not in origins and environment.resolve(provider_id).names:
            origins[provider_id] = "environment"
    logger.info("providers.credentials_composed", origins=origins)


__all__ = ["VaultFirstCredentials", "compose_provider_credentials"]
