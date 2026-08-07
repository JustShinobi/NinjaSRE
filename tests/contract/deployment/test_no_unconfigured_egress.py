"""SC-008: a full investigation, watched at the socket, reaching nothing unconfigured.

The claim Article X makes is observable or it is nothing, so this observes it.
Every ``socket.connect`` the process attempts is recorded — at the socket, below
every client library, so nothing routes round the monitor by using a different
one — and a complete investigation runs inside the recording.

The investigation is the real one: the canonical ReAct loop, the pipeline, the
capability catalogue, the credential proxy, and a vendor stack, driven against a
scripted provider. Offline is not a weaker version of this test; it is the point.
A deployment configured with a local model and no other endpoint has no reason to
open a socket at all, and this is what "no reason" means as an assertion.

The monitor is deliberately not a mock of anything. It wraps the real
``socket.socket.connect``, so a connection that did happen is recorded whoever
made it — including one made by a library nobody in this repository wrote.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

from config.constants.deployment import (
    NINJASRE_AIR_GAPPED_ENV,
    NINJASRE_EGRESS_ALLOWLIST_ENV,
)
from config.constants.llm import NINJASRE_LLM_PROVIDER_ENV, OLLAMA_BASE_URL_ENV
from config.constants.persistence import NINJASRE_DATABASE_URL_ENV
from platform.startup.egress import external_destinations, unexpected
from tests.harness.loader import Scenario
from tests.harness.runner import run_scenario
from tests.unit.harness.test_runner import scripted

pytestmark = pytest.mark.contract

#: An air-gapped standard deployment: one database, one local model, no egress.
AIR_GAPPED = {
    NINJASRE_DATABASE_URL_ENV: "postgresql://ninjasre@postgres:5432/ninjasre",
    NINJASRE_LLM_PROVIDER_ENV: "ollama",
    OLLAMA_BASE_URL_ENV: "http://ollama:11434/v1",
    NINJASRE_AIR_GAPPED_ENV: "true",
}


class ConnectionMonitor:
    """Records every outbound connection the process attempts.

    Wraps ``socket.socket.connect`` rather than any client's own hook, because
    the guarantee is about the process and not about the libraries this
    repository happens to use. Connections are recorded and then allowed: a
    monitor that blocked would be testing the monitor.
    """

    def __init__(self) -> None:
        self.addresses: list[str] = []

    def record(self, address: Any) -> None:
        """Record one connection attempt, whatever address family it used."""
        if isinstance(address, tuple) and address:
            self.addresses.append(str(address[0]))
        else:
            self.addresses.append(str(address))

    @property
    def hosts(self) -> tuple[str, ...]:
        """Return the distinct hosts this process reached, in the order it reached them."""
        seen: dict[str, None] = {}
        for address in self.addresses:
            seen.setdefault(address, None)
        return tuple(seen)


@pytest.fixture
def monitor(monkeypatch: pytest.MonkeyPatch) -> Iterator[ConnectionMonitor]:
    """Watch every socket this process opens for the duration of a test."""
    watcher = ConnectionMonitor()
    original = socket.socket.connect

    def watched(self: socket.socket, address: Any) -> None:
        watcher.record(address)
        original(self, address)

    monkeypatch.setattr(socket.socket, "connect", watched)
    yield watcher


def test_the_monitor_sees_a_connection_when_there_is_one(monitor: ConnectionMonitor) -> None:
    """A monitor that saw nothing because it was broken would pass every test below."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        client = socket.socket()
        client.connect(listener.getsockname())
        client.close()
    finally:
        listener.close()

    assert "127.0.0.1" in monitor.hosts


async def test_a_full_investigation_opens_no_socket_at_all(
    runnable_scenario: Scenario,
    monitor: ConnectionMonitor,
) -> None:
    """SC-005 and SC-008 together: the whole stack, offline, reaching nothing."""
    run = await run_scenario(runnable_scenario, llm=scripted(runnable_scenario))

    assert run.run is not None, "the investigation has to have actually happened"
    assert monitor.hosts == (), f"the investigation reached {monitor.hosts}"


async def test_nothing_the_investigation_reached_was_unconfigured(
    runnable_scenario: Scenario,
    monitor: ConnectionMonitor,
) -> None:
    """The general form: whatever it reached, the configuration had to have named it."""
    await run_scenario(runnable_scenario, llm=scripted(runnable_scenario))

    assert unexpected(monitor.hosts, AIR_GAPPED) == ()


def test_an_air_gapped_configuration_permits_no_destination_off_the_host() -> None:
    """The configuration half of the same claim, checked without running anything."""
    assert external_destinations(AIR_GAPPED) == ()


def test_a_connection_the_operator_did_permit_is_not_a_finding() -> None:
    """The monitor must not be a burglar alarm that goes off for the postman."""
    environ = AIR_GAPPED | {NINJASRE_EGRESS_ALLOWLIST_ENV: "api.pagerduty.com"}

    assert unexpected(["api.pagerduty.com", "postgres"], environ) == ()


def test_a_connection_nobody_permitted_is_reported_with_its_host() -> None:
    assert unexpected(["metrics.vendor.example"], AIR_GAPPED) == ("metrics.vendor.example",)
