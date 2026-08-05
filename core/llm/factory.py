"""Resolving a role to a client: role, then provider, then model, then transport.

The composition root of the layer. It is the only place that reads
configuration, constructs a transport, and hands out a client, so every other
module can be written as a pure function of its inputs.

Model selection *policy* per role is a later feature's job. What is here is the
mechanism it will drive: an explicit binding wins, then the environment, then
the shipped default. A role nobody has configured resolves to the default
provider rather than failing, because an investigation that cannot start is
worse than one that starts on the default model and says so in its trace.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from config.constants.llm import (
    DEFAULT_PROVIDER,
    DEFAULT_TRANSPORT,
    NINJASRE_LLM_MODEL_ENV,
    NINJASRE_LLM_PROVIDER_ENV,
    NINJASRE_LLM_TRANSPORT_ENV,
    SUPPORTED_TRANSPORTS,
    TRANSPORT_LITELLM,
)
from core.llm.client import ProviderClient
from core.llm.credentials import CredentialResolver, EnvironmentCredentialResolver
from core.llm.internal.client_cache import ClientCache
from core.llm.internal.client_cache_key import ClientCacheKey
from core.llm.providers import adapter_for
from core.llm.registry import ModelDescriptor, ModelRegistry, UnknownModelError, default_registry
from core.llm.transports import WireTransport
from core.llm.transports.litellm import LiteLlmTransport
from core.llm.transports.sdk import SdkTransport

#: The role used when a caller names none.
DEFAULT_ROLE = "default"


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    """Which provider, model, and transport a role resolves to."""

    role: str
    provider_id: str
    model_id: str
    transport: str = DEFAULT_TRANSPORT

    def cache_key(self, descriptor: ModelDescriptor, base_url: str = "") -> ClientCacheKey:
        """Return the cache key this binding produces."""
        return ClientCacheKey(
            role=self.role,
            provider_id=self.provider_id,
            model_id=self.model_id,
            transport=self.transport,
            base_url=base_url,
            deployment_id=descriptor.deployment_id or "",
        )


def _configured_transport() -> str:
    requested = os.environ.get(NINJASRE_LLM_TRANSPORT_ENV, "").strip().lower()
    return requested if requested in SUPPORTED_TRANSPORTS else DEFAULT_TRANSPORT


def resolve_binding(
    role: str = DEFAULT_ROLE,
    *,
    provider_id: str | None = None,
    model_id: str | None = None,
    transport: str | None = None,
    registry: ModelRegistry | None = None,
) -> ProviderBinding:
    """Return the binding for ``role``.

    Explicit arguments win, then the environment, then the shipped default. The
    resolved binding is returned rather than applied so a caller — or the run
    trace — can see what an investigation is about to run on before it starts.
    """
    catalogue = registry or default_registry()

    resolved_provider = (
        provider_id or os.environ.get(NINJASRE_LLM_PROVIDER_ENV, "").strip() or DEFAULT_PROVIDER
    )
    resolved_model = model_id or os.environ.get(NINJASRE_LLM_MODEL_ENV, "").strip()

    if not resolved_model:
        try:
            resolved_model = catalogue.default_for_provider(resolved_provider).model_id
        except UnknownModelError:
            resolved_model = catalogue.default_for_provider(DEFAULT_PROVIDER).model_id
            resolved_provider = DEFAULT_PROVIDER

    return ProviderBinding(
        role=role,
        provider_id=resolved_provider,
        model_id=resolved_model,
        transport=transport or _configured_transport(),
    )


def build_transport(name: str) -> WireTransport:
    """Return the transport named ``name``."""
    if name == TRANSPORT_LITELLM:
        return LiteLlmTransport()
    return SdkTransport()


@dataclass(slots=True)
class LlmFactory:
    """Builds and caches clients.

    An instance rather than module-level state, so a test — or a second
    deployment profile in one process — gets its own cache and its own
    credential resolver without reaching into a global.
    """

    registry: ModelRegistry
    credentials: CredentialResolver
    cache: ClientCache

    def __init__(
        self,
        *,
        registry: ModelRegistry | None = None,
        credentials: CredentialResolver | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.credentials = credentials or EnvironmentCredentialResolver()
        self.cache = ClientCache()

    def get(
        self,
        role: str = DEFAULT_ROLE,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
        transport: str | None = None,
    ) -> ProviderClient:
        """Return the client bound to ``role``, building it on first use."""
        binding = resolve_binding(
            role,
            provider_id=provider_id,
            model_id=model_id,
            transport=transport,
            registry=self.registry,
        )
        descriptor = self.registry.get(binding.provider_id, binding.model_id)
        resolved = self.credentials.resolve(binding.provider_id)
        key = binding.cache_key(descriptor, base_url=resolved.get("base_url") or "")

        def build() -> ProviderClient:
            return ProviderClient(
                adapter=adapter_for(binding.provider_id),
                descriptor=descriptor,
                transport=build_transport(binding.transport),
                credentials=self.credentials,
            )

        return self.cache.get_or_create(key, build)


_FACTORY = LlmFactory()


def get_llm(
    role: str = DEFAULT_ROLE,
    *,
    provider_id: str | None = None,
    model_id: str | None = None,
    transport: str | None = None,
) -> ProviderClient:
    """Return the client for ``role`` from the process-wide factory.

    The one call the rest of NinjaSRE makes. Everything below it — dialects,
    adapters, transports, retry — is reached through the returned client and
    never imported by a caller.
    """
    return _FACTORY.get(role, provider_id=provider_id, model_id=model_id, transport=transport)


def reset_factory(
    *,
    registry: ModelRegistry | None = None,
    credentials: CredentialResolver | None = None,
) -> LlmFactory:
    """Replace the process-wide factory. For tests and for a configuration reload."""
    global _FACTORY
    _FACTORY = LlmFactory(registry=registry, credentials=credentials)
    return _FACTORY


__all__ = [
    "DEFAULT_ROLE",
    "LlmFactory",
    "ProviderBinding",
    "build_transport",
    "get_llm",
    "reset_factory",
    "resolve_binding",
]
