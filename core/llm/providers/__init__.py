"""The adapter registry: provider identifier to the code that speaks its wire.

Adding a provider is one module here and one row in ``core.llm.registry``. The
lookup is a dictionary rather than a scan of the package so an adapter appears
because somebody registered it, not because of where its file happens to sit —
and so a provider added at runtime works the same way as a shipped one.
"""

from __future__ import annotations

from config.constants.llm import (
    PROVIDER_ANTHROPIC,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_AZURE_OPENAI,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_GOOGLE_VERTEX_AI,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
)
from core.llm.providers.anthropic import AnthropicAdapter
from core.llm.providers.azure_openai import AzureOpenAiAdapter
from core.llm.providers.base import ProviderAdapter
from core.llm.providers.bedrock import BedrockAdapter
from core.llm.providers.gemini import GeminiAdapter, VertexAdapter
from core.llm.providers.openai_compat import (
    NvidiaNimAdapter,
    OllamaAdapter,
    OpenAiAdapter,
    OpenRouterAdapter,
)


class UnsupportedProviderError(LookupError):
    """A provider with no adapter.

    Raised rather than defaulted to something OpenAI-shaped: a wrong wire fails
    at the first tool call, by which point the investigation has already spent
    its budget getting there.
    """


_ADAPTERS: dict[str, ProviderAdapter] = {
    PROVIDER_ANTHROPIC: AnthropicAdapter(),
    PROVIDER_OPENAI: OpenAiAdapter(),
    PROVIDER_AZURE_OPENAI: AzureOpenAiAdapter(),
    PROVIDER_AWS_BEDROCK: BedrockAdapter(),
    PROVIDER_GOOGLE_GEMINI: GeminiAdapter(),
    PROVIDER_GOOGLE_VERTEX_AI: VertexAdapter(),
    PROVIDER_OPENROUTER: OpenRouterAdapter(),
    PROVIDER_NVIDIA_NIM: NvidiaNimAdapter(),
    PROVIDER_OLLAMA: OllamaAdapter(),
}


def adapter_for(provider_id: str) -> ProviderAdapter:
    """Return the adapter for ``provider_id``.

    Raises:
        UnsupportedProviderError: nothing is registered for it.
    """
    adapter = _ADAPTERS.get(provider_id)
    if adapter is None:
        raise UnsupportedProviderError(
            f"no adapter registered for provider {provider_id!r}; "
            f"registered providers are {', '.join(sorted(_ADAPTERS))}"
        )
    return adapter


def register_adapter(adapter: ProviderAdapter) -> None:
    """Register or replace the adapter for one provider."""
    _ADAPTERS[adapter.provider_id] = adapter


def registered_provider_ids() -> tuple[str, ...]:
    """Return every provider with an adapter."""
    return tuple(sorted(_ADAPTERS))


__all__ = [
    "AnthropicAdapter",
    "AzureOpenAiAdapter",
    "BedrockAdapter",
    "GeminiAdapter",
    "NvidiaNimAdapter",
    "OllamaAdapter",
    "OpenAiAdapter",
    "OpenRouterAdapter",
    "ProviderAdapter",
    "UnsupportedProviderError",
    "VertexAdapter",
    "adapter_for",
    "register_adapter",
    "registered_provider_ids",
]
