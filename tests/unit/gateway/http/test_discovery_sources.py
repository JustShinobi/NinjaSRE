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

import pytest

from gateway.http.discovery_sources import compose_discovery_sources

pytestmark = pytest.mark.unit


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


class _State:
    """Only what the composer touches."""

    def __init__(self) -> None:
        self.gateway = object()
        self.discovery_sources: dict[str, object] = {}
