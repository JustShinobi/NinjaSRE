"""Binding the control plane a hypervisor write actually reaches.

The measured state before this existed: ``control_plane.current()`` was ``None``
in every deployment there has ever been, because nothing in the repository
called ``bind``. Without it ``unmet_for_remediation`` names a missing control
plane, ``compose_remediation`` composes nothing and writes ``desk_skipped``, the
request builder reads a snapshot it declares unreadable, the plan factory
derives no undo, and the call is refused for want of a plan — so **no approval
is ever queued**, and the count in a real deployment is zero by construction
rather than by policy.

So these tests are about the wire, not about the plane. The properties, and how
each would be silently wrong:

**A configured cluster becomes a bound control plane.** The failure this
replaces is a binding nothing performs.

**Binding it lets the desk compose.** That is the whole chain: without the desk
there is nothing to propose through, and an operator reading "this deployment
proposed nothing" cannot tell a decision from a missing wire.

**The bound plane reaches the hypervisor only through the credential proxy.** It
holds no credential and cannot: a control plane that built its own client from
ambient configuration would be one lookup away from acting on somebody else's
estate.

**A deployment with no cluster binds nothing and says so.** Binding a plane
that cannot answer would make every remediation fail at the moment of use
instead of being absent at the moment of composition.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from capabilities.registry.catalogue import Registry
from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.proxmox import DECLARATIONS, ProxmoxControlPlane
from gateway.http.control_plane import compose_control_plane
from gateway.http.remediation import compose_remediation, unmet_for_remediation
from gateway.http.state import GatewayState
from gateway.runtime.investigator import ReActInvestigationRunner
from integrations._base.transport import HttpProxyTransport
from integrations.proxmox.writes import ProxmoxWriteClient
from platform.credentials.proxy.trust import TrustAnchor
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence

pytestmark = pytest.mark.unit

ORG = "acme"
PROXY = "http://127.0.0.1:8787"
ADDRESS = "https://pve02.lan.example:8006"
FINGERPRINT = "00:01:02:03:04:05:06:07:08:09:0A:0B:0C:0D:0E:0F:10:11:12:13:14:15:16:17:18:19:1A:1B:1C:1D:1E:1F"


@pytest.fixture(autouse=True)
def _unbound() -> Iterator[None]:
    """Start every test from what a fresh deployment has: nothing bound."""
    previous = control_plane.bind(None)
    yield
    control_plane.restore(previous)


def _state() -> GatewayState:
    """Return the gateway state a composition root would hand the composer."""
    store = FakePersistence()
    return GatewayState(
        gateway=store,
        tokens=TokenService(gateway=store),
        investigator=ReActInvestigationRunner(llm=None, registry=Registry()),  # type: ignore[arg-type]
    )


def _configured(monkeypatch: pytest.MonkeyPatch, *entries: Mapping[str, Any]) -> None:
    """Make the configuration tree resolve to ``entries``."""
    from gateway.http import control_plane as module

    async def resolved(_state: object, _org: str) -> tuple[Mapping[str, Any], ...]:
        return entries

    monkeypatch.setattr(module, "_active_integrations", resolved)


PROXMOX = {"name": "proxmox", "enabled": True, "base_url": ADDRESS}


# -- the wire ------------------------------------------------------------------


async def test_a_configured_cluster_becomes_a_bound_control_plane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, PROXMOX)

    bound = await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY)

    assert bound is not None, (
        "nothing bound a control plane for a deployment whose hypervisor is configured. "
        "Every remediation refuses for want of one, and no approval is ever queued."
    )
    assert control_plane.current() is bound
    assert isinstance(bound, ProxmoxControlPlane)


async def test_the_bound_plane_carries_every_write_this_deployment_declares(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, PROXMOX)

    bound = await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY)

    assert bound is not None
    assert dict(bound.declarations) == dict(DECLARATIONS)


async def test_binding_it_is_what_lets_the_desk_compose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The end of the chain, and the reason the binding is worth having."""
    _configured(monkeypatch, PROXMOX)
    state = _state()

    assert any("control plane" in missing for missing in unmet_for_remediation(state))

    await compose_control_plane(state, org_id=ORG, proxy_url=PROXY)

    assert unmet_for_remediation(state) == ()
    desk = await compose_remediation(state, org_id=ORG, proxy_url=PROXY)
    assert desk is not None, (
        "the desk still did not compose with a control plane bound. Without it nothing "
        "queues an approval, and the count in a deployment is zero by construction."
    )


# -- and it reaches the hypervisor the one sanctioned way ------------------------


async def test_the_bound_plane_reaches_the_cluster_only_through_the_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, PROXMOX)

    bound = await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY)

    assert bound is not None
    assert isinstance(bound.client, ProxmoxWriteClient)
    transport = bound.client._transport  # noqa: SLF001 — the point of the test
    assert isinstance(transport, HttpProxyTransport)
    assert transport.base_url == PROXY


async def test_the_bound_plane_holds_no_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It cannot hold one: the proxy injects at the network edge, and it alone."""
    _configured(monkeypatch, PROXMOX)

    bound = await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY)

    assert bound is not None
    written = repr(bound.client._context)  # noqa: SLF001 — the point of the test
    assert "token" not in written.lower()
    assert "password" not in written.lower()


async def test_the_bound_plane_is_pointed_at_the_address_the_operator_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, PROXMOX)

    bound = await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY)

    assert bound is not None
    assert bound.client.endpoints.hosts == ("pve02.lan.example",)


async def test_the_bound_plane_carries_the_certificate_trust_that_was_declared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """So a verification report reads back what this deployment actually accepts."""
    _configured(
        monkeypatch,
        {**PROXMOX, "trust": {"fingerprints": [FINGERPRINT]}},
    )

    bound = await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY)

    assert bound is not None
    assert bound.client.trust.anchor is TrustAnchor.PINNED_FINGERPRINT
    assert bound.client.trust.matches_fingerprint(FINGERPRINT)


# -- and a deployment with nothing configured binds nothing ----------------------


async def test_a_deployment_with_no_cluster_binds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch)

    assert await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY) is None
    assert control_plane.current() is None


async def test_a_cluster_switched_off_binds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, {**PROXMOX, "enabled": False})

    assert await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY) is None


async def test_a_cluster_with_no_address_binds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plane pointed nowhere fails at the first write, which is further away."""
    _configured(monkeypatch, {**PROXMOX, "base_url": ""})

    assert await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY) is None


async def test_a_deployment_with_no_credential_proxy_binds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, PROXMOX)

    assert await compose_control_plane(_state(), org_id=ORG, proxy_url="") is None


async def test_an_unreadable_configuration_binds_nothing_rather_than_failing_the_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway.http import control_plane as module

    async def unreadable(_state: object, _org: str) -> tuple[Mapping[str, Any], ...]:
        raise RuntimeError("the configuration tree did not answer")

    monkeypatch.setattr(module, "_active_integrations", unreadable)

    assert await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY) is None


async def test_a_disabled_cluster_clears_a_previously_bound_plane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configured(monkeypatch, PROXMOX)
    bound = await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY)
    assert bound is not None
    assert control_plane.current() is bound

    # Now switch off the integration and recompose
    _configured(monkeypatch, dict(PROXMOX, enabled=False))
    recomposed = await compose_control_plane(_state(), org_id=ORG, proxy_url=PROXY)
    assert recomposed is None
    assert control_plane.current() is None


# -- the wire is in the composition root, and it is there before the desk --------


def test_the_process_that_serves_binds_it_and_binds_it_before_the_desk() -> None:
    """Cut this call and the deployment goes back to proposing nothing.

    An AST walk rather than a text match, so a call that has been renamed,
    commented out or moved behind a branch that never runs is a failure here
    rather than a line that still reads correctly.
    """
    from gateway.http import lifespan as module

    tree = ast.parse(inspect.getsource(module))
    called: list[str] = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]

    assert "compose_control_plane" in called, (
        "nothing in the process that serves binds a control plane. Without it "
        "compose_remediation writes desk_skipped, no approval is ever queued, and the "
        "deployment proposes nothing for a reason no policy chose."
    )
    assert "compose_remediation" in called
    assert called.index("compose_control_plane") < called.index("compose_remediation"), (
        "the control plane is bound after the desk is composed, so the desk asks "
        "whether one exists before one does and composes nothing anyway."
    )
