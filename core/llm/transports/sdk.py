"""The default transport: each provider's own SDK, imported only when used.

Every vendor SDK is an optional extra, and every import of one happens inside a
function. Three things follow, and all three matter:

- A no-egress deployment installs ``ninjasre[ollama]`` and gets nothing from
  Anthropic, OpenAI, or AWS in its dependency tree. "Provider neutral" that
  requires nine vendor SDKs on disk is not provider neutral.
- A missing extra is reported as a configuration problem, once, naming the
  extra to install — not as an ``ImportError`` at start-up from a provider
  nobody configured.
- ``make check-vendor-sdks`` has exactly one directory to police.

The bindings below are written from each vendor's documented surface. They are
the one part of this layer that recorded fixtures cannot prove, because a
fixture proves the parse and this is the carry. ``core.llm.preflight`` is what
confirms a binding against the operator's own deployment, and it is meant to be
run before anyone depends on a provider.
"""

from __future__ import annotations

import importlib
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
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
    TRANSPORT_SDK,
)
from core.llm.credentials import ProviderCredentials
from core.llm.failures import ErrorObservation
from core.llm.transports import (
    TransportError,
    TransportUnavailableError,
    WireRequest,
    WireResponse,
)


@dataclass(frozen=True, slots=True)
class SdkBinding:
    """Which distribution and module a provider's SDK lives in."""

    #: The extra an operator installs: ``pip install "ninjasre[anthropic]"``.
    extra: str
    #: The module that must import for the binding to work.
    module: str
    #: Every module the binding touches, so a partial install is reported once.
    requires: tuple[str, ...] = ()


#: OpenAI-wire providers share one SDK pointed at a different base URL. That is
#: the whole reason five of the nine providers cost almost nothing to support.
_OPENAI_BINDING = SdkBinding(extra="openai", module="openai")

_BINDINGS: dict[str, SdkBinding] = {
    PROVIDER_ANTHROPIC: SdkBinding(extra="anthropic", module="anthropic"),
    PROVIDER_OPENAI: _OPENAI_BINDING,
    PROVIDER_AZURE_OPENAI: _OPENAI_BINDING,
    PROVIDER_OPENROUTER: _OPENAI_BINDING,
    PROVIDER_NVIDIA_NIM: _OPENAI_BINDING,
    PROVIDER_OLLAMA: _OPENAI_BINDING,
    PROVIDER_AWS_BEDROCK: SdkBinding(extra="bedrock", module="boto3", requires=("botocore",)),
    PROVIDER_GOOGLE_GEMINI: SdkBinding(extra="google", module="google.genai"),
    PROVIDER_GOOGLE_VERTEX_AI: SdkBinding(extra="google", module="google.genai"),
}

#: Base URLs for the OpenAI-wire providers that are not OpenAI itself. An
#: operator overrides any of these through the credential resolver.
_DEFAULT_BASE_URLS: dict[str, str] = {
    PROVIDER_OPENROUTER: "https://openrouter.ai/api/v1",
    PROVIDER_NVIDIA_NIM: "https://integrate.api.nvidia.com/v1",
    PROVIDER_OLLAMA: "http://localhost:11434/v1",
}

#: Local endpoints authenticate with nothing. The OpenAI client still wants a
#: key, so it gets a placeholder that never leaves the host.
_UNUSED_LOCAL_KEY = "not-required"


def binding_for(provider_id: str) -> SdkBinding | None:
    """Return the SDK binding for ``provider_id``, if one is registered."""
    return _BINDINGS.get(provider_id)


def register_binding(provider_id: str, binding: SdkBinding) -> None:
    """Register the SDK binding for a provider added at runtime."""
    _BINDINGS[provider_id] = binding


def _import_or_report(provider_id: str) -> Any:
    """Return the provider's SDK module, or report the extra that is missing."""
    binding = _BINDINGS.get(provider_id)
    if binding is None:
        raise TransportUnavailableError(
            ErrorObservation(
                message=(
                    f"provider {provider_id!r} has no SDK binding; register one with "
                    "core.llm.transports.sdk.register_binding"
                ),
                exception_type="TransportUnavailableError",
            )
        )

    for module_name in (*binding.requires, binding.module):
        try:
            importlib.import_module(module_name)
        except ImportError as error:
            raise TransportUnavailableError(
                ErrorObservation(
                    message=(
                        f"the {provider_id!r} provider needs the {binding.extra!r} extra: "
                        f'install it with `pip install "ninjasre[{binding.extra}]"`'
                    ),
                    exception_type="TransportUnavailableError",
                )
            ) from error

    return importlib.import_module(binding.module)


def observe_sdk_error(error: Exception) -> ErrorObservation:
    """Return what is known about ``error`` without importing a vendor's types.

    Status and body are read off whatever attributes the SDK happens to expose.
    Matching structurally rather than by type keeps this module free of vendor
    imports at module scope, which is the boundary the build check enforces.
    """
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)

    body = getattr(error, "body", None)
    error_code = None
    message = str(error)
    if isinstance(body, Mapping):
        inner = body.get("error")
        if isinstance(inner, Mapping):
            error_code = inner.get("type") or inner.get("code")
            message = str(inner.get("message") or message)

    return ErrorObservation(
        status_code=status_code if isinstance(status_code, int) else None,
        error_code=str(error_code) if error_code else None,
        message=message,
        exception_type=type(error).__name__,
        body=dict(body) if isinstance(body, Mapping) else {},
    )


def as_document(value: Any) -> Mapping[str, Any]:
    """Return an SDK response object as a plain document.

    Every current vendor SDK models responses with a serialiser of one of these
    names. Going through it means the parse path downstream sees exactly the
    document a recorded fixture holds.
    """
    for method in ("model_dump", "to_dict", "dict"):
        serialiser = getattr(value, method, None)
        if callable(serialiser):
            document = serialiser()
            if isinstance(document, Mapping):
                return document
    if isinstance(value, Mapping):
        return value
    raise TransportError(
        ErrorObservation(
            message=f"provider returned {type(value).__name__}, which is not a document",
            exception_type="TransportError",
        )
    )


# --- Per-provider clients -----------------------------------------------------


def _anthropic_client(module: Any, credentials: ProviderCredentials, timeout: float) -> Any:
    return module.AsyncAnthropic(
        api_key=credentials.require("api_key"),
        base_url=credentials.get("base_url"),
        timeout=timeout,
        max_retries=0,  # retry is this layer's decision, coupled to classification
    )


def _openai_client(
    module: Any,
    provider_id: str,
    credentials: ProviderCredentials,
    timeout: float,
) -> Any:
    if provider_id == PROVIDER_AZURE_OPENAI:
        return module.AsyncAzureOpenAI(
            api_key=credentials.require("api_key"),
            azure_endpoint=credentials.require("endpoint"),
            api_version=credentials.require("api_version"),
            timeout=timeout,
            max_retries=0,
        )

    base_url = credentials.get("base_url") or _DEFAULT_BASE_URLS.get(provider_id)
    api_key = credentials.get("api_key") or _UNUSED_LOCAL_KEY
    return module.AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=0,
    )


def _google_client(module: Any, provider_id: str, credentials: ProviderCredentials) -> Any:
    if provider_id == PROVIDER_GOOGLE_VERTEX_AI:
        return module.Client(
            vertexai=True,
            project=credentials.require("project"),
            location=credentials.require("location"),
        )
    return module.Client(api_key=credentials.require("api_key"))


def _bedrock_client(module: Any, credentials: ProviderCredentials) -> Any:
    session = module.Session(profile_name=credentials.get("profile"))
    return session.client(
        "bedrock-runtime",
        region_name=credentials.require("region"),
        endpoint_url=credentials.get("endpoint"),
        aws_access_key_id=credentials.get("access_key_id"),
        aws_secret_access_key=credentials.get("secret_access_key"),
        aws_session_token=credentials.get("session_token"),
    )


async def _send_anthropic(module: Any, request: WireRequest) -> WireResponse:
    client = _anthropic_client(module, request.credentials, request.timeout_seconds)
    message = await client.messages.create(**dict(request.payload))
    return WireResponse(payload=as_document(message))


async def _send_openai(module: Any, request: WireRequest) -> WireResponse:
    client = _openai_client(
        module, request.provider_id, request.credentials, request.timeout_seconds
    )
    completion = await client.chat.completions.create(**dict(request.payload))
    return WireResponse(payload=as_document(completion))


async def _send_google(module: Any, request: WireRequest) -> WireResponse:
    client = _google_client(module, request.provider_id, request.credentials)
    payload = dict(request.payload)
    response = await client.aio.models.generate_content(
        model=payload.pop("model", request.model_id),
        contents=payload.pop("contents", []),
        config=payload.pop("config", None),
    )
    return WireResponse(payload=as_document(response))


async def _send_bedrock(module: Any, request: WireRequest) -> WireResponse:
    import asyncio

    client = _bedrock_client(module, request.credentials)
    payload = dict(request.payload)

    # botocore is synchronous, and blocking the event loop would stall every
    # other turn in the same process. A worker thread is the smallest correct
    # answer that does not add an async AWS client to the dependency tree.
    response = await asyncio.to_thread(lambda: client.converse(**payload))
    return WireResponse(payload=as_document(response))


_SENDERS: dict[str, Callable[[Any, WireRequest], Awaitable[WireResponse]]] = {
    PROVIDER_ANTHROPIC: _send_anthropic,
    PROVIDER_OPENAI: _send_openai,
    PROVIDER_AZURE_OPENAI: _send_openai,
    PROVIDER_OPENROUTER: _send_openai,
    PROVIDER_NVIDIA_NIM: _send_openai,
    PROVIDER_OLLAMA: _send_openai,
    PROVIDER_AWS_BEDROCK: _send_bedrock,
    PROVIDER_GOOGLE_GEMINI: _send_google,
    PROVIDER_GOOGLE_VERTEX_AI: _send_google,
}


class SdkTransport:
    """Carries requests through each provider's own SDK."""

    @property
    def name(self) -> str:
        """Return this transport's configuration identifier."""
        return TRANSPORT_SDK

    async def send(self, request: WireRequest) -> WireResponse:
        """Return the provider's response document.

        Raises:
            TransportError: the request failed, classified from what the SDK
                exposed about it.
            TransportUnavailableError: the provider's extra is not installed.
        """
        module = _import_or_report(request.provider_id)
        sender = _SENDERS.get(request.provider_id)
        if sender is None:
            raise TransportUnavailableError(
                ErrorObservation(
                    message=f"no SDK sender registered for provider {request.provider_id!r}",
                    exception_type="TransportUnavailableError",
                )
            )
        try:
            return await sender(module, request)
        except TransportError:
            raise
        except Exception as error:  # noqa: BLE001 — every SDK raises its own types
            raise TransportError(observe_sdk_error(error)) from error

    async def stream(self, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
        """Yield provider-shaped chunks for a streamed request.

        Streaming goes through the same senders with the provider's stream flag
        set, so a chunk is the same kind of document a recorded fixture holds
        and the same parse path reads it.
        """
        module = _import_or_report(request.provider_id)
        payload = {**dict(request.payload), "stream": True}

        try:
            if request.provider_id == PROVIDER_ANTHROPIC:
                client = _anthropic_client(module, request.credentials, request.timeout_seconds)
                async with client.messages.stream(**dict(request.payload)) as stream:
                    async for event in stream:
                        yield as_document(event)
                return

            if request.provider_id in {PROVIDER_GOOGLE_GEMINI, PROVIDER_GOOGLE_VERTEX_AI}:
                client = _google_client(module, request.provider_id, request.credentials)
                body = dict(request.payload)
                iterator = await client.aio.models.generate_content_stream(
                    model=body.pop("model", request.model_id),
                    contents=body.pop("contents", []),
                    config=body.pop("config", None),
                )
                async for chunk in iterator:
                    yield as_document(chunk)
                return

            if request.provider_id == PROVIDER_AWS_BEDROCK:
                async for chunk in _stream_bedrock(module, request):
                    yield chunk
                return

            client = _openai_client(
                module, request.provider_id, request.credentials, request.timeout_seconds
            )
            stream = await client.chat.completions.create(**payload)
            async for chunk in stream:
                yield as_document(chunk)
        except TransportError:
            raise
        except Exception as error:  # noqa: BLE001 — every SDK raises its own types
            raise TransportError(observe_sdk_error(error)) from error


async def _stream_bedrock(module: Any, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
    """Yield Converse stream events, pulled off the blocking iterator in a thread."""
    import asyncio

    client = _bedrock_client(module, request.credentials)
    response = await asyncio.to_thread(lambda: client.converse_stream(**dict(request.payload)))
    events = response.get("stream")
    if events is None:
        return

    iterator = iter(events)
    sentinel = object()
    while True:
        event = await asyncio.to_thread(lambda: next(iterator, sentinel))
        if event is sentinel:
            return
        if isinstance(event, Mapping):
            yield event


__all__ = [
    "SdkBinding",
    "SdkTransport",
    "as_document",
    "binding_for",
    "observe_sdk_error",
    "register_binding",
]
