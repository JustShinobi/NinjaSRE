"""A verifier must probe the address the operator configured, not the placeholder.

Every self-hosted package ships a documentation host — ``alertmanager.example.com``
— because nobody packaging an integration knows where your cluster is. The
operator declares the real one, ``IntegrationAccess.client`` applies it, and
every vendor *tool* goes through that. The verifiers did not: each built its own
client from a transport and a context, which is everything except where the
vendor is.

Nothing caught it because nothing ran them. Composed as they stood, "Test again"
would have reached ``alertmanager.example.com``, reported it unreachable, and
been right about a host the operator has never heard of.

Parametrised over the catalogue rather than written per vendor, so a package
added later fails this by construction instead of quietly joining the ones that
address a placeholder.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import pytest

from integrations._base import access
from integrations._base.access import IntegrationAccess
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import RequestContext
from integrations._catalogue.discovery import catalogue
from integrations._verification.framework import IntegrationVerifier
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

pytestmark = pytest.mark.unit

CONTEXT = RequestContext(org_id="acme", team_id="-", capability="integration.verify")


class _Recording:
    """Records where each call was addressed, then refuses it.

    Refuses rather than answers because what is under test is the address, and
    a fake that had to satisfy fifteen different response shapes would be
    testing the fakes. ``UNAUTHENTICATED`` because it is not retryable: a
    retryable refusal would make every case here three calls instead of one.
    """

    def __init__(self) -> None:
        self.urls: list[str] = []

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        self.urls.append(request.url)
        raise IntegrationError(
            "the address under test has nothing behind it",
            integration=request.integration,
            reason=IntegrationErrorReason.UNAUTHENTICATED,
        )


def _addressable() -> tuple[tuple[str, Any], ...]:
    """Return every integration that declares an address and ships a verifier."""
    return tuple(
        (entry.descriptor.name, entry.descriptor.verifier)
        for entry in catalogue()
        if entry.descriptor.schema.endpoint_names
        and isinstance(entry.descriptor.verifier, IntegrationVerifier)
    )


ADDRESSABLE = _addressable()


#: A port and a path prefix, because both are things an operator's address
#: carries and both are things a naive rewrite loses.
def _address(name: str) -> str:
    return f"https://{name}.test.invalid:8443/prefix"


@contextlib.contextmanager
def _bound(transport: _Recording, endpoints: dict[str, str]) -> Iterator[None]:
    previous = access.bind(
        IntegrationAccess(
            transport=transport,  # type: ignore[arg-type]
            org_id="acme",
            team_id="-",
            endpoints=endpoints,
        )
    )
    try:
        yield
    finally:
        access.restore(previous)


@pytest.mark.parametrize(("name", "verifier"), ADDRESSABLE, ids=[name for name, _ in ADDRESSABLE])
async def test_a_verifier_probes_where_the_operator_said_the_vendor_is(
    name: str, verifier: Any
) -> None:
    recording = _Recording()
    endpoints = {declared: _address(declared) for declared, _ in ADDRESSABLE}

    with _bound(recording, endpoints), contextlib.suppress(IntegrationError):
        await verifier.connect(recording, CONTEXT)

    assert recording.urls, f"{name}'s verifier made no call at all"
    for url in recording.urls:
        assert f"{name}.test.invalid" in url, f"{name} probed {url}"


@pytest.mark.parametrize(("name", "verifier"), ADDRESSABLE, ids=[name for name, _ in ADDRESSABLE])
async def test_a_verifier_falls_back_to_its_own_package_when_nothing_is_configured(
    name: str, verifier: Any
) -> None:
    """Unchanged behaviour for a deployment that has declared nothing, which is
    every deployment until somebody fills the field in."""
    recording = _Recording()

    with _bound(recording, {}), contextlib.suppress(IntegrationError):
        await verifier.connect(recording, CONTEXT)

    assert recording.urls
    for url in recording.urls:
        assert f"{name}.test.invalid" not in url


async def test_the_path_a_configured_address_carries_survives() -> None:
    """The case a URL rewrite at the transport cannot pass. An address behind a
    reverse proxy is ``https://host/alertmanager``, and dropping the prefix
    sends every call to the wrong place on the right host — which reads as a
    404 from the vendor rather than as a configuration mistake."""
    verifier = next(v for name, v in ADDRESSABLE if name == "alertmanager")
    recording = _Recording()

    with (
        _bound(recording, {"alertmanager": "https://edge.test.invalid/alertmanager"}),
        contextlib.suppress(IntegrationError),
    ):
        await verifier.connect(recording, CONTEXT)

    assert recording.urls
    assert recording.urls[0].startswith("https://edge.test.invalid/alertmanager/")
