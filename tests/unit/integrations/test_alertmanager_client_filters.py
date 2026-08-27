"""An empty narrowing must not become a query the vendor rejects.

Alertmanager reads `filter` as a matcher and refuses an empty one with
`400 bad matcher format`. The client sent it unconditionally, so the ordinary
call — "what is firing", with nothing narrowed — was the one that failed. It
surfaced the first time this integration was pointed at a real Alertmanager
rather than at a recording, because a recording answers whatever it was given.
"""

from __future__ import annotations

from typing import Any

import pytest

from integrations._base.transport import ProxyTransport, RequestContext
from integrations.alertmanager.client import AlertmanagerClient
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

pytestmark = pytest.mark.unit


class _Recording(ProxyTransport):
    """Records the request and answers with an empty list."""

    def __init__(self) -> None:
        self.sent: list[ProxyRequest] = []

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        self.sent.append(request)
        return OutboundResponse(200, {"content-type": "application/json"}, b"[]")


def _client(transport: _Recording) -> AlertmanagerClient:
    return AlertmanagerClient(
        transport=transport,
        context=RequestContext(org_id="acme", team_id="payments", capability="probe"),
        base_url="http://alertmanager.example.com:9093",
    )


def _query(request: Any) -> str:
    return str(request.url).partition("?")[2]


async def test_asking_for_everything_sends_no_matcher() -> None:
    transport = _Recording()

    await _client(transport).list_incidents()

    assert "filter=" not in _query(transport.sent[0])


async def test_a_named_status_is_still_sent_as_a_matcher() -> None:
    transport = _Recording()

    await _client(transport).list_incidents(status='severity="critical"')

    assert "filter=" in _query(transport.sent[0])


async def test_the_timeline_omits_an_empty_matcher_too() -> None:
    transport = _Recording()

    await _client(transport).incident_timeline()

    assert "filter=" not in _query(transport.sent[0])


async def test_the_timeline_keeps_the_incident_it_was_given() -> None:
    transport = _Recording()

    await _client(transport).incident_timeline(incident='alertname="InstanceDown"')

    assert "filter=" in _query(transport.sent[0])


# --- A value that is not a matcher ------------------------------------------
#
# The two tests above pass matchers already formatted, and the client forwards
# them correctly. What a real investigation sends is not that. Measured against
# staging: the agent called the timeline with the deployment's own resource
# identifier and the statistics with the word "firing", and Alertmanager
# refused both with `400 bad matcher format`. Four calls out of four.
#
# The vendor's grammar is the client's business. An agent that has to know
# Alertmanager writes matchers as `name="value"` is an agent that will get it
# wrong, and being told afterwards costs the turn either way.


async def test_a_bare_value_becomes_a_matcher_the_vendor_accepts() -> None:
    transport = _Recording()

    await _client(transport).incident_timeline(incident="CronJobStale")

    query = _query(transport.sent[0])
    assert "alertname" in query, f"a bare name was forwarded unwrapped: {query}"
    assert "%3D" in query or "=" in query.partition("filter")[2]


async def test_an_identifier_the_vendor_cannot_know_is_not_sent_as_a_matcher() -> None:
    """Our resource ids mean nothing to Alertmanager, and it says so with a 400.

    Sending one as an ``alertname`` matcher would be just as wrong and would
    come back empty instead of refused — which is worse, because an empty
    answer reads as "there is nothing" rather than "you asked wrongly".
    """
    transport = _Recording()

    await _client(transport).incident_timeline(incident="res-7a73b8aa1194c1ed14dd87f7e0e80b81")

    assert "filter=" not in _query(transport.sent[0])


async def test_a_status_word_narrows_by_the_parameter_that_takes_it() -> None:
    """Alertmanager expresses status with booleans, never with a matcher."""
    transport = _Recording()

    await _client(transport).list_incidents(status="firing")

    query = _query(transport.sent[0])
    assert "filter=" not in query, f"a status word was sent as a matcher: {query}"
    assert "active=true" in query
