"""Composing the discovery sources a deployment's configuration points at.

The defect this covers: ``discovery_sources`` was a field with a default of
``{}`` and no assignment anywhere in the codebase. Every piece behind it
existed — the Proxmox client, the sweep, the enricher — and the route answered
"no discovery source is composed" to a deployment whose credential was stored,
whose integration was active, and whose endpoint was configured.

It is resolved from the configuration tree at start-up rather than from the
environment, and for the reason the change sources give: which cluster a
deployment watches is a fact about the estate, and the estate's facts are
edited where there is provenance, a preview and an audit row.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from gateway.http.discovery_sources import compose_discovery_sources, compose_signal_sources
from integrations.proxmox import bridge_readings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_bridge_binding() -> Iterator[None]:
    bridge_readings.clear()
    yield
    bridge_readings.clear()


class _Config:
    """Whatever the configuration tree resolves to, as the composer reads it."""

    def __init__(self, active: list[dict[str, object]]) -> None:
        self.active = active


async def test_an_active_integration_with_an_endpoint_is_composed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: a configured cluster becomes a source the route can find."""
    from gateway.http import discovery_sources as module

    async def resolved(_state: object, _org: str) -> tuple[dict[str, object], ...]:
        return (
            {
                "name": "proxmox",
                "enabled": True,
                "base_url": "https://pve.example.invalid:8006/",
            },
        )

    monkeypatch.setattr(module, "_active_integrations", resolved)

    state = _State()
    composed = await compose_discovery_sources(state, org_id="acme", proxy_url="http://127.0.0.1:1")

    assert set(composed) == {"proxmox"}
    assert set(state.discovery_sources) == {"proxmox"}

    # The credential was stored under the organisation-wide handle, because the
    # token that wrote it held no team. A sweep that asked for the empty team
    # would build a handle the grammar refuses and be turned away by the proxy.
    from config.constants.security import CREDENTIAL_ORG_WIDE_TEAM

    context = composed["proxmox"].client._context  # noqa: SLF001 — the point of the test
    assert context.team_id == CREDENTIAL_ORG_WIDE_TEAM


def test_the_endpoint_is_a_bare_host_because_the_client_adds_the_port() -> None:
    """A Proxmox base URL is built as https://{host}:{port}/api2/json.

    Handing it a host that already carries a port produced
    https://192.168.68.159:8006:8006/... — a name no resolver has, reported as
    "Name does not resolve" rather than as the configuration mistake it is.
    """
    from gateway.http.discovery_sources import _endpoints

    assert _endpoints("https://192.168.68.159:8006/") == ("192.168.68.159",)
    assert _endpoints("https://pve.lan.example:8006") == ("pve.lan.example",)
    assert _endpoints("http://pve.lan.example") == ("pve.lan.example",)
    assert _endpoints("") == ()


async def test_an_integration_that_is_switched_off_is_not_composed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled means disabled. A source built anyway would sweep a cluster
    somebody deliberately stopped watching."""
    from gateway.http import discovery_sources as module

    async def resolved(_state: object, _org: str) -> tuple[dict[str, object], ...]:
        return ({"name": "proxmox", "enabled": False, "base_url": "https://pve.invalid/"},)

    monkeypatch.setattr(module, "_active_integrations", resolved)

    state = _State()
    composed = await compose_discovery_sources(state, org_id="acme", proxy_url="http://127.0.0.1:1")

    assert composed == {}


async def test_an_integration_with_no_endpoint_is_skipped_and_said_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client pointed nowhere would fail at the first sweep rather than here."""
    from gateway.http import discovery_sources as module

    async def resolved(_state: object, _org: str) -> tuple[dict[str, object], ...]:
        return ({"name": "proxmox", "enabled": True, "base_url": ""},)

    monkeypatch.setattr(module, "_active_integrations", resolved)

    state = _State()
    composed = await compose_discovery_sources(state, org_id="acme", proxy_url="http://127.0.0.1:1")

    assert composed == {}


async def test_a_deployment_with_no_credential_proxy_composes_nothing() -> None:
    """A source reaches its vendor through the proxy and never around it."""
    state = _State()
    composed = await compose_discovery_sources(state, org_id="acme", proxy_url="")

    assert composed == {}


async def test_a_configuration_that_cannot_be_read_does_not_stop_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The console somebody would fix it from is served by this same process."""
    from gateway.http import discovery_sources as module

    async def refuse(_state: object, _org: str) -> tuple[dict[str, object], ...]:
        raise RuntimeError("the configuration tree is unreadable")

    monkeypatch.setattr(module, "_active_integrations", refuse)

    state = _State()
    composed = await compose_discovery_sources(state, org_id="acme", proxy_url="http://127.0.0.1:1")

    assert composed == {}


async def test_composing_signal_sources_binds_the_node_reader_a_tool_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect this covers: a node-health tool needs a real reader bound,
    and nothing bound one — every deployment's bridge reading was ``None``,
    always."""
    from gateway.http import discovery_sources as module

    async def resolved(_state: object, _org: str) -> tuple[dict[str, object], ...]:
        return ({"name": "prometheus", "enabled": True, "base_url": "http://10.20.20.37:9090"},)

    async def no_schedule(_state: object, *, org_id: str) -> object:
        return object()

    monkeypatch.setattr(module, "_active_integrations", resolved)
    monkeypatch.setattr(module, "schedule_observation_tick", no_schedule)

    state = _State()
    await compose_signal_sources(state, org_id="acme", proxy_url="http://127.0.0.1:1")

    assert bridge_readings.current() is not None


async def test_composing_signal_sources_with_nothing_configured_binds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway.http import discovery_sources as module

    async def resolved(_state: object, _org: str) -> tuple[dict[str, object], ...]:
        return ()

    monkeypatch.setattr(module, "_active_integrations", resolved)

    state = _State()
    await compose_signal_sources(state, org_id="acme", proxy_url="http://127.0.0.1:1")

    assert bridge_readings.current() is None


async def test_composing_signal_sources_with_no_proxy_binds_nothing() -> None:
    state = _State()
    await compose_signal_sources(state, org_id="acme", proxy_url="")

    assert bridge_readings.current() is None


class _State:
    """Only what the composer touches."""

    def __init__(self) -> None:
        self.gateway = object()
        self.discovery_sources: dict[str, object] = {}
        self.signal_sources: tuple[object, ...] = ()
