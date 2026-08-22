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
