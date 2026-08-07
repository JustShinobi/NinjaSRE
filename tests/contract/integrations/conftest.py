"""The catalogue every contract test below is parameterised over.

One suite, one row per integration. The catalogue is three vendors today and
roughly eighty-five by the end of the wave, and the arithmetic of that growth is
the whole reason the suite is shaped this way: eighty-five test files drift, and
the ones that drift are the ones nobody reads. One suite over a discovered
catalogue cannot, because there is no per-integration file to forget to update
and a framework change is checked against every vendor in the same run.

The fixtures here are module-level constants rather than pytest fixtures because
``pytest.mark.parametrize`` needs the ids at collection time, and a fixture is
not resolved until a test runs. Discovery is a handful of imports Python has
already done, so paying for it at import is free.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from integrations._base.transport import InProcessProxyTransport, RequestContext
from integrations._catalogue.discovery import catalogue, profiles
from integrations._catalogue.entry import CatalogueEntry
from platform.credentials.descriptor import IntegrationDescriptor
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

REPO_ROOT = Path(__file__).resolve().parents[3]

ORG_ID = "acme"
TEAM_ID = "payments"
SCOPE = TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID)
CONTEXT = RequestContext(org_id=ORG_ID, team_id=TEAM_ID, capability="contract_probe")

#: Every catalogued integration, in name order. This is the parametrisation.
CATALOGUE: tuple[CatalogueEntry, ...] = catalogue()

#: The same catalogue keyed by name, for a test that has the id and wants the row.
ENTRIES: dict[str, CatalogueEntry] = {entry.name: entry for entry in CATALOGUE}

#: The vendor declarations behind the entries.
PROFILES = profiles()


def integration_ids() -> tuple[str, ...]:
    """Return every catalogued integration name, in order."""
    return tuple(entry.name for entry in CATALOGUE)


#: A syntactically valid credential per integration, in the shape each schema
#: requires. Not secrets — they are made up, and the suite asserts that none of
#: them reaches a client, which is the property SC-004 is about.
CREDENTIALS: dict[str, dict[str, str]] = {
    "datadog": {
        "api_key": "0123456789abcdef0123456789abcdef",
        "app_key": "0123456789abcdef0123456789abcdef01234567",
    },
    "kubernetes": {"token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IiJ9.contract"},
    "aws": {
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "region": "us-east-1",
    },
}


@dataclass(slots=True)
class RecordingVendor:
    """The far side of the proxy: records what arrived, answers from a queue."""

    responses: list[OutboundResponse] = field(default_factory=list)
    sent: list[OutboundRequest] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and answer with the next scripted response."""
        self.sent.append(request)
        if self.responses:
            return self.responses.pop(0)
        return OutboundResponse(200, {"content-type": "application/json"}, b"{}")


def json_response(payload: object, *, status: int = 200) -> OutboundResponse:
    """Return a scripted response carrying ``payload`` as JSON."""
    return OutboundResponse(
        status, {"content-type": "application/json"}, json.dumps(payload).encode("utf-8")
    )


async def stand_up(
    descriptors: Sequence[IntegrationDescriptor],
    *,
    seeded: Sequence[str] = (),
) -> tuple[InProcessProxyTransport, RecordingVendor]:
    """Return a transport onto a proxy holding credentials for ``seeded``.

    Every integration's rule is registered, so a request that reaches an
    undeclared host is refused for the reason it would be refused in
    production rather than for the reason a narrower fixture would invent.
    """
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    schemas = CredentialSchemaRegistry.from_schemas(*(found.schema for found in descriptors))
    vault = Vault(gateway=gateway, schemas=schemas)
    for name in seeded:
        await vault.store(
            SCOPE, CredentialHandle(integration=name, team_id=TEAM_ID), CREDENTIALS[name]
        )

    vendor = RecordingVendor()
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(*(found.rule for found in descriptors)),
        sender=vendor,
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: datetime(2026, 8, 7, 9, 0, tzinfo=UTC),
    )
    return InProcessProxyTransport(create_proxy_app(engine)), vendor
