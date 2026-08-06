"""FR-021. "Does this credential work?" answered by using it, never by showing it.

The operator request behind the verification command is always the same:
something is failing and they want to know whether the credential is the
problem. The instinct is to show them the value so they can compare it against
their password manager, and defeating that instinct is most of what this feature
is for — a key that looks right and has been revoked looks exactly as right as
one that works.

So the answer comes from a call. These tests assert the two properties that make
that answer useful: it distinguishes the failures that need different actions,
and no result ever carries the value it was checking.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from integrations._base.transport import InProcessProxyTransport, RequestContext
from integrations.registry import descriptors, integration_names
from platform.credentials.errors import UnknownIntegration
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.credentials.verification import CredentialVerification
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

pytestmark = pytest.mark.contract

ORG_ID = "acme"
TEAM_ID = "payments"
SCOPE = TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID)
CONTEXT = RequestContext(org_id=ORG_ID, team_id=TEAM_ID, capability="credential_verify")

#: One credential per reference integration, in the format each schema requires.
CREDENTIALS: dict[str, dict[str, str]] = {
    "datadog": {
        "api_key": "0123456789abcdef0123456789abcdef",
        "app_key": "0123456789abcdef0123456789abcdef01234567",
    },
    "kubernetes": {"token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IiJ9.probe"},
    "aws": {
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "region": "us-east-1",
    },
}


@dataclass(slots=True)
class AcceptingVendor:
    """A vendor that accepts whatever the proxy signed or injected."""

    status: int = 200
    body: bytes = b"{}"
    sent: list[OutboundRequest] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and answer with the scripted status."""
        self.sent.append(request)
        return OutboundResponse(self.status, {"content-type": "application/json"}, self.body)


async def stand_up(*, seeded: tuple[str, ...], status: int = 200):
    """Return a transport, the vendor behind it, and a verification runner."""
    catalogue = descriptors()
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    schemas = CredentialSchemaRegistry()
    schemas.register_all(descriptor.schema for descriptor in catalogue.values())
    vault = Vault(gateway=gateway, schemas=schemas)
    for name in seeded:
        await vault.store(
            SCOPE, CredentialHandle(integration=name, team_id=TEAM_ID), CREDENTIALS[name]
        )

    vendor = AcceptingVendor(status=status)
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(
            *(descriptor.rule for descriptor in catalogue.values())
        ),
        sender=vendor,
        auditor=ResolutionAuditor(gateway=gateway),
    )
    return (
        InProcessProxyTransport(create_proxy_app(engine)),
        vendor,
        CredentialVerification(catalogue),
    )


async def test_a_working_credential_verifies() -> None:
    transport, _, verification = await stand_up(seeded=("datadog",))

    result = await verification.verify("datadog", transport=transport, context=CONTEXT)

    assert result.ok
    assert result.status_code == 200


async def test_an_unconfigured_credential_is_a_result_and_not_an_exception() -> None:
    """ "Nothing is configured" is precisely the answer the operator asked for."""
    transport, _, verification = await stand_up(seeded=())

    result = await verification.verify("datadog", transport=transport, context=CONTEXT)

    assert not result.ok
    assert "No Datadog credential is configured" in result.detail


async def test_verifying_every_integration_reports_one_result_each() -> None:
    """The command an operator runs after onboarding, for the whole catalogue."""
    transport, _, verification = await stand_up(seeded=tuple(CREDENTIALS))

    results = await verification.verify_all(transport=transport, context=CONTEXT)

    assert tuple(result.integration for result in results) == integration_names()
    assert all(result.ok for result in results)


async def test_no_verification_result_carries_the_value_it_checked() -> None:
    """The whole point: the answer is better than the value, and safer."""
    transport, _, verification = await stand_up(seeded=tuple(CREDENTIALS))

    results = await verification.verify_all(transport=transport, context=CONTEXT)

    rendered = str([result.to_record() for result in results])
    for credential in CREDENTIALS.values():
        for value in credential.values():
            assert value not in rendered


async def test_an_integration_nobody_installed_is_named_rather_than_guessed() -> None:
    transport, _, verification = await stand_up(seeded=())

    with pytest.raises(UnknownIntegration) as raised:
        await verification.verify("typo", transport=transport, context=CONTEXT)

    assert "datadog" in str(raised.value)


async def test_a_probe_makes_exactly_one_call() -> None:
    """A verifier that ran a real query would cost quota every time it was asked."""
    transport, vendor, verification = await stand_up(seeded=("kubernetes",))

    await verification.verify("kubernetes", transport=transport, context=CONTEXT)

    assert len(vendor.sent) == 1
    assert vendor.sent[0].method == "GET"
