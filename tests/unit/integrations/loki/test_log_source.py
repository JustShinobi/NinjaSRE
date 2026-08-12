"""Loki as the bridge's ``LogSource``, which nothing implemented.

``LogSource`` declared what an investigation needs of a log system, ``LokiClient``
could already query one, and no type joined them — so a deployment with Loki
configured and reachable answered every log question with "no source composed".
The client and the port were both right and there was nothing between them.

Two properties this has to get right, because both failures are silent:

**Loki's timestamps are nanoseconds since the epoch, as strings.** Read as
seconds, every line lands in the year 1970 and sorts before anything real; read
as milliseconds, in the wrong century. The window in the answer would still look
plausible.

**A stream's labels belong to the stream, not the line.** Loki returns one
``values`` array per stream with the labels beside it, so flattening without
carrying the labels down loses which guest each line came from.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from integrations.loki.log_source import LokiLogSource, lines_of

pytestmark = pytest.mark.unit

START = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
END = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)

#: One stream as Loki returns it: labels once, then [nanoseconds, line] pairs.
STREAM = {
    "stream": {"job": "proxmox-syslog", "host": "pve01"},
    "values": [
        ["1786525200000000000", "pve-container@100: started"],  # START
        ["1786525260000000000", "pve-container@100: stopped"],  # a minute later
    ],
}


def test_a_streams_labels_travel_with_every_line_it_returned() -> None:
    """Flattened without them, nobody can tell which guest a line is about."""
    found = lines_of((STREAM,))

    assert [line.line for line in found] == [
        "pve-container@100: started",
        "pve-container@100: stopped",
    ]
    assert all(line.labels["host"] == "pve01" for line in found)


def test_a_nanosecond_timestamp_is_read_as_nanoseconds() -> None:
    """Read as seconds it lands in 1970, and the window still looks plausible."""
    found = lines_of((STREAM,))

    assert found[0].observed_at == START
    assert found[0].observed_at.tzinfo is UTC


def test_a_line_whose_timestamp_is_unreadable_is_dropped_not_dated_now() -> None:
    """Stamping it with the current time makes a stale line look live, which is
    the one reading that changes an operator's conclusion."""
    assert lines_of(({"stream": {}, "values": [["not a number", "a line"]]},)) == ()


def test_a_malformed_entry_is_dropped_rather_than_raised() -> None:
    """A vendor's payload is not a schema this can rely on."""
    assert lines_of(({"stream": {}, "values": [["1786604400000000000"], [], "not a pair"]},)) == ()


async def test_reading_a_window_asks_loki_for_exactly_that_window() -> None:
    """The bound in the answer has to be the window actually read."""

    class _Client:
        def __init__(self) -> None:
            self.asked: dict[str, object] = {}

        async def search_logs(self, query: str = "", **parameters: object) -> object:
            self.asked = {"query": query, **parameters}

            class _Pages:
                items = (STREAM,)

            return _Pages()

    client = _Client()
    found = await LokiLogSource(client=client).lines(  # type: ignore[arg-type]
        selector='{job="proxmox-syslog"}', start=START, end=END, limit=50
    )

    assert client.asked["query"] == '{job="proxmox-syslog"}'
    # Nanoseconds, which is what Loki's range endpoint takes.
    assert client.asked["start"] == str(int(START.timestamp() * 1_000_000_000))
    assert client.asked["end"] == str(int(END.timestamp() * 1_000_000_000))
    assert client.asked["limit"] == 50
    assert len(found) == 2


async def test_a_source_that_did_not_answer_is_unreachable_not_empty() -> None:
    """An empty answer means "nothing matched", which leads a responder to the
    opposite conclusion from "we could not ask".

    Raised as this package's own error, never the observability bridge's: an
    integration that imported the bridge would make an optional feature
    mandatory. The gateway translates at the seam."""
    from integrations._base.errors import IntegrationError

    class _Broken:
        async def search_logs(self, query: str = "", **parameters: object) -> object:
            raise RuntimeError("connection refused")

    with pytest.raises(IntegrationError):
        await LokiLogSource(client=_Broken()).lines(  # type: ignore[arg-type]
            selector="{}", start=START, end=END, limit=10
        )


async def test_loki_declares_no_retention_so_the_answer_carries_its_own_bound() -> None:
    """Zero is "it has no opinion", not "it keeps nothing" — the bridge's own
    reading, and Loki genuinely publishes no retention over its HTTP API."""
    assert await LokiLogSource(client=object()).retention_seconds() == 0  # type: ignore[arg-type]


def test_the_adapter_satisfies_the_port_the_bridge_asks_for() -> None:
    """The joint this whole module exists to close."""
    from platform.observation.bridge.ports import LogSource

    assert isinstance(LokiLogSource(client=object()), LogSource)  # type: ignore[arg-type]
