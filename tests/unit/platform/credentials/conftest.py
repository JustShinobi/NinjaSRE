"""A vault and a proxy built from fakes, for the tests that are about one piece.

The red-team suite in ``tests/security/`` stands the whole stack up and hunts
for a credential. These are the narrower tests: does rotation take effect, does
one team ever see another's key, does SigV4 match the specification's worked
example. They need the same wiring and none of the investigation, so it lives
here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import ProxyApp, create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import (
    HeaderInjection,
    InjectionRule,
    InjectionRuleRegistry,
)
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.rate_limit import TenantRateLimiter
from platform.credentials.proxy.refresh import RefreshedCredential
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialField, CredentialSchema, FieldKind
from platform.credentials.vault import Vault
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

INTEGRATION = "acme-monitoring"
ORG_ID = "acme"
TEAM_ID = "payments"
OTHER_TEAM_ID = "search"
CAPABILITY = "acme_search_logs"
HOST = "api.acme-monitoring.example"
URL = f"https://{HOST}/v1/logs"

AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

SCHEMA = CredentialSchema(
    integration=INTEGRATION,
    fields=(
        CredentialField(name="api_key", description="The key."),
        CredentialField(name="region", kind=FieldKind.PUBLIC, required=False),
    ),
)

RULE = InjectionRule(
    integration=INTEGRATION,
    hosts=(HOST,),
    injections=(HeaderInjection(header="X-Api-Key", field="api_key"),),
)


@dataclass(slots=True)
class ScriptedSender:
    """Returns queued responses and records what it was asked to send."""

    responses: list[OutboundResponse] = field(default_factory=list)
    sent: list[OutboundRequest] = field(default_factory=list)
    failures: list[Exception] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and answer with the next scripted response."""
        self.sent.append(request)
        if self.failures:
            raise self.failures.pop(0)
        if self.responses:
            return self.responses.pop(0)
        return OutboundResponse(status_code=200, body=b"{}")

    def keys_seen(self) -> tuple[str, ...]:
        """Return the API key on each recorded request, in order."""
        return tuple(request.headers.get("X-Api-Key", "") for request in self.sent)


@dataclass(slots=True)
class ScriptedRefresher:
    """Issues short-lived credentials on demand, and counts how often it was asked."""

    issued: list[RefreshedCredential] = field(default_factory=list)
    calls: int = 0
    fails: bool = False

    async def refresh(self, integration: str, values: Mapping[str, str]) -> RefreshedCredential:
        """Return the next scripted credential."""
        self.calls += 1
        if self.fails:
            raise ConnectionError("the token endpoint is unreachable")
        if self.issued:
            return self.issued.pop(0)
        return RefreshedCredential(values=dict(values), expires_at=None)


@dataclass(slots=True)
class Harness:
    """A vault, a resolver, an engine, and an app over one fake datastore."""

    gateway: FakePersistence
    vault: Vault
    engine: ProxyEngine
    app: ProxyApp
    sender: ScriptedSender
    limiter: TenantRateLimiter
    refresher: ScriptedRefresher

    def scope(self, team_id: str = TEAM_ID) -> TenantScope:
        """Return the tenant scope for ``team_id``."""
        return TenantScope(org_id=ORG_ID, team_node_id=team_id)

    def handle(self, team_id: str = TEAM_ID) -> CredentialHandle:
        """Return the credential handle for ``team_id``."""
        return CredentialHandle(integration=INTEGRATION, team_id=team_id)

    async def audit_events(self) -> tuple[object, ...]:
        """Return every audit event recorded for this organisation."""
        async with self.gateway.begin(self.scope()) as uow:
            return await uow.audit.query(limit=100)


async def build_harness(
    *,
    rule: InjectionRule = RULE,
    now: datetime | None = None,
    with_refresher: bool = False,
) -> Harness:
    """Return a wired harness for one organisation, with nothing in the vault."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    from platform.credentials.schemas import CredentialSchemaRegistry

    schemas = CredentialSchemaRegistry.from_schemas(SCHEMA)
    sender = ScriptedSender()
    limiter = TenantRateLimiter()
    refresher = ScriptedRefresher()
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(rule),
        sender=sender,
        auditor=ResolutionAuditor(gateway=gateway),
        limiter=limiter,
        refresher=refresher if with_refresher else None,
        clock=(lambda: now) if now is not None else None,
    )
    return Harness(
        gateway=gateway,
        vault=Vault(gateway=gateway, schemas=schemas),
        engine=engine,
        app=create_proxy_app(engine),
        sender=sender,
        limiter=limiter,
        refresher=refresher,
    )


def json_response(payload: object, *, status: int = 200) -> OutboundResponse:
    """Return a scripted vendor response carrying ``payload``."""
    return OutboundResponse(
        status_code=status,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )


@pytest.fixture
async def harness() -> Harness:
    """Return a wired harness with nothing in the vault."""
    return await build_harness()
