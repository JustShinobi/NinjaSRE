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

import importlib
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


def vault_values(name: str) -> dict[str, str]:
    """Return ``name``'s scenario credential without the fields the vault does not hold.

    A scenario declares what an operator submits, which since addresses became
    configurable is a credential *and* an address. The vault holds the first
    half; the second is configuration, and handing it over would be refused as
    a field the vault's view of the schema does not declare.
    """
    schema = ENTRIES[name].descriptor.schema
    addresses = set(schema.endpoint_names)
    return {
        field: value for field, value in CREDENTIALS.get(name, {}).items() if field not in addresses
    }


def endpoint_values(name: str) -> dict[str, str]:
    """Return the address half of ``name``'s scenario credential, if it declares one."""
    schema = ENTRIES[name].descriptor.schema
    addresses = set(schema.endpoint_names)
    return {
        field: value for field, value in CREDENTIALS.get(name, {}).items() if field in addresses
    }


def integration_ids() -> tuple[str, ...]:
    """Return every catalogued integration name, in order."""
    return tuple(entry.name for entry in CATALOGUE)


#: A syntactically valid credential per integration, in the shape each schema
#: requires. Not secrets — they are made up, and the suite asserts that none of
#: them reaches a client, which is the property SC-003 is about.
#:
#: Read from each integration's synthetic scenario rather than written out here.
#: A second copy of eighty-odd credential shapes is a second thing to update when
#: a schema gains a field, and the copy nobody updates is the one that turns a
#: real contract failure into a fixture failure somewhere else in the suite.
def _declared_credentials() -> dict[str, dict[str, str]]:
    """Return each integration's scenario credential, keyed by integration."""
    found: dict[str, dict[str, str]] = {}
    for entry in CATALOGUE:
        module = importlib.import_module(f"tests.synthetic.integration_scenarios.{entry.name}")
        credential = getattr(module, "CREDENTIAL", None)
        if credential is not None:
            found[entry.name] = dict(credential)
    return found


CREDENTIALS: dict[str, dict[str, str]] = _declared_credentials()


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

    # The vault's view of each schema: everything but the address, which is
    # stored in the configuration tree rather than here. Seeding the whole
    # declaration would ask the vault to hold a field it does not hold.
    schemas = CredentialSchemaRegistry.from_schemas(
        *(stored for found in descriptors if (stored := found.schema.for_vault()) is not None)
    )
    vault = Vault(gateway=gateway, schemas=schemas)
    for name in seeded:
        await vault.store(
            SCOPE, CredentialHandle(integration=name, team_id=TEAM_ID), vault_values(name)
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
