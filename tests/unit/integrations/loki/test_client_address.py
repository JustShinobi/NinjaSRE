"""Pointing the Loki client at the Loki this deployment actually runs.

``loki.example.com`` is a placeholder — nobody packaging this knows where a
self-hosted Loki is — and the client could only be built from the region map, so
every query went to a host that does not resolve. The same defect the metrics
client had, and the same fix: the operator's configured address wins, and the
egress allow-list still decides whether the host may be reached at all.
"""

from __future__ import annotations

import pytest

from integrations.loki.client import LokiClient

pytestmark = pytest.mark.unit


def _client(**overrides: object) -> LokiClient:
    from integrations._base.transport import RequestContext

    class _Transport:
        async def send(self, *_: object, **__: object) -> object:
            raise AssertionError("this test never sends")

    return LokiClient(
        transport=_Transport(),  # type: ignore[arg-type]
        context=RequestContext(org_id="acme", team_id="team", capability="logs.read"),
        **overrides,  # type: ignore[arg-type]
    )


def test_a_configured_address_wins_over_the_shipped_placeholder() -> None:
    # Compared without the trailing slash the transport normalises onto it.
    configured = _client(base_url="https://loki.lan.example").base_url

    assert configured.rstrip("/") == "https://loki.lan.example"


def test_a_deployment_that_configured_nothing_still_gets_the_region_default() -> None:
    """Configuring none is the ordinary state before an operator points it anywhere."""
    from integrations.loki.schema import base_url

    assert _client().base_url.rstrip("/") == base_url("").rstrip("/")
