"""The transport demo mode installs, and the reason it raises rather than falls back.

FR-018 says every provider response in demo mode comes from a fixture. A
transport that served fixtures where it had one and made a real call where it
did not would satisfy that requirement on the day it was written and stop
satisfying it the first time somebody added a prompt the fixture set does not
cover — quietly, because a working demonstration and a demonstration that is
spending money look identical from the outside.

So this raises. A demonstration that cannot answer from the recording is a
demonstration with a gap in it, and the gap is a thing to fix rather than a
thing to paper over with a live call.

It is a real ``WireTransport``: same protocol the SDK and LiteLLM transports
satisfy, so it is substituted at composition rather than special-cased anywhere
in the client. Nothing downstream knows it is talking to a recording, which is
what makes the demonstration exercise the real path.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from config.constants.first_run import NINJASRE_DEMO_MODE_ENV
from core.llm.transports import WireRequest, WireResponse

#: Values that mean yes, matching the startup validator's own reading so a
#: deployment cannot be half in demo mode.
_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes", "on"})

TRANSPORT_NAME = "demonstration-fixture"


class RealRequestInDemoMode(RuntimeError):
    """Something tried to reach a provider while demo mode was on.

    A hard failure rather than a warning. In a test this fails the test, which
    is SC-008; in a running demonstration it fails the request, which is the
    only outcome that cannot quietly become a bill.
    """

    def __init__(self, request: WireRequest, *, known: Sequence[str] = ()) -> None:
        listed = f" Recorded exchanges: {', '.join(known[:4])}." if known else ""
        super().__init__(
            f"demo mode has no recorded response for {request.provider_id}/{request.model_id}, "
            f"and refuses to make a real call to get one. Record the exchange into the "
            f"fixture set, or turn demo mode off.{listed}"
        )
        self.provider_id = request.provider_id
        self.model_id = request.model_id


def demo_mode_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether this deployment is serving a demonstration."""
    import os

    source = environ if environ is not None else os.environ
    return source.get(NINJASRE_DEMO_MODE_ENV, "").strip().lower() in _TRUTHY


def exchange_key(request: WireRequest) -> str:
    """Return the key a recorded response is filed under.

    A hash of the provider, the model and the payload, so the same request finds
    the same recording and a *different* request finds nothing rather than
    finding something close enough to be misleading.
    """
    material = json.dumps(
        {
            "provider": request.provider_id,
            "model": request.model_id,
            "payload": _canonical(request.payload),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _canonical(payload: Mapping[str, Any]) -> Any:
    """Return the payload with the parts that vary between runs removed.

    A request identical in everything that matters should hit the same recording
    whatever the request id or timestamp attached to it happened to be.
    """
    return {
        key: value
        for key, value in sorted(payload.items())
        if key not in {"request_id", "timestamp", "user"}
    }


class FixtureTransport:
    """Serves recorded provider responses, and raises on anything else.

    ``responses`` is keyed by ``exchange_key``. ``fallback`` is the one recorded
    answer used when a request matches nothing — supplied deliberately by a
    caller that wants a demonstration to be able to answer anything, and absent
    by default, because the safe direction for "we have no recording" is to
    refuse.
    """

    __slots__ = ("_fallback", "_responses", "_seen")

    def __init__(
        self,
        responses: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        fallback: Mapping[str, Any] | None = None,
    ) -> None:
        self._responses = dict(responses or {})
        self._fallback = fallback
        self._seen: list[str] = []

    @property
    def name(self) -> str:
        """Return the transport identifier used in configuration and traces."""
        return TRANSPORT_NAME

    @property
    def calls(self) -> tuple[str, ...]:
        """Return every exchange key this transport was asked for, in order."""
        return tuple(self._seen)

    def record(self, request: WireRequest, payload: Mapping[str, Any]) -> str:
        """File ``payload`` as the answer to ``request``, and return its key."""
        key = exchange_key(request)
        self._responses[key] = dict(payload)
        return key

    async def send(self, request: WireRequest) -> WireResponse:
        """Return the recorded response, or refuse.

        Raises:
            RealRequestInDemoMode: nothing was recorded for this request.
        """
        key = exchange_key(request)
        self._seen.append(key)
        recorded = self._responses.get(key, self._fallback)
        if recorded is None:
            raise RealRequestInDemoMode(request, known=tuple(self._responses))
        return WireResponse(payload=dict(recorded))

    async def stream(self, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
        """Yield the recorded response as a single chunk, or refuse.

        One chunk rather than a simulated token stream: what a demonstration
        needs to show streaming is the *run* event stream, which
        ``demo.scripted`` produces, and pretending to stream tokens here would
        add a second fiction with nothing behind it.
        """
        response = await self.send(request)
        yield response.payload


__all__ = [
    "TRANSPORT_NAME",
    "FixtureTransport",
    "RealRequestInDemoMode",
    "demo_mode_enabled",
    "exchange_key",
]
