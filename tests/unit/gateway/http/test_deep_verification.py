"""Composing the thing that makes "Test again" reach the vendor.

``GatewayState.deep_verifier`` was a field with a default of ``None`` and no
assignment in any composition root. Everything behind it existed — fifteen
packages ship a verifier, the runner probes connectivity and then each declared
permission, and CI drives exactly that — so the one route that would turn
``unknown`` into a measurement answered 404 on every deployment, always. An
operator connected an integration to find out whether it worked, and the control
that would have told them was inert.

Two things have to be true for the composed verifier to be worth having, and
both are here: it must reach the address the operator configured rather than the
package's placeholder, and it must resolve the *caller's* team. A credential
lives under a team handle and the fallback goes team → organisation and never
back, so a verify wired to the organisation-wide binding alone would report a
team's working credential as missing — the same false negative this whole pass
exists to remove, reintroduced one layer down.
"""

from __future__ import annotations

from typing import Any

import pytest

from gateway.http.deep_verification import VERIFY_CAPABILITY, compose_deep_verifier
from integrations._base import access
from integrations._base.access import IntegrationAccess
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

pytestmark = pytest.mark.unit

ADDRESS = "http://10.20.20.36:9093"


class _Recording:
    """Records what was asked of the vendor, and refuses it."""

    def __init__(self) -> None:
        self.requests: list[ProxyRequest] = []

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        self.requests.append(request)
        raise IntegrationError(
            "nothing is listening",
            integration=request.integration,
            reason=IntegrationErrorReason.UNAUTHENTICATED,
        )


class _State:
    """Only what the composer touches."""

    def __init__(self) -> None:
        self.deep_verifier: Any = None


@pytest.fixture
def unbind() -> Any:
    previous = access.bind(None)
    yield
    access.restore(previous)


def _bind(transport: _Recording, endpoints: dict[str, str]) -> IntegrationAccess:
    """Bind a vendor access for this process, as ``compose_integration_access`` does."""
    bound = IntegrationAccess(
        transport=transport,  # type: ignore[arg-type]
        org_id="acme",
        team_id="-",
        endpoints=endpoints,
    )
    access.bind(bound)
    return bound


async def test_a_deployment_with_no_binding_composes_nothing(unbind: None) -> None:
    """And the route's 404 stays true, which is the sentence it is written to
    say: reaching a vendor needs a credential proxy, and one was not composed."""
    state = _State()

    compose_deep_verifier(state)

    assert state.deep_verifier is None


async def test_a_deployment_with_a_binding_can_reach_its_vendor(unbind: None) -> None:
    recording = _Recording()
    _bind(recording, {"alertmanager": ADDRESS})
    state = _State()

    compose_deep_verifier(state)

    assert state.deep_verifier is not None
    report = await state.deep_verifier("alertmanager", "-")

    assert report is not None
    assert report["integration"] == "alertmanager"
    assert recording.requests, "the verifier made no vendor call"
    assert recording.requests[0].url.startswith(ADDRESS)


async def test_an_integration_with_no_verifier_answers_none(unbind: None) -> None:
    """So the route can tell "this deployment composed none" from "there is
    nothing further to ask this vendor" — two different refusals."""
    _bind(_Recording(), {})
    state = _State()
    compose_deep_verifier(state)
    assert state.deep_verifier is not None

    assert await state.deep_verifier("nothing-answers-to-this", "-") is None


async def test_the_call_is_made_for_the_team_that_asked(unbind: None) -> None:
    """A credential stored under a team handle is invisible from the
    organisation-wide one, so the team has to travel with the request."""
    recording = _Recording()
    _bind(recording, {"alertmanager": ADDRESS})
    state = _State()
    compose_deep_verifier(state)
    assert state.deep_verifier is not None

    await state.deep_verifier("alertmanager", "payments")

    assert recording.requests[0].team_id == "payments"
    assert recording.requests[0].capability == VERIFY_CAPABILITY


async def test_it_re_reads_the_binding_rather_than_capturing_it(unbind: None) -> None:
    """Writing an address rebinds a new frozen ``IntegrationAccess``. A closure
    over the old one would faithfully test the address it replaced, which is
    exactly the confusion the address field was added to end."""
    first, second = _Recording(), _Recording()
    _bind(first, {})
    state = _State()
    compose_deep_verifier(state)
    assert state.deep_verifier is not None

    _bind(second, {"alertmanager": ADDRESS})
    await state.deep_verifier("alertmanager", "-")

    assert not first.requests
    assert second.requests[0].url.startswith(ADDRESS)
