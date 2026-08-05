"""Parameterises the provider contract suite over all nine providers.

The transport is a queue of recorded documents. That is the whole trick: an
adapter's parse path is a pure function over a document, so replaying
a recorded one exercises exactly the code a live call would, at no cost and with
no credential. What a replay cannot cover is the carry itself — that is what
``core.llm.preflight`` is for, and the suite says so rather than pretending
otherwise.

Secrets never enter a cassette because no cassette is ever recorded from a live
call here: they are written from the vendors' documented response shapes. There
is nothing to scrub, which is a stronger guarantee than scrubbing.
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from typing import Any

import pytest
from cassettes import stream_chunks, text_response

from config.constants.llm import SUPPORTED_PROVIDERS
from core.llm.client import ProviderClient
from core.llm.credentials import StaticCredentialResolver
from core.llm.failures import ErrorObservation
from core.llm.providers import adapter_for
from core.llm.registry import ModelDescriptor, build_default_registry
from core.llm.retry import RetryPolicy
from core.llm.transports import TransportError, WireRequest, WireResponse
from core.llm.types import InvokeRequest, Message, Role


class RecordedTransport:
    """Replays queued documents, and records what was sent.

    Recording the requests matters as much as replaying the responses: half of
    what the contract suite asserts is that the *payload* an adapter builds is
    the shape its provider accepts, and that is only visible from here.
    """

    def __init__(
        self,
        responses: Iterable[Mapping[str, Any] | BaseException] = (),
        chunks: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self._responses: deque[Mapping[str, Any] | BaseException] = deque(responses)
        self._chunks = tuple(chunks)
        self.sent: list[WireRequest] = []
        self.streamed: list[WireRequest] = []

    @property
    def name(self) -> str:
        """Return this transport's identifier."""
        return "recorded"

    def queue(self, response: Mapping[str, Any] | BaseException) -> None:
        """Add one response to the back of the queue."""
        self._responses.append(response)

    @property
    def last_payload(self) -> Mapping[str, Any]:
        """Return the payload of the most recent request."""
        return self.sent[-1].payload

    async def send(self, request: WireRequest) -> WireResponse:
        """Return the next queued document, or raise the next queued failure."""
        self.sent.append(request)
        if not self._responses:
            raise AssertionError(
                f"{request.provider_id}: the adapter sent more requests than the "
                "cassette has responses for"
            )
        nxt = self._responses.popleft()
        if isinstance(nxt, BaseException):
            raise nxt
        return WireResponse(payload=nxt)

    async def stream(self, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
        """Yield the recorded chunks for a streamed request."""
        self.streamed.append(request)
        for chunk in self._chunks:
            yield chunk


def transport_failure(
    *,
    status_code: int | None = None,
    error_code: str | None = None,
    message: str = "",
    retry_after_seconds: float | None = None,
) -> TransportError:
    """Return a transport failure shaped like one a provider would produce."""
    return TransportError(
        ErrorObservation(
            status_code=status_code,
            error_code=error_code,
            message=message,
            retry_after_seconds=retry_after_seconds,
        )
    )


#: Credentials for every provider, so no test is skipped for want of one and
#: nothing here resembles a real key.
_TEST_CREDENTIALS = {
    provider_id: {
        "api_key": "test-key-not-a-real-credential",
        "endpoint": "https://example.invalid",
        "api_version": "2026-01-01",
        "deployment": "test-deployment",
        "region": "eu-west-1",
        "project": "test-project",
        "location": "europe-west1",
        "base_url": "https://example.invalid/v1",
    }
    for provider_id in SUPPORTED_PROVIDERS
}


def build_client(
    provider_id: str,
    *,
    transport: RecordedTransport,
    descriptor: ModelDescriptor | None = None,
    max_attempts: int = 3,
) -> ProviderClient:
    """Return a client for ``provider_id`` wired to ``transport``.

    Backoff is instant and jitter is pinned: a suite that sleeps for real is a
    suite people stop running, and one that cannot pin the jitter cannot assert
    the delay it computed.
    """
    registry = build_default_registry()
    resolved = descriptor or registry.default_for_provider(provider_id)

    async def _no_sleep(_seconds: float) -> None:
        return None

    return ProviderClient(
        adapter=adapter_for(provider_id),
        descriptor=resolved,
        transport=transport,
        credentials=StaticCredentialResolver(_TEST_CREDENTIALS),
        retry_policy=RetryPolicy(max_attempts=max_attempts, base_delay_seconds=0.01),
        jitter=lambda: 0.0,
        sleeper=_no_sleep,
    )


@pytest.fixture(params=SUPPORTED_PROVIDERS, name="provider_id")
def _provider_id(request: pytest.FixtureRequest) -> str:
    """Run each contract test against every supported provider."""
    return str(request.param)


@pytest.fixture(name="descriptor")
def _descriptor(provider_id: str) -> ModelDescriptor:
    return build_default_registry().default_for_provider(provider_id)


@pytest.fixture(name="transport")
def _transport(provider_id: str) -> RecordedTransport:
    return RecordedTransport(
        responses=[text_response(provider_id)],
        chunks=stream_chunks(provider_id),
    )


@pytest.fixture(name="client")
def _client(provider_id: str, transport: RecordedTransport) -> ProviderClient:
    return build_client(provider_id, transport=transport)


@pytest.fixture(name="simple_request")
def _simple_request() -> InvokeRequest:
    return InvokeRequest(
        messages=(Message(role=Role.USER, text="Why is checkout returning 503?"),),
        system="You are an SRE investigating a production incident.",
    )
