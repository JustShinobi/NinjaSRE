"""SC-008. Demo mode reaches nothing, proved by making it impossible to.

Two guards, because they fail differently and both failures have happened to
somebody. The socket guard catches *any* outbound connection, from any library,
including one added by a dependency nobody here wrote. The fixture transport
catches the specific case the socket guard cannot distinguish — a provider call
that would have been legitimate on a non-demonstration deployment — and turns it
into a message that names the missing recording.

The socket guard is installed at the lowest point that still leaves the test
readable: ``socket.socket.connect``. Above it, an HTTP client's own
"no requests" flag is a flag somebody can forget to set; below it, the test is
asserting about the operating system.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

from core.llm.credentials import ProviderCredentials
from core.llm.transports import WireRequest
from platform.persistence.fakes import FakePersistence
from platform.startup.demo import (
    FixtureTransport,
    RealRequestInDemoMode,
    demonstration_residue,
    load_dataset,
    remove_demonstration,
    seed_demonstration,
    stream_scripted_investigation,
)

pytestmark = pytest.mark.security


class OutboundConnectionInDemoMode(AssertionError):
    """Something opened a socket while a demonstration was running."""


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make every outbound connection fail the test, whoever attempts it."""

    def refuse(self: socket.socket, address: Any) -> None:
        raise OutboundConnectionInDemoMode(
            f"demo mode opened a socket to {address!r}. Every response must come from a fixture."
        )

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    yield


async def test_the_whole_demonstration_runs_without_opening_a_socket(
    no_network: None,
) -> None:
    """Load it, stream it, sweep it, remove it. Nothing reaches anything."""
    store = FakePersistence()
    dataset = load_dataset()

    report = await seed_demonstration(store, dataset=dataset)
    assert report.total > 100

    events = [event async for event in stream_scripted_investigation(dataset, interval_seconds=0)]
    assert events

    assert await demonstration_residue(store) != ()
    await remove_demonstration(store)
    assert await demonstration_residue(store) == ()


async def test_a_provider_call_in_demo_mode_fails_the_test_rather_than_going_out(
    no_network: None,
) -> None:
    """The transport is the second guard, and this is what it is for: a message
    naming the missing recording, rather than a connection error from a socket
    the test happened to have blocked."""
    transport = FixtureTransport()

    with pytest.raises(RealRequestInDemoMode):
        await transport.send(
            WireRequest(
                provider_id="anthropic",
                model_id="claude-opus-5",
                payload={"messages": [{"role": "user", "content": "diagnose this"}]},
                credentials=ProviderCredentials(provider_id="anthropic", values={}),
            )
        )


async def test_the_guard_would_notice_a_call(no_network: None) -> None:
    """A guard that never fires proves nothing. This is the test that it fires."""
    with pytest.raises(OutboundConnectionInDemoMode):
        socket.socket().connect(("example.invalid", 443))
