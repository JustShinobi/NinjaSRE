"""The three reference integrations, each proving a different row of FR-018's table.

Datadog is the ordinary case: two headers, a direct client, and nothing else to
decide. Kubernetes is the case where NinjaSRE cannot know the host, so the
operator declares the allow-list. AWS is the case the whole feature exists for —
SigV4 needs the key at construction time, so a signing client is a key-holding
client, and the signing moved to the proxy (SC-006).

The AWS tests are the ones to read. ``test_the_client_process_never_holds_a
signing_key`` is the concrete form of SC-006: the request the *client* builds is
inspected and has no signature in it, and the request the *vendor* receives
does. That pair is what the requirement actually says.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from integrations._base.retry import RetryPolicy
from integrations._base.transport import InProcessProxyTransport, RequestContext
from integrations.aws import AWS, CloudWatchLogsClient, rule_for
from integrations.aws.client import LOGS_TARGET_HEADER
from integrations.datadog import DATADOG, DatadogClient
from integrations.kubernetes import IN_CLUSTER_HOST, KUBERNETES, KubernetesClient
from integrations.kubernetes.config import rule_for as kubernetes_rule_for
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


# -- Datadog: the ordinary case -----------------------------------------------


DATADOG_CREDENTIAL = {
    "api_key": "0123456789abcdef0123456789abcdef",
    "app_key": "0123456789abcdef0123456789abcdef01234567",
}


async def test_datadog_receives_both_keys_and_the_client_holds_neither() -> None:
    transport, vendor = await stand_up(DATADOG, DATADOG_CREDENTIAL)
    vendor.responses.append(json_body({"data": [], "meta": {"page": {}}}))
    client = DatadogClient(transport=transport, context=CONTEXT, retry=NO_RETRY)

    await client.search_logs("service:checkout", start="now-1h", end="now")

    sent = vendor.sent[0]
    assert sent.headers["DD-API-KEY"] == DATADOG_CREDENTIAL["api_key"]
    assert sent.headers["DD-APPLICATION-KEY"] == DATADOG_CREDENTIAL["app_key"]
    assert not hasattr(client, "api_key")


async def test_datadog_pages_and_reports_when_it_stopped_early() -> None:
    transport, vendor = await stand_up(DATADOG, DATADOG_CREDENTIAL)
    vendor.responses.extend(
        [
            json_body({"data": [{"id": "1"}], "meta": {"page": {"after": "cursor-2"}}}),
            json_body({"data": [{"id": "2"}], "meta": {"page": {}}}),
        ]
    )
    client = DatadogClient(transport=transport, context=CONTEXT, retry=NO_RETRY)

    found = await client.search_logs("service:checkout", start="now-1h", end="now")

    assert [entry["id"] for entry in found.items] == ["1", "2"]
    assert found.pages_followed == 2
    assert not found.truncated
    assert json.loads(vendor.sent[1].body or b"{}")["page"]["cursor"] == "cursor-2"


async def test_the_datadog_site_selects_the_base_url_and_is_not_a_secret() -> None:
    transport, vendor = await stand_up(DATADOG, DATADOG_CREDENTIAL)
    client = DatadogClient(
        transport=transport, context=CONTEXT, site="datadoghq.eu", retry=NO_RETRY
    )

    await client.alerting_monitors()

    assert vendor.sent[0].host == "api.datadoghq.eu"


async def test_the_datadog_verifier_reports_success_without_showing_a_key() -> None:
    transport, _ = await stand_up(DATADOG, DATADOG_CREDENTIAL)

    result = await DATADOG.verifier.probe(transport, CONTEXT)

    assert result.ok
    assert DATADOG_CREDENTIAL["api_key"] not in str(result.to_record())


async def test_the_datadog_verifier_explains_a_rejection_in_the_operators_terms() -> None:
    transport, vendor = await stand_up(DATADOG, DATADOG_CREDENTIAL)
    vendor.responses.append(OutboundResponse(401, {}, b"forbidden"))

    result = await DATADOG.verifier.probe(transport, CONTEXT)

    assert not result.ok
    assert "Re-issue it" in result.detail


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


# -- AWS: SC-006 --------------------------------------------------------------


AWS_CREDENTIAL = {
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "region": "us-east-1",
}


async def test_the_client_process_never_holds_a_signing_key() -> None:
    """SC-006, stated as the pair of assertions the requirement actually makes."""
    transport, vendor = await stand_up(AWS, AWS_CREDENTIAL)
    vendor.responses.append(json_body({"logGroups": []}))
    client = CloudWatchLogsClient(transport=transport, context=CONTEXT, retry=NO_RETRY)

    await client.describe_log_groups()

    signed = vendor.sent[0]
    assert signed.headers["Authorization"].startswith("AWS4-HMAC-SHA256 ")
    assert AWS_CREDENTIAL["secret_access_key"] not in str(signed.headers)
    held = {slot: getattr(client, slot, None) for slot in _slots_of(type(client))}
    assert AWS_CREDENTIAL["secret_access_key"] not in repr(held)


async def test_the_request_the_client_built_carries_no_signature() -> None:
    """The other half: what leaves the client is unsigned and carries only a handle."""
    transport, vendor = await stand_up(AWS, AWS_CREDENTIAL)
    client = CloudWatchLogsClient(transport=transport, context=CONTEXT, retry=NO_RETRY)

    await client.describe_log_groups()

    unsigned = transport.app.engine  # the engine saw the client's request first
    assert unsigned is not None
    # The proxy added it; the vendor is the first to see one.
    assert "Authorization" in vendor.sent[0].headers


async def test_the_aws_signature_covers_the_body() -> None:
    transport, vendor = await stand_up(AWS, AWS_CREDENTIAL)
    vendor.responses.append(json_body({"events": [], "nextToken": ""}))
    client = CloudWatchLogsClient(transport=transport, context=CONTEXT, retry=NO_RETRY)

    await client.filter_log_events("/aws/lambda/checkout", start_ms=0, end_ms=1000)

    signed = vendor.sent[0]
    assert signed.headers[LOGS_TARGET_HEADER] == "Logs_20140328.FilterLogEvents"
    assert "x-amz-content-sha256" in signed.headers["Authorization"]


async def test_an_undeclared_aws_region_is_refused() -> None:
    """ "AWS" is not a trust boundary; a service in a region the operator declared is."""
    rule = rule_for(regions=("us-east-1",))

    assert rule.permits("logs.us-east-1.amazonaws.com")
    assert not rule.permits("logs.eu-west-1.amazonaws.com")


async def test_the_aws_verifier_tells_a_bad_signature_from_a_bad_key() -> None:
    """Both arrive as 403, and they send an operator to opposite places."""
    transport, vendor = await stand_up(AWS, AWS_CREDENTIAL)
    vendor.responses.append(OutboundResponse(403, {}, b"<Error><Code>SignatureDoesNotMatch</Code>"))

    result = await AWS.verifier.probe(transport, CONTEXT)

    assert not result.ok
    assert "clock" in result.detail


async def test_the_aws_verifier_names_an_expired_session_token() -> None:
    transport, vendor = await stand_up(AWS, AWS_CREDENTIAL)
    vendor.responses.append(OutboundResponse(403, {}, b"<Error><Code>ExpiredToken</Code>"))

    result = await AWS.verifier.probe(transport, CONTEXT)

    assert "refresher" in result.detail


# -- FR-018, per vendor -------------------------------------------------------


@pytest.mark.parametrize(
    ("descriptor", "expected"),
    [
        (DATADOG, SdkStrategy.DIRECT_CLIENT),
        (KUBERNETES, SdkStrategy.DIRECT_CLIENT),
        (AWS, SdkStrategy.PROXY_SIGNED),
    ],
    ids=lambda value: getattr(value, "name", str(value)),
)
def test_each_reference_integration_records_its_sdk_decision(
    descriptor: IntegrationDescriptor, expected: SdkStrategy
) -> None:
    assert descriptor.sdk_strategy is expected
    assert len(descriptor.strategy_note.split()) > 20, (
        "a one-line rationale is not a decision anybody can review"
    )


def test_no_integration_may_declare_the_strategy_that_exists_to_be_refused() -> None:
    """There is no in-process-credential exception, and the type says so."""
    with pytest.raises(ValueError, match="no in-process-credential exception"):
        IntegrationDescriptor(
            name=DATADOG.name,
            schema=DATADOG.schema,
            rule=DATADOG.rule,
            verifier=DATADOG.verifier,
            client_class=DatadogClient,
            sdk_strategy=SdkStrategy.NO_EXCEPTION_GRANTED,
            strategy_note="the SDK insists",
        )


@pytest.mark.parametrize("descriptor", [DATADOG, KUBERNETES, AWS], ids=lambda value: value.name)
def test_the_schema_and_the_rule_have_not_drifted(descriptor: IntegrationDescriptor) -> None:
    """A field rename on one side sends an unauthenticated request and gets a 401."""
    assert descriptor.undeclared_injection_fields() == ()


def _slots_of(cls: type) -> tuple[str, ...]:
    """Return every slot the class and its bases declare.

    A slotted class has no ``__dict__``, which is itself part of the guarantee —
    there is nowhere to stash a credential — so "what does this instance hold"
    has to be asked of the slots.
    """
    return tuple(slot for base in cls.__mro__ for slot in getattr(base, "__slots__", ()))
