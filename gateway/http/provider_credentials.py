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
)
from core.llm.factory import reset_factory
from gateway.http.credential_schemas import schema_for
from platform.credentials.proxy.llm import provider_lease
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

    A failure to read the vault leaves the environment resolver in place and
    says so. Refusing to boot over it would take away the console somebody would
    fix the vault from, and the deployment that names its key in a manifest is
    unaffected either way.
    """
    try:
        lease = await provider_lease(
            VaultCredentialResolver(gateway=state.gateway, schemas=_schemas()),
            TenantScope(org_id=org_id),
        )
    except Exception as unreadable:  # noqa: BLE001 — the environment still answers
        logger.warning("providers.lease_unavailable", error=str(unreadable))
        return

    held = [provider for provider in SUPPORTED_PROVIDERS if lease.resolve(provider).names]
    reset_factory(
        credentials=VaultFirstCredentials(vault=lease, environment=EnvironmentCredentialResolver())
    )
    # The provider names, never a value. Which providers this deployment holds a
    # key for is the fact an operator reading a boot log is looking for.
    logger.info("providers.credentials_composed", providers=sorted(held))


__all__ = ["VaultFirstCredentials", "compose_provider_credentials"]
