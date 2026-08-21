"""The reference integration, proving the row of FR-018's table it sits on.

Kubernetes is the case where NinjaSRE cannot know the host, so the operator
declares the allow-list. Its official client's transport can be replaced but
its credential loading cannot, which is exactly the shape Article IV forbids —
so the client is written directly on the shared base instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from integrations._base.retry import RetryPolicy
from integrations._base.transport import InProcessProxyTransport, RequestContext
from integrations.kubernetes import IN_CLUSTER_HOST, KUBERNETES, KubernetesClient
from integrations.kubernetes.schema import rule_for as kubernetes_rule_for
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy
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

pytestmark = pytest.mark.contract

ORG_ID = "acme"
TEAM_ID = "payments"
CONTEXT = RequestContext(org_id=ORG_ID, team_id=TEAM_ID, capability="reference_probe")
SCOPE = TenantScope(org_id=ORG_ID, team_node_id=TEAM_ID)

NO_RETRY = RetryPolicy(max_attempts=1)


@dataclass(slots=True)
class Vendor:
    """The far side of the proxy: records requests, answers from a queue."""

    responses: list[OutboundResponse] = field(default_factory=list)
    sent: list[OutboundRequest] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        """Record ``request`` and answer with the next scripted response."""
        self.sent.append(request)
        return (
            self.responses.pop(0)
            if self.responses
            else OutboundResponse(200, {"content-type": "application/json"}, b"{}")
        )


async def stand_up(
    descriptor: IntegrationDescriptor,
    credential: dict[str, str],
    *,
    rule: InjectionRule | None = None,
) -> tuple[InProcessProxyTransport, Vendor]:
    """Return a transport onto a proxy holding ``credential`` for ``descriptor``."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    schemas = CredentialSchemaRegistry.from_schemas(descriptor.schema)
    await Vault(gateway=gateway, schemas=schemas).store(
        SCOPE,
        CredentialHandle(integration=descriptor.name, team_id=TEAM_ID),
        credential,
    )

    vendor = Vendor()
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(rule if rule is not None else descriptor.rule),
        sender=vendor,
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
    )
    return InProcessProxyTransport(create_proxy_app(engine)), vendor


def json_body(payload: object) -> OutboundResponse:
    """Return a scripted 200 carrying ``payload``."""
    return OutboundResponse(200, {"content-type": "application/json"}, json.dumps(payload).encode())


# -- Kubernetes: the operator declares the allow-list -------------------------


KUBERNETES_CREDENTIAL = {"token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IiJ9.sentinel", "cluster": "prod"}


async def test_the_kubernetes_token_arrives_as_a_bearer_header() -> None:
    transport, vendor = await stand_up(KUBERNETES, KUBERNETES_CREDENTIAL)
    vendor.responses.append(json_body({"items": []}))
    client = KubernetesClient(transport=transport, context=CONTEXT, retry=NO_RETRY)

    await client.events(namespace="production", object_name="checkout-7f4c")

    assert vendor.sent[0].headers["Authorization"] == f"Bearer {KUBERNETES_CREDENTIAL['token']}"
    assert "involvedObject.name%3Dcheckout-7f4c" in vendor.sent[0].url


async def test_an_operator_declared_api_server_is_permitted_and_others_are_not() -> None:
    """The property FR-009 wants holds; what changes is who declares the hosts."""
    rule = kubernetes_rule_for("k8s.acme.example")

    assert rule.permits("k8s.acme.example")
    assert rule.permits(IN_CLUSTER_HOST), "an in-cluster worker must keep working"
    assert not rule.permits("k8s.attacker.example")


async def test_kubernetes_reaches_an_operator_declared_endpoint() -> None:
    transport, vendor = await stand_up(
        KUBERNETES, KUBERNETES_CREDENTIAL, rule=kubernetes_rule_for("k8s.acme.example")
    )
    vendor.responses.append(json_body({"kind": "Pod"}))
    client = KubernetesClient(
        transport=transport, context=CONTEXT, api_server="k8s.acme.example", retry=NO_RETRY
    )

    await client.pod("checkout-7f4c", namespace="production")

    assert vendor.sent[0].host == "k8s.acme.example"


async def test_the_kubernetes_verifier_separates_a_bad_token_from_bad_rbac() -> None:
    """Two answers that send an operator to completely different places."""
    transport, vendor = await stand_up(KUBERNETES, KUBERNETES_CREDENTIAL)
    vendor.responses.append(OutboundResponse(403, {}, b"forbidden"))

    result = await KUBERNETES.verifier.probe(transport, CONTEXT)

    assert not result.ok
    assert "role binding" in result.detail


# -- FR-018, per vendor -------------------------------------------------------


def test_the_reference_integration_records_its_sdk_decision() -> None:
    assert KUBERNETES.sdk_strategy is SdkStrategy.DIRECT_CLIENT
    assert len(KUBERNETES.strategy_note.split()) > 20, (
        "a one-line rationale is not a decision anybody can review"
    )


def test_no_integration_may_declare_the_strategy_that_exists_to_be_refused() -> None:
    """There is no in-process-credential exception, and the type says so."""
    with pytest.raises(ValueError, match="no in-process-credential exception"):
        IntegrationDescriptor(
            name=KUBERNETES.name,
            schema=KUBERNETES.schema,
            rule=KUBERNETES.rule,
            verifier=KUBERNETES.verifier,
            client_class=KubernetesClient,
            sdk_strategy=SdkStrategy.NO_EXCEPTION_GRANTED,
            strategy_note="the SDK insists",
        )


def test_the_schema_and_the_rule_have_not_drifted() -> None:
    """A field rename on one side sends an unauthenticated request and gets a 401."""
    assert KUBERNETES.undeclared_injection_fields() == ()
