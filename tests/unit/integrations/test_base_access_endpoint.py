"""The binding carries where each vendor is, so no tool has to know.

A hundred and ninety-three vendor tool modules call ``access.client(...)`` and
none of them can be asked to look up an address first: a tool that resolved its
own configuration is the tool that acts on somebody else's estate. So the
binding resolves it once, and a client is built pointed at the operator's own
instance without a single tool module changing.
"""

from __future__ import annotations

from integrations._base.access import IntegrationAccess
from integrations._base.transport import ProxyTransport
from integrations.alertmanager.client import AlertmanagerClient
from integrations.prometheus.client import PrometheusClient


class _Transport(ProxyTransport):
    """A transport nothing calls: these tests only ask what a client addresses."""

    async def send(self, request: object) -> object:  # pragma: no cover - never called
        raise AssertionError("no test here makes a call")


def _access(**endpoints: str) -> IntegrationAccess:
    return IntegrationAccess(
        transport=_Transport(), org_id="acme", team_id="_org", endpoints=endpoints
    )


def test_a_client_addresses_the_endpoint_the_operator_configured() -> None:
    access = _access(alertmanager="http://10.20.20.36:9093")

    client = access.client(AlertmanagerClient, capability="alertmanager_incident_statistics")

    assert client.base_url == "http://10.20.20.36:9093/"


def test_a_vendor_with_no_configured_endpoint_falls_back_to_its_own_region() -> None:
    """Refusing to build one would take the catalogue offline for the unconfigured."""
    access = _access(alertmanager="http://10.20.20.36:9093")

    client = access.client(PrometheusClient, capability="prometheus_metric_query")

    assert client.base_url == "https://prometheus.example.com/"


def test_a_caller_that_names_an_address_itself_is_not_overridden() -> None:
    """The verifier passes one to probe what was just entered, before it is stored."""
    access = _access(alertmanager="http://10.20.20.36:9093")

    client = access.client(
        AlertmanagerClient,
        capability="alertmanager_incident_statistics",
        base_url="http://somewhere.else:9093",
    )

    assert client.base_url == "http://somewhere.else:9093/"


def test_a_binding_with_no_endpoints_behaves_as_it_always_did() -> None:
    access = IntegrationAccess(transport=_Transport(), org_id="acme", team_id="_org")

    client = access.client(AlertmanagerClient, capability="alertmanager_incident_statistics")

    assert client.base_url == "https://alertmanager.example.com/"
