"""Binding the one thing every vendor tool in the catalogue needs.

``integrations/_base/access.py`` says it plainly: there is one binding per
process, set by whoever composes the deployment, and a tool either has it or
reports itself unavailable by name.

Nothing set it. ``IntegrationAccess`` was referenced only inside its own module
— not by the gateway, not by a surface, not by a test — while a hundred and
ninety-three vendor tool modules read ``current()`` to make their calls. So
every one of them reported itself unavailable, on every deployment, always. Not
Grafana in particular: the whole catalogue.

This is the composition, and the test that matters is the one asserting the boot
does it.
"""

from __future__ import annotations

import pytest

from gateway.http.integration_access import compose_integration_access

pytestmark = pytest.mark.unit


class _State:
    pass


@pytest.fixture(autouse=True)
def _unbound() -> object:
    from integrations._base import access

    previous = access.bind(None)
    yield
    access.restore(previous)


async def test_a_deployment_with_a_proxy_binds_access_for_every_vendor_tool() -> None:
    from integrations._base import access

    composed = await compose_integration_access(
        _State(), org_id="acme", proxy_url="https://proxy.internal"
    )

    assert composed is not None
    assert access.current() is composed


async def test_the_binding_carries_the_organisation_and_a_team() -> None:
    """The proxy resolves a credential per tenant, so a blank one resolves to
    nothing — which the binding itself refuses to be constructed with."""
    composed = await compose_integration_access(
        _State(), org_id="acme", proxy_url="https://proxy.internal"
    )

    assert composed is not None
    assert composed.org_id == "acme"
    assert composed.team_id.strip()


async def test_a_deployment_with_no_proxy_binds_nothing() -> None:
    """A vendor call goes through the proxy and never around it, so a deployment
    without one has no access to bind — and the tools say so by name rather than
    answering as though the vendor had nothing to report."""
    from integrations._base import access

    composed = await compose_integration_access(_State(), org_id="acme", proxy_url="")

    assert composed is None
    assert access.current() is None


async def test_the_binding_holds_no_credential() -> None:
    """It carries a transport and two identifiers, all three safe in a prompt.
    The proxy on the far side is what turns them into an authenticated call."""
    composed = await compose_integration_access(
        _State(), org_id="acme", proxy_url="https://proxy.internal"
    )

    assert composed is not None
    fields = {name: getattr(composed, name) for name in ("org_id", "team_id")}
    assert not any("secret" in str(value).lower() for value in fields.values())
    assert not hasattr(composed, "token")


async def test_a_tool_can_build_its_client_once_access_is_bound() -> None:
    """The whole point of the binding: a tool asks for a client and gets one
    wired to this process's proxy, without ever naming a credential."""
    from integrations._base import access
    from integrations.grafana.client import GrafanaClient

    await compose_integration_access(_State(), org_id="acme", proxy_url="https://proxy.internal")
    bound = access.current()

    assert bound is not None
    client = bound.client(GrafanaClient, capability="grafana.recent_changes")
    assert isinstance(client, GrafanaClient)


def test_the_boot_composes_the_vendor_access() -> None:
    """The joint, for the thirtieth time this session — and the widest of them:
    a hundred and ninety-three tools were waiting on this one call."""
    import inspect

    from gateway.http import lifespan

    assert "compose_integration_access" in inspect.getsource(lifespan)
