"""The optional LiteLLM transport.

Genuinely useful for an operator already running LiteLLM, and deliberately not
the default. Putting a third party's dialect translation on the critical path
for tool calling means that when a schema is rejected, the question becomes
whose translation rejected it — and that question is asked during an incident.

So it is an extra, and its equivalence to the SDK path is a contract test rather
than a claim: the same request through either transport must produce the same
``InvokeResult``.

LiteLLM speaks the OpenAI wire for every provider it fronts, so the adapter
payload it receives is the OpenAI-wire one with a routed model identifier.
"""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator, Mapping
from typing import Any

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
    TRANSPORT_LITELLM,
)
from core.llm.failures import ErrorObservation
from core.llm.transports import (
    TransportError,
    TransportUnavailableError,
    WireRequest,
    WireResponse,
)
from core.llm.transports.sdk import as_document, observe_sdk_error

#: LiteLLM routes on a ``prefix/model`` identifier of its own. Mapping it here
#: keeps NinjaSRE's provider identifiers stable regardless of what LiteLLM
#: decides to call things next.
_ROUTE_PREFIXES: dict[str, str] = {
    PROVIDER_ANTHROPIC: "anthropic",
    PROVIDER_OPENAI: "openai",
    PROVIDER_AZURE_OPENAI: "azure",
    PROVIDER_AWS_BEDROCK: "bedrock",
    PROVIDER_GOOGLE_GEMINI: "gemini",
    PROVIDER_GOOGLE_VERTEX_AI: "vertex_ai",
    PROVIDER_OPENROUTER: "openrouter",
    PROVIDER_NVIDIA_NIM: "nvidia_nim",
    PROVIDER_OLLAMA: "ollama_chat",
}


def route_for(provider_id: str, model_id: str) -> str:
    """Return the identifier LiteLLM routes ``model_id`` on."""
    prefix = _ROUTE_PREFIXES.get(provider_id)
    if prefix is None or model_id.startswith(f"{prefix}/"):
        return model_id
    return f"{prefix}/{model_id}"


def _import_litellm() -> Any:
    try:
        return importlib.import_module("litellm")
    except ImportError as error:
        raise TransportUnavailableError(
            ErrorObservation(
                message=(
                    "the LiteLLM transport needs the 'litellm' extra: install it with "
                    '`pip install "ninjasre[litellm]"`, or leave the default SDK transport '
                    "configured"
                ),
                exception_type="TransportUnavailableError",
            )
        ) from error


def _routed_payload(request: WireRequest) -> dict[str, Any]:
    """Return the payload with LiteLLM's routing and credentials applied."""
    payload = dict(request.payload)
    payload["model"] = route_for(request.provider_id, request.model_id)

    api_key = request.credentials.get("api_key")
    if api_key:
        payload.setdefault("api_key", api_key)
    base_url = request.credentials.get("base_url") or request.credentials.get("endpoint")
    if base_url:
        payload.setdefault("api_base", base_url)
    payload.setdefault("timeout", request.timeout_seconds)
    # Retry belongs to this layer, where it is coupled to classification.
    payload.setdefault("num_retries", 0)
    return payload


class LiteLlmTransport:
    """Carries requests through a LiteLLM installation."""

    @property
    def name(self) -> str:
        """Return this transport's configuration identifier."""
        return TRANSPORT_LITELLM

    async def send(self, request: WireRequest) -> WireResponse:
        """Return the provider's response document, as LiteLLM produced it.

        Raises:
            TransportError: the request failed.
            TransportUnavailableError: LiteLLM is not installed.
        """
        module = _import_litellm()
        try:
            completion = await module.acompletion(**_routed_payload(request))
            return WireResponse(payload=as_document(completion))
        except TransportError:
            raise
        except Exception as error:  # noqa: BLE001 — LiteLLM re-raises vendor types
            raise TransportError(observe_sdk_error(error)) from error

    async def stream(self, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
        """Yield OpenAI-wire chunks for a streamed request."""
        module = _import_litellm()
        payload = {**_routed_payload(request), "stream": True}
        try:
            stream = await module.acompletion(**payload)
            async for chunk in stream:
                yield as_document(chunk)
        except TransportError:
            raise
        except Exception as error:  # noqa: BLE001 — LiteLLM re-raises vendor types
            raise TransportError(observe_sdk_error(error)) from error


__all__ = ["LiteLlmTransport", "route_for"]
