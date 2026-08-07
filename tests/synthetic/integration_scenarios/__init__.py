"""One scenario module per integration, and what running one means.

The seventh parity artefact, and the one whose absence is hardest to notice. An
integration with a schema, a verifier, a client, tools, a skill, and docs looks
finished. What it lacks is anything that would fail when the vendor changes a
response shape — and the first thing to notice that is the investigation which
needed it.

So a scenario here drives the **whole path**: the real capability, the real
client, the real credential proxy with the real injection rule, and a scripted
vendor on the far side. Nothing is mocked between the tool and the wire. What
that catches is precisely what recorded fixtures are for — a renamed response
field, a changed pagination cursor, an injection that stopped matching the
schema — and it catches them in the build rather than in an incident.

A scenario is deliberately not a full investigation. Those live beside this
directory and exercise the pipeline; these exercise one vendor, end to end, so
that a failure names the integration rather than the loop.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.capability.registered import RegisteredTool, capability_marker
from core.capability.result import CapabilityResult
from integrations._base.access import IntegrationAccess, bind, restore
from integrations._base.transport import InProcessProxyTransport
from platform.credentials.descriptor import IntegrationDescriptor
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import InjectionRule, InjectionRuleRegistry
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

ORG_ID = "acme"
TEAM_ID = "payments"
SCOPE = TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID)
AT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class IntegrationScenario:
    """One capability call against a scripted vendor, and what it should produce.

    ``expected_summary`` is a fragment rather than the whole sentence. The point
    of asserting on the evidence summary at all is that it is what a human reads
    in a finding, and a test pinned to its exact wording is a test that fails on
    an improvement to the wording.
    """

    key: str
    integration: str
    capability: str
    arguments: Mapping[str, Any]
    responses: tuple[OutboundResponse, ...]
    credential: Mapping[str, str]
    expected_summary: str
    expected_paths: tuple[str, ...] = ()
    expected_truncated: bool = False
    rule: InjectionRule | None = None


@dataclass(slots=True)
class ScriptedVendor:
    """The far side of the proxy: records what arrived, answers from a queue."""

    responses: list[OutboundResponse] = field(default_factory=list)
    sent: list[OutboundRequest] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and answer with the next scripted response."""
        self.sent.append(request)
        if self.responses:
            return self.responses.pop(0)
        return OutboundResponse(200, {"content-type": "application/json"}, b"{}")


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    """What running one scenario produced."""

    result: CapabilityResult
    vendor: ScriptedVendor

    @property
    def paths(self) -> tuple[str, ...]:
        """Return the vendor URLs the capability actually reached."""
        return tuple(request.url for request in self.vendor.sent)


def capability_named(name: str, tools: Sequence[Any]) -> RegisteredTool:
    """Return the registration for ``name`` among ``tools``.

    Raises:
        LookupError: nothing in ``tools`` declares that capability.
    """
    for candidate in tools:
        registered = capability_marker(candidate)
        if registered is not None and registered.name == name:
            return registered
    raise LookupError(f"no capability named {name!r} among the ones this integration declares")


async def run_scenario(
    scenario: IntegrationScenario,
    *,
    descriptor: IntegrationDescriptor,
    tool: RegisteredTool,
) -> ScenarioOutcome:
    """Run one scenario through the real proxy and return what it produced."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    schemas = CredentialSchemaRegistry.from_schemas(descriptor.schema)
    await Vault(gateway=gateway, schemas=schemas).store(
        SCOPE,
        CredentialHandle(integration=descriptor.name, team_id=TEAM_ID),
        dict(scenario.credential),
    )

    vendor = ScriptedVendor(responses=list(scenario.responses))
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(
            scenario.rule if scenario.rule is not None else descriptor.rule
        ),
        sender=vendor,
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: AT,
    )

    previous = bind(
        IntegrationAccess(
            transport=InProcessProxyTransport(create_proxy_app(engine)),
            org_id=ORG_ID,
            team_id=TEAM_ID,
        )
    )
    try:
        result = await tool.invoke(dict(scenario.arguments))
    finally:
        restore(previous)

    return ScenarioOutcome(result=result, vendor=vendor)


def json_response(payload: object, *, status: int = 200) -> OutboundResponse:
    """Return a scripted response carrying ``payload`` as JSON."""
    import json

    return OutboundResponse(
        status, {"content-type": "application/json"}, json.dumps(payload).encode("utf-8")
    )


__all__ = [
    "AT",
    "ORG_ID",
    "SCOPE",
    "TEAM_ID",
    "IntegrationScenario",
    "ScenarioOutcome",
    "ScriptedVendor",
    "capability_named",
    "json_response",
    "run_scenario",
]
