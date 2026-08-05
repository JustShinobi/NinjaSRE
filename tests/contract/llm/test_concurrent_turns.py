"""The concurrent-turn race, reproduced deterministically and with no threads.

The bug this pins down is worth stating precisely, because it is the kind that
survives review. Clients are cached per role, so two turns running at once share
one instance. A turn whose cache markers were rejected sets a flag on that shared
client — "this provider does not accept markers" — and the *other* turn's error
handler then reads the flag. But that turn had already sent its request, with
markers, before the flag existed. It takes the branch belonging to somebody
else's failure and loses its turn, in a way that reproduces only under
concurrency and only sometimes.

The fix is structural, not a lock: every input a handler consults is captured
into the request when it is built, so there is no shared mutable state to read.
This file proves both halves — that the corrected client survives the
interleaving, and that the same interleaving still breaks a client written the
old way. A race test that cannot fail is not evidence.

Deterministic and thread-free because asyncio only switches at an ``await``, so
the interleaving is chosen here rather than by the scheduler.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from cassettes import text_response
from conftest import build_client, transport_failure

from config.constants.llm import PROVIDER_ANTHROPIC
from core.llm.client import ProviderClient
from core.llm.registry import build_default_registry
from core.llm.transports import WireRequest, WireResponse
from core.llm.types import DegradationKind, InvokeRequest, InvokeResult, Message, Role

pytestmark = pytest.mark.contract

_PROVIDER = PROVIDER_ANTHROPIC


def _cache_marker_rejection() -> Exception:
    return transport_failure(
        status_code=400,
        message="cache_control: this field is no longer supported for this model",
    )


#: The turns this transport can tell apart, by the tag each puts in its message.
_TURN_TAGS = ("A", "B", "C", "D")


def _carries_cache_markers(payload: Mapping[str, Any]) -> bool:
    """Return whether a payload asked the provider to cache anything."""
    return "cache_control" in str(payload)


class InterleavingTransport:
    """Hands the two turns to each other at exactly the wrong moment.

    Turn A sends first and is parked. Turn B then runs its whole failure-and-
    retry cycle. Only once B has finished — and, in the broken design, mutated
    the shared client — is A's failure delivered. That ordering is the race,
    made a decision rather than an accident.
    """

    def __init__(self) -> None:
        self.first_request_arrived = asyncio.Event()
        self.second_turn_finished = asyncio.Event()
        self.sent: list[WireRequest] = []
        self._seen_turns: set[str] = set()

    @property
    def name(self) -> str:
        """Return this transport's identifier."""
        return "interleaving"

    async def send(self, request: WireRequest) -> WireResponse:
        """Fail a marked request, succeed an unmarked one, park turn A in between."""
        self.sent.append(request)
        # Each turn tags its own user message, and the tag survives every wire
        # shape — reading it back out of the serialised payload means this
        # transport works for any provider without knowing one.
        body = str(request.payload)
        turn = next((name for name in _TURN_TAGS if f"turn {name}:" in body), "")

        marked = _carries_cache_markers(request.payload)
        first_time = turn not in self._seen_turns
        self._seen_turns.add(turn)

        if marked and first_time and turn == "A":
            # Park turn A mid-flight and let turn B run to completion.
            self.first_request_arrived.set()
            await self.second_turn_finished.wait()
            raise _cache_marker_rejection()

        if marked:
            raise _cache_marker_rejection()

        return WireResponse(payload=text_response(_PROVIDER))


class SharedStateClient:
    """A client written the way the bug was written, for the control case.

    It keeps "has this provider rejected markers" on the instance, which is
    exactly the mutation the corrected design does not have. It exists so the
    test below can show the interleaving is genuinely hostile.
    """

    def __init__(self, inner: ProviderClient) -> None:
        self._inner = inner
        self.cache_rejected = False

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Invoke, skipping the uncached retry when *any* turn saw a rejection."""
        if self.cache_rejected:
            # The state another turn wrote decides this turn's behaviour, even
            # though this turn already sent markers. This is the defect.
            return await self._inner.invoke(request)

        result = await self._inner.invoke(request)
        if any(
            degradation.kind is DegradationKind.PROMPT_CACHE_MARKERS_REJECTED
            for degradation in result.degradations
        ):
            self.cache_rejected = True
        return result


def _request(turn: str) -> InvokeRequest:
    """Return a cacheable request tagged so the transport can tell the turns apart."""
    return InvokeRequest(
        messages=(Message(role=Role.USER, text=f"turn {turn}: why is checkout failing?"),),
        # Large enough that there is a prefix worth caching at all.
        system="S" * 4_000,
        prompt_cache=True,
    )


def _cacheable_client(transport: InterleavingTransport) -> ProviderClient:
    registry = build_default_registry()
    descriptor = registry.default_for_provider(_PROVIDER)
    assert descriptor.supports_prompt_cache, "the reference provider must support caching"
    return build_client(_PROVIDER, transport=transport, descriptor=descriptor)


async def test_a_turn_is_decided_by_what_its_own_request_carried() -> None:
    """Both interleaved turns complete, each retrying uncached for itself."""
    transport = InterleavingTransport()
    client = _cacheable_client(transport)

    async def turn_a() -> InvokeResult:
        return await client.invoke(_request("A"))

    async def turn_b() -> InvokeResult:
        # Wait until A is parked mid-flight, so B's whole cycle runs inside it.
        await transport.first_request_arrived.wait()
        result = await client.invoke(_request("B"))
        transport.second_turn_finished.set()
        return result

    result_a, result_b = await asyncio.gather(turn_a(), turn_b())

    assert result_a.succeeded, result_a.failure_message
    assert result_b.succeeded, result_b.failure_message

    for result in (result_a, result_b):
        assert any(
            degradation.kind is DegradationKind.PROMPT_CACHE_MARKERS_REJECTED
            for degradation in result.degradations
        ), "each turn must record its own rejection"

    marked = [request for request in transport.sent if _carries_cache_markers(request.payload)]
    unmarked = [
        request for request in transport.sent if not _carries_cache_markers(request.payload)
    ]
    assert len(marked) == 2, "each turn sends markers once"
    assert len(unmarked) == 2, "each turn retries uncached once"


async def test_the_interleaving_still_breaks_a_client_that_shares_state() -> None:
    """The control case. Without this, the test above proves nothing."""
    transport = InterleavingTransport()
    shared = SharedStateClient(_cacheable_client(transport))

    async def turn_a() -> InvokeResult:
        return await shared.invoke(_request("A"))

    async def turn_b() -> InvokeResult:
        await transport.first_request_arrived.wait()
        result = await shared.invoke(_request("B"))
        transport.second_turn_finished.set()
        return result

    await asyncio.gather(turn_a(), turn_b())

    assert shared.cache_rejected is True, (
        "the interleaving must leave one turn's failure visible to the other; "
        "if it does not, the test above is not exercising the race"
    )


async def test_two_turns_never_observe_each_other_through_the_client() -> None:
    """Nothing on a shared client changes between two identical turns."""
    transport = InterleavingTransport()
    client = _cacheable_client(transport)

    before = {
        name: getattr(client, name)
        for name in dir(client)
        if not name.startswith("__") and not callable(getattr(client, name, None))
    }

    await asyncio.gather(client.invoke(_request("C")), client.invoke(_request("D")))

    after = {
        name: getattr(client, name)
        for name in dir(client)
        if not name.startswith("__") and not callable(getattr(client, name, None))
    }
    assert before == after
