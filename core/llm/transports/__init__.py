"""The seam between "what to send" and "how it gets there".

An adapter builds a provider-shaped payload and reads a provider-shaped
response. A transport is what carries the bytes in between. Splitting the two is
what lets the contract suite run every adapter against recorded payloads on
every pull request without a network, a credential, or a token: the part that
breaks when a vendor changes a dialect is the part that is tested for free.

Two transports ship. The vendor SDK is the default and the one the contract
suite treats as normative; LiteLLM is available for operators already running
it. Choosing between them must not change an ``InvokeResult``, and a contract
test says so.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.llm import LLM_REQUEST_TIMEOUT_SECONDS
from core.llm.credentials import ProviderCredentials
from core.llm.failures import ErrorObservation


@dataclass(frozen=True, slots=True)
class WireRequest:
    """One provider-shaped request, ready to be carried.

    Everything the transport needs is here, captured when the request was built.
    A transport never reads back from client state — that is the whole of the
    concurrent-turn fix, enforced by there being nothing else to read.
    """

    provider_id: str
    model_id: str
    payload: Mapping[str, Any]
    credentials: ProviderCredentials
    timeout_seconds: float = LLM_REQUEST_TIMEOUT_SECONDS
    #: Provider-shaped routing that is not part of the body: a Bedrock region,
    #: an Azure deployment and API version, a Vertex project.
    routing: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WireResponse:
    """One provider-shaped response, as a plain document.

    Plain, because every parse path downstream is a pure function over a
    document — which is what makes a recorded fixture indistinguishable from a
    live call, and therefore what makes the contract suite meaningful.
    """

    payload: Mapping[str, Any]
    status_code: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)


class TransportError(Exception):
    """A request that did not come back, carrying enough to classify it."""

    def __init__(self, observation: ErrorObservation) -> None:
        super().__init__(observation.message or observation.exception_type or "transport error")
        self.observation = observation


class TransportUnavailableError(TransportError):
    """The transport cannot run at all — usually an extra that is not installed.

    Distinct from a failed request. A missing SDK is an operator's configuration
    problem, reported once and clearly, not something to retry.
    """


@runtime_checkable
class WireTransport(Protocol):
    """Carries a provider-shaped request to a provider and back."""

    @property
    def name(self) -> str:
        """Return the transport identifier used in configuration and traces."""

    async def send(self, request: WireRequest) -> WireResponse:
        """Return the provider's response document.

        Raises:
            TransportError: the request did not produce a response.
        """

    def stream(self, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
        """Return an iterator of provider-shaped chunks for a streamed request."""


__all__ = [
    "TransportError",
    "TransportUnavailableError",
    "WireRequest",
    "WireResponse",
    "WireTransport",
]
