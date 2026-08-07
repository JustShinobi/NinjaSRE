"""SC-006: an investigation on a Kubernetes and AWS stack, tier-1 integrations only.

The gate the wave was ordered around. Tiering is only worth the checkpoint it
costs if the platform is *usable* when the first tier is done, and "usable"
means one thing: an alert arrives, the pipeline runs, the loop reaches real
vendors through the real credential proxy, and the diagnosis it produces cites
what those vendors actually returned.

So nothing here is a capability double. The tools are the ones the integration
packages register, the clients are their own, the proxy is the real engine with
each integration's real injection rule, and only two things are scripted: the
provider, and the vendors on the far side of the wire — which is exactly the
boundary every other synthetic test in this directory draws.

What that catches is the thing a per-integration scenario cannot. Each vendor's
own scenario proves its client parses its vendor's shape; this proves that three
of them can be bound into one process at once, that the loop can call across
them in a single investigation, and that the evidence arrives attributed to the
integration it came from rather than to whichever was bound last.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from capabilities.registry.planning import CatalogueRanker
from core.agent.react_loop import ReActLoop
from core.capability.registered import RegisteredTool, capability_marker
from core.domain.alerts.normalisation import RawAlert
from core.pipeline.build import build_pipeline, investigation_hooks
from core.pipeline.ports import FixedCatalogueResolver, InMemoryIncidentIndex, StaticCatalogue
from core.pipeline.state_factory import initial_state
from core.state.types import STAGE_ORDER, TeamContext
from integrations._base.access import IntegrationAccess, bind, restore
from integrations._base.transport import InProcessProxyTransport
from integrations._catalogue.discovery import catalogue as integration_catalogue
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
from tests.synthetic.conftest import LoopTurn, ScenarioLLM
from tests.synthetic.integration_scenarios import aws as aws_scenarios
from tests.synthetic.integration_scenarios import aws_ec2 as ec2_scenarios
from tests.synthetic.integration_scenarios import capability_named
from tests.synthetic.integration_scenarios import kubernetes as kubernetes_scenarios

pytestmark = pytest.mark.synthetic

ORG_ID = "acme"
TEAM_ID = "payments"
SCOPE = TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID)
AT = datetime(2026, 8, 7, 12, 30, tzinfo=UTC)

#: The stack the primary story describes, narrowed to what tier 1 delivers.
TIER_ONE_STACK: tuple[str, ...] = ("kubernetes", "aws", "aws_ec2")

CREDENTIALS: dict[str, dict[str, str]] = {
    "kubernetes": dict(kubernetes_scenarios.CREDENTIAL),
    "aws": dict(aws_scenarios.CREDENTIAL),
    "aws_ec2": dict(ec2_scenarios.CREDENTIAL),
}

#: What each vendor answers, keyed by a fragment of the path the client calls.
#: A path nobody scripted answers with an empty document, which is what a real
#: vendor with nothing to report does.
VENDOR_ANSWERS: tuple[tuple[str, bytes, str], ...] = (
    (
        "/api/v1/namespaces/payments/events",
        json.dumps(
            {
                "items": [
                    {
                        "reason": "OOMKilled",
                        "message": "Container checkout exceeded its memory limit",
                        "involvedObject": {"name": "checkout-7f4c", "kind": "Pod"},
                    },
                    {
                        "reason": "OOMKilled",
                        "message": "Container checkout exceeded its memory limit",
                        "involvedObject": {"name": "checkout-7f4c", "kind": "Pod"},
                    },
                    {
                        "reason": "Scheduled",
                        "message": "Successfully assigned checkout-7f4c",
                        "involvedObject": {"name": "checkout-7f4c", "kind": "Pod"},
                    },
                ]
            }
        ).encode("utf-8"),
        "application/json",
    ),
    (
        "DescribeInstanceStatus",
        b"<?xml version='1.0'?><DescribeInstanceStatusResponse><instanceStatusSet>"
        b"<item><instanceId>i-0a1</instanceId>"
        b"<instanceState><name>running</name></instanceState></item>"
        b"<item><instanceId>i-0a2</instanceId>"
        b"<instanceState><name>running</name></instanceState></item>"
        b"</instanceStatusSet></DescribeInstanceStatusResponse>",
        "text/xml",
    ),
)


@dataclass(slots=True)
class StackVendors:
    """Every tier-1 vendor at once, answering on the path each client calls."""

    sent: list[OutboundRequest] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and answer with whatever was scripted for its path."""
        self.sent.append(request)
        for fragment, body, content_type in VENDOR_ANSWERS:
            if fragment in request.url:
                return OutboundResponse(200, {"content-type": content_type}, body)
        return OutboundResponse(200, {"content-type": "application/json"}, b"{}")

    @property
    def hosts(self) -> set[str]:
        """Return every host the stack actually reached."""
        return {request.host for request in self.sent}


async def stand_up_stack() -> tuple[InProcessProxyTransport, StackVendors]:
    """Return a transport onto a proxy holding this team's whole tier-1 stack."""
    entries = {entry.name: entry for entry in integration_catalogue()}
    descriptors = [entries[name].descriptor for name in TIER_ONE_STACK]

    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    schemas = CredentialSchemaRegistry.from_schemas(*(found.schema for found in descriptors))
    vault = Vault(gateway=gateway, schemas=schemas)
    for name in TIER_ONE_STACK:
        await vault.store(
            SCOPE, CredentialHandle(integration=name, team_id=TEAM_ID), CREDENTIALS[name]
        )

    vendors = StackVendors()
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(*(found.rule for found in descriptors)),
        sender=vendors,
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: AT,
    )
    return InProcessProxyTransport(create_proxy_app(engine)), vendors


def tier_one_tools() -> tuple[RegisteredTool, ...]:
    """Return every capability the tier-1 stack registers, as the agent sees them."""
    import importlib

    found: list[RegisteredTool] = []
    for name in TIER_ONE_STACK:
        module = importlib.import_module(f"integrations.{name}.tools")
        for attribute in vars(module).values():
            registered = capability_marker(attribute)
            if registered is not None and registered not in found:
                found.append(registered)
    return tuple(found)


def alert() -> RawAlert:
    """Return the page that starts the investigation."""
    return RawAlert(
        payload={
            "receiver": "payments-oncall",
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


def scripted_provider() -> ScenarioLLM:
    """Return the provider double: intake, two tool-calling turns, then a diagnosis."""
    from core.llm.types import ToolCall

    workload_events = capability_named("kubernetes_workload_events", _declared("kubernetes"))
    inventory = capability_named("aws_ec2_resource_inventory", _declared("aws_ec2"))

    return ScenarioLLM(
        structured=[
            {
                "is_incident": True,
                "confidence": 0.95,
                "reason": "an alert is firing on a production service",
                "alert_name": "HighErrorRate",
                "severity": "critical",
                "summary": "checkout error rate above 5%",
                "components": ["checkout"],
                "error_text": "",
            },
            {
                "root_cause_category": "resource_exhaustion",
                "summary": (
                    "The checkout container was OOM-killed twice inside the window [e1]; "
                    "the EC2 fleet behind it stayed running [e2], so the constraint is the "
                    "container's memory limit rather than the nodes."
                ),
                "confidence": 0.86,
                "contributing_factors": [],
                "recommended_actions": ["Raise the checkout container's memory limit."],
                "claims": [],
            },
        ],
        turns=[
            LoopTurn(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name=workload_events.name,
                        arguments={"namespace": "payments", "object_name": "checkout-7f4c"},
                    ),
                    ToolCall(
                        id="c2",
                        name=inventory.name,
                        arguments={"kind": "", "start": "", "end": ""},
                    ),
                )
            ),
            LoopTurn(
                text=(
                    "The checkout container was OOM-killed inside the incident window [e1], "
                    "and every EC2 instance behind it stayed running [e2]."
                )
            ),
        ],
    )


def _declared(integration: str) -> tuple[object, ...]:
    """Return every attribute an integration's tools package binds."""
    import importlib

    return tuple(vars(importlib.import_module(f"integrations.{integration}.tools")).values())


async def investigate() -> tuple[Any, StackVendors]:
    """Run the whole pipeline over the tier-1 stack and return what happened."""
    transport, vendors = await stand_up_stack()
    tools = tier_one_tools()
    llm = scripted_provider()

    previous = bind(IntegrationAccess(transport=transport, org_id=ORG_ID, team_id=TEAM_ID))
    try:
        pipeline = build_pipeline(
            llm=llm,
            runtime=ReActLoop(llm=llm, tools=tools, hooks=investigation_hooks()),
            resolver=FixedCatalogueResolver(
                StaticCatalogue(tools=tools, declarations=tuple(found.metadata for found in tools))
            ),
            ranker=CatalogueRanker(),
            incidents=InMemoryIncidentIndex(),
            strict=True,
        )
        run = await pipeline.run(
            initial_state(
                alert(),
                TeamContext(
                    team_id=TEAM_ID,
                    integrations=TIER_ONE_STACK,
                    destinations=(),
                ),
                run_id="run-tier-one",
            )
        )
    finally:
        restore(previous)
    return run, vendors


async def test_the_investigation_completes_on_tier_one_integrations_alone() -> None:
    """SC-006: the platform is usable before the wave finishes."""
    run, _ = await investigate()

    assert run.stages_run == STAGE_ORDER
    assert run.succeeded
    assert not run.halted_early


async def test_the_diagnosis_cites_evidence_the_real_vendors_returned() -> None:
    run, _ = await investigate()

    diagnosis = run.state.investigation.diagnosis
    assert diagnosis is not None
    assert not diagnosis.fallback_used
    sources = {entry.source for entry in run.state.evidence.entries}
    assert sources == {"kubernetes", "aws_ec2"}


async def test_every_call_left_through_the_proxy_for_a_permitted_host() -> None:
    """Article IV, across three integrations bound into one process at once."""
    _, vendors = await investigate()

    assert vendors.sent, "the investigation reached no vendor at all"
    entries = {entry.name: entry for entry in integration_catalogue()}
    permitted = {host for name in TIER_ONE_STACK for host in entries[name].descriptor.rule.hosts}
    assert vendors.hosts <= permitted


async def test_no_credential_value_reaches_the_investigation_state() -> None:
    """The state is persisted, replayed, and read by people and by models."""
    run, _ = await investigate()

    rendered = repr(run.state.evidence.entries) + repr(run.state.investigation.diagnosis)
    for credential in CREDENTIALS.values():
        for value in credential.values():
            if len(value) > 8:
                assert value not in rendered


async def test_the_two_integrations_report_separately_rather_than_merging() -> None:
    """One process, two vendors, and the attribution has to survive both."""
    run, _ = await investigate()

    by_capability = {entry.capability: entry for entry in run.state.evidence.entries}

    assert by_capability["kubernetes_workload_events"].source == "kubernetes"
    assert by_capability["aws_ec2_resource_inventory"].source == "aws_ec2"
