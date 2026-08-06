"""The wiring the red-team suite investigates, and the sentinel it hunts for.

The point of this suite is that it does not simulate the invariant. It stands a
real vault, a real proxy, a real integration client, and a real investigation
next to each other, seeds a credential that exists nowhere else in the universe,
and then goes looking for it in every place Article IV says it must not be.

Two things make that a measurement rather than a slogan.

**The sentinel is unique.** ``SENTINEL_API_KEY`` is a literal that appears in
this file and in the vault, and nowhere else. A scan finding it anywhere in the
agent's reach is finding the credential, not a coincidence.

**There is a positive control.** ``RecordingSender`` keeps every request that
left the proxy, and the suite asserts the sentinel *did* arrive at the vendor.
Without that, a test that broke the call entirely would pass with the highest
possible marks.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel, ToolMetadata
from core.capability.registered import RegisteredTool
from core.capability.result import CapabilityResult, Evidence
from core.domain.alerts.normalisation import RawAlert
from core.state.types import TeamContext
from integrations._base.client import IntegrationClient
from integrations._base.retry import RetryPolicy
from integrations._base.transport import InProcessProxyTransport, RequestContext
from integrations.datadog import DATADOG, DatadogClient
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.rate_limit import TenantRateLimiter
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

#: The credential the suite hunts for. Two fields, because Datadog needs two and
#: a proxy that injected one of them would otherwise look correct.
#:
#: Both are *format-valid* — 32 hex characters and 40 alphanumerics — because the
#: vault validates on write and a sentinel the schema rejects could never be
#: stored. They are also distinctive enough that finding either anywhere in the
#: agent's reach is finding the credential rather than a coincidence.
SENTINEL_API_KEY = "5ea1decafc0ffee0000ba5e51ff11ce1"
SENTINEL_APP_KEY = "SENT1NELdatadogAPPKEY0000000000000000ZZZ"

SENTINELS: tuple[str, ...] = (SENTINEL_API_KEY, SENTINEL_APP_KEY)

ORG_ID = "acme"
TEAM_ID = "payments"
CAPABILITY = "datadog_search_logs"

AT = datetime(2026, 8, 6, 12, 30, tzinfo=UTC)


@dataclass(slots=True)
class RecordingSender:
    """Stands in for the network, and keeps what the proxy handed it.

    This is the vendor's side of the boundary. Everything it receives is
    *supposed* to carry the credential — that is the whole job — so it is also
    the positive control that proves the injection happened at all.
    """

    response: OutboundResponse = field(
        default_factory=lambda: OutboundResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(
                {"logs": [{"message": "checkout OOMKilled", "service": "checkout"}]}
            ).encode("utf-8"),
        )
    )
    sent: list[OutboundRequest] = field(default_factory=list)
    failures: list[Exception] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and return the scripted response."""
        self.sent.append(request)
        if self.failures:
            raise self.failures.pop(0)
        return self.response

    def rendered(self) -> tuple[str, ...]:
        """Return every recorded request flattened to strings, for scanning."""
        rendered: list[str] = []
        for request in self.sent:
            rendered.append(request.url)
            rendered.extend(f"{name}: {value}" for name, value in request.headers.items())
            if request.body is not None:
                rendered.append(request.body.decode("utf-8", errors="replace"))
        return tuple(rendered)


@dataclass(slots=True)
class ProxyStack:
    """A vault, a proxy, and a client, wired the way a deployment wires them."""

    gateway: FakePersistence
    vault: Vault
    engine: ProxyEngine
    sender: RecordingSender
    transport: InProcessProxyTransport
    scope: TenantScope

    def client(self, *, retry: RetryPolicy | None = None) -> DatadogClient:
        """Return a Datadog client on the proxy, holding no credential.

        ``retry`` is overridable so a test asserting a failure does not spend
        the default policy's backoff proving it. The backoff itself has its own
        unit tests; this suite is about where the credential is.
        """
        return DatadogClient(
            transport=self.transport,
            context=RequestContext(org_id=ORG_ID, team_id=TEAM_ID, capability=CAPABILITY),
            site="datadoghq.com",
            retry=retry if retry is not None else RetryPolicy(max_attempts=1),
        )

    def tool(self) -> RegisteredTool:
        """Return the agent-callable capability that reaches Datadog."""
        return integration_tool(self.client())


def integration_tool(client: IntegrationClient) -> RegisteredTool:
    """Return a capability whose body is a real client call through the proxy."""

    async def call(**arguments: Any) -> CapabilityResult:
        response = await client.get("/api/v2/logs/events", params={"query": arguments["query"]})
        payload = response.json()
        return CapabilityResult.ok(
            CAPABILITY,
            value={"arguments": arguments, "logs": payload["logs"]},
            evidence=(
                Evidence(
                    source="datadog",
                    evidence_type=EvidenceType.LOG,
                    summary="one log line matching the incident window",
                    reference=f"datadog:{CAPABILITY}",
                ),
            ),
        )

    metadata = ToolMetadata(
        name=CAPABILITY,
        display_name="Datadog Search Logs",
        description="Search Datadog logs for the incident window.",
        domain="observability",
        tags=("errors", "logs"),
        use_cases=("investigate an elevated error rate", "find why a pod restarted"),
        evidence_source="datadog",
        evidence_type=EvidenceType.LOG,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
        requires=Requirements(integrations=("datadog",)),
    )
    return RegisteredTool(
        metadata=metadata,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
            },
            "required": ["query"],
        },
        output_schema={"type": "object"},
        call=call,
        source_module="tests.security.conftest",
        source_qualname="integration_tool.call",
    )


async def build_stack(*, sender: RecordingSender | None = None) -> ProxyStack:
    """Return a wired stack. Nothing is in the vault until ``seed_sentinel`` runs."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")
    schemas = CredentialSchemaRegistry.from_schemas(DATADOG.schema)
    rules = InjectionRuleRegistry.from_rules(DATADOG.rule)
    outbound = sender if sender is not None else RecordingSender()

    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=rules,
        sender=outbound,
        auditor=ResolutionAuditor(gateway=gateway),
        limiter=TenantRateLimiter(),
    )
    return ProxyStack(
        gateway=gateway,
        vault=Vault(gateway=gateway, schemas=schemas),
        engine=engine,
        sender=outbound,
        transport=InProcessProxyTransport(create_proxy_app(engine)),
        scope=TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID),
    )


async def seed_sentinel(
    stack: ProxyStack,
    *,
    expires_at: datetime | None = None,
) -> None:
    """Put the sentinel credential in the vault, where only the proxy may read it."""
    await stack.vault.store(
        stack.scope,
        CredentialHandle(integration="datadog", team_id=TEAM_ID),
        {"api_key": SENTINEL_API_KEY, "app_key": SENTINEL_APP_KEY},
        description="the credential this suite hunts for",
        expires_at=expires_at,
    )


@pytest.fixture
async def stack() -> ProxyStack:
    """Return a wired stack with the sentinel already seeded."""
    built = await build_stack()
    await seed_sentinel(built)
    return built


# -- scanning -----------------------------------------------------------------


def strings_in(value: Any) -> Iterator[str]:
    """Yield every string reachable from ``value``, however it is nested.

    Deliberately exhaustive rather than schema-aware. A scan that knew which
    fields to look at would miss the field somebody adds next week, which is
    precisely the leak this suite exists to catch.
    """
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, bytes):
        yield value.decode("utf-8", errors="replace")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from strings_in(key)
            yield from strings_in(item)
        return
    if isinstance(value, Sequence):
        for item in value:
            yield from strings_in(item)
        return
    if hasattr(value, "to_record"):
        yield from strings_in(value.to_record())
        return
    if hasattr(value, "__dict__") or hasattr(value, "__slots__"):
        yield repr(value)
        return
    yield repr(value)


def find_sentinels(value: Any) -> tuple[str, ...]:
    """Return the sentinels that appear anywhere inside ``value``."""
    found: set[str] = set()
    for text in strings_in(value):
        for sentinel in SENTINELS:
            if sentinel in text:
                found.add(sentinel)
    return tuple(sorted(found))


def alert() -> RawAlert:
    """Return the alert the investigation starts from."""
    return RawAlert(
        payload={
            "receiver": "payments-team",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighErrorRate",
                        "severity": "critical",
                        "service": "checkout",
                    },
                    "annotations": {"summary": "checkout error rate above 5%"},
                    "startsAt": (AT - timedelta(minutes=12)).isoformat(),
                    "endsAt": "0001-01-01T00:00:00Z",
                }
            ],
        },
        received_at=AT,
    )


def team() -> TeamContext:
    """Return the team the investigation runs for."""
    return TeamContext(team_id=TEAM_ID, integrations=("datadog",), destinations=())
