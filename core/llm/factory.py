"""Resolving a role to a client: role, then provider, then model, then transport.

The composition root of the layer. It is the only place that reads
configuration, constructs a transport, and hands out a client, so every other
module can be written as a pure function of its inputs.

What decides a role's provider is configuration: an explicit binding wins, then
this role's own configured choice, then the investigator's, then the shipped
default. A role nobody has configured resolves rather than failing, because an
investigation that cannot start is worse than one that starts on a named model
and says so in its trace.

The environment is not in that list, and its absence is deliberate — see
``resolve_binding``. It still supplies what it is for: an endpoint, a
credential, and the transport, none of which is a choice about what this
deployment is.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from config.constants.config_service import MODEL_ROLE_INVESTIGATOR
from config.constants.llm import (
    DEFAULT_PROVIDER,
    DEFAULT_TRANSPORT,
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

#: What the configuration tree binds each role to, as ``role -> (provider, model)``.
#:
#: Process-wide, and published by the composition root rather than read here.
#: ``resolve_binding`` is synchronous and resolving the configuration tree is
#: not, so the alternative would be for this module to learn to await — which
#: would make every caller in the investigation loop async for a value that
#: changes when an operator saves a form, not per turn.
#:
#: Empty is the honest starting state: a deployment that has not been set up
#: yet has bound nothing, and every role falls through to the environment and
#: then to the shipped default.
_CONFIGURED_BINDINGS: dict[str, tuple[str, str]] = {}


def publish_configured_bindings(bindings: dict[str, tuple[str, str]]) -> None:
    """Replace what configuration says each role runs on.

    Called by the composition root after it resolves the configuration tree,
    and again whenever that tree changes. Replaces rather than merges: a role
    an operator has unbound must stop being bound, and a merge would leave the
    old answer in place with nothing to say it was withdrawn.
    """
    _CONFIGURED_BINDINGS.clear()
    _CONFIGURED_BINDINGS.update(bindings)


def reset_configured_bindings() -> None:
    """Forget every published binding, returning to environment and defaults."""
    _CONFIGURED_BINDINGS.clear()


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

    Explicit arguments win, then this role's configured binding, then the
    investigator's, then the shipped default. The resolved binding is returned
    rather than applied so a caller — or the run trace — can see what an
    investigation is about to run on before it starts.

    **The environment does not choose a provider.** It used to answer for any
    role configuration did not name, and that remainder was the whole of a real
    failure: a deployment bound its investigator to Gemini in the console, left
    the other seven roles alone as the console invites, and every one of them
    fell past configuration into a ``NINJASRE_LLM_PROVIDER`` a manifest had set
    to Ollama at some earlier point, on a host that no longer answered. Episode
    extraction therefore called a provider nobody had chosen and no screen
    showed, and fifty investigations lost their episode to a connection
    refused. Nothing was misconfigured — the operator chose one provider and
    the deployment ran on two.

    **An unnamed role follows the investigator**, which is the promise the
    console already makes in words and the only fallback that cannot surprise
    anybody: the provider somebody picked is the provider their deployment
    uses. The shipped default answers only where nothing is configured at all,
    which is a deployment nobody has set up yet.

    The environment keeps what it is genuinely for — an endpoint, a credential,
    a transport — and loses the one thing it should never have decided.
    """
    catalogue = registry or default_registry()
    configured_provider, configured_model = _CONFIGURED_BINDINGS.get(role, ("", ""))
    if not configured_provider and role != MODEL_ROLE_INVESTIGATOR:
        configured_provider, configured_model = _CONFIGURED_BINDINGS.get(
            MODEL_ROLE_INVESTIGATOR, ("", "")
        )

    resolved_provider = provider_id or configured_provider or DEFAULT_PROVIDER
    # A model is only inherited from the same source that chose the provider. A
    # model name means something to one provider, and carrying one across a
    # different provider would ask Ollama for a Claude model.
    resolved_model = model_id or (
        configured_model if provider_id is None and configured_provider else ""
    )

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
    "publish_configured_bindings",
    "reset_configured_bindings",
    "reset_factory",
    "resolve_binding",
]
