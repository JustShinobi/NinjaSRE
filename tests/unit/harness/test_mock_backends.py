"""The vendor boundary: what it serves, what it answers when it has nothing, and
what it remembers.

Three properties are asserted here and each one is a requirement the corpus
depends on. A recorded response reaches the agent through the *real* client and
the *real* proxy (FR-007), so a scenario fails when the client breaks rather
than only when the agent does. A call nothing recorded gets an empty-but-valid
answer instead of an error (FR-008), so exploring beyond a scenario's evidence
is a normal thing to do. And every call is remembered (FR-010), because
trajectory scoring is about what the agent actually did.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from integrations._base.access import IntegrationAccess, bind, restore
from integrations._catalogue.discovery import catalogue as integration_catalogue
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from tests.harness.backends import backend_for, registry
from tests.harness.backends.base import (
    GENERIC_BACKEND,
    MockVendorBoundary,
    VendorStack,
    stand_up,
    synthesise_credential,
)
from tests.harness.backends.recording import REDACTED, RecordingSender, scrub, scrub_document
from tests.harness.loader import EvidenceFixture, RecordedResponse, ResponseMatch
from tests.synthetic.integration_scenarios import capability_named

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 7, 12, 30, tzinfo=UTC)
ORG_ID = "acme"
TEAM_ID = "payments"


def _fixture(
    *responses: RecordedResponse, integration: str = "kubernetes", filename: str = "kubernetes.json"
) -> EvidenceFixture:
    return EvidenceFixture(
        filename=filename,
        integration=integration,
        evidence_source=integration,
        responses=responses,
    )


def _request(url: str, *, method: str = "GET") -> OutboundRequest:
    return OutboundRequest(method=method, url=url)


def _declared(integration: str) -> tuple[Any, ...]:
    """Return every attribute an integration's tools package binds."""
    import importlib

    return tuple(vars(importlib.import_module(f"integrations.{integration}.tools")).values())


# -- serving and falling back -------------------------------------------------


async def test_a_recorded_response_is_served_to_the_call_that_matches_it() -> None:
    boundary = MockVendorBoundary(
        fixtures=(
            _fixture(
                RecordedResponse(
                    match=ResponseMatch(path_contains="/events"), body={"items": [{"a": 1}]}
                )
            ),
        ),
        hosts={"cluster.example": "kubernetes"},
    )

    answer = await boundary.send(
        _request("https://cluster.example/api/v1/events"), timeout_seconds=5.0
    )

    assert json.loads(answer.body) == {"items": [{"a": 1}]}
    assert boundary.calls[0].matched
    assert boundary.calls[0].fixture == "kubernetes.json"


async def test_an_unmatched_call_answers_empty_but_valid_rather_than_an_error() -> None:
    """FR-008: 'nothing there' is a finding; 'the tool is broken' changes behaviour."""
    boundary = MockVendorBoundary(
        backends={"kubernetes": backend_for("kubernetes")},
        hosts={"cluster.example": "kubernetes"},
    )

    answer = await boundary.send(
        _request("https://cluster.example/api/v1/pods"), timeout_seconds=5.0
    )

    assert answer.status_code == 200
    assert json.loads(answer.body)["items"] == []
    assert boundary.unmatched and not boundary.calls[0].matched


async def test_the_narrowest_recorded_response_wins_whatever_the_file_order() -> None:
    broad = RecordedResponse(match=ResponseMatch(path_contains="/api"), body={"which": "broad"})
    narrow = RecordedResponse(
        match=ResponseMatch(path_contains="/api/v1/namespaces/payments/events"),
        body={"which": "narrow"},
    )
    boundary = MockVendorBoundary(
        fixtures=(_fixture(broad, narrow),), hosts={"cluster.example": "kubernetes"}
    )

    answer = await boundary.send(
        _request("https://cluster.example/api/v1/namespaces/payments/events"), timeout_seconds=5.0
    )

    assert json.loads(answer.body) == {"which": "narrow"}


async def test_every_call_is_recorded_whether_or_not_anything_answered_it() -> None:
    """FR-010: a call that found nothing is still a call the agent chose to make."""
    boundary = MockVendorBoundary(
        fixtures=(_fixture(RecordedResponse(match=ResponseMatch(path_contains="/events"))),),
        hosts={"cluster.example": "kubernetes"},
    )

    await boundary.send(_request("https://cluster.example/api/v1/events"), timeout_seconds=5.0)
    await boundary.send(_request("https://cluster.example/api/v1/pods"), timeout_seconds=5.0)

    assert [call.matched for call in boundary.calls] == [True, False]
    assert boundary.reached_integrations == {"kubernetes"}
    assert boundary.reached_hosts == {"cluster.example"}


async def test_a_fixture_for_another_integration_never_answers_this_vendor() -> None:
    boundary = MockVendorBoundary(
        fixtures=(
            _fixture(
                RecordedResponse(match=ResponseMatch(path_contains="/api"), body={"wrong": True}),
                integration="datadog",
                filename="datadog.json",
            ),
        ),
        backends={"kubernetes": backend_for("kubernetes")},
        hosts={"cluster.example": "kubernetes"},
    )

    answer = await boundary.send(
        _request("https://cluster.example/api/v1/pods"), timeout_seconds=5.0
    )

    assert json.loads(answer.body)["items"] == []


# -- registration -------------------------------------------------------------


def test_a_backend_is_found_by_walking_rather_than_by_being_listed() -> None:
    """T021: a new integration adds a module, not a change to the harness."""
    found = registry()

    assert {"kubernetes", "github", "grafana", "loki", "prometheus"} <= set(found)
    for integration, backend in found.items():
        assert backend.integration == integration


def test_an_integration_with_no_module_falls_back_to_the_generic_json_vendor() -> None:
    assert backend_for("a-vendor-nobody-wrote-a-module-for") is GENERIC_BACKEND


@pytest.mark.parametrize(
    ("integration", "url", "expected"),
    [
        ("kubernetes", "https://h/api/v1/pods", {"items": []}),
        ("prometheus", "https://h/api/v1/query?query=up", {"status": "success"}),
        ("loki", "https://h/loki/api/v1/query_range", {"status": "success"}),
    ],
)
def test_each_backends_empty_answer_is_the_shape_its_client_parses(
    integration: str, url: str, expected: dict[str, Any]
) -> None:
    answer = backend_for(integration).empty_for(_request(url))

    document = json.loads(answer.body)
    for key, value in expected.items():
        assert document[key] == value


def test_the_kubernetes_log_subresource_answers_text_rather_than_a_document() -> None:
    answer = backend_for("kubernetes").empty_for(
        _request("https://h/api/v1/namespaces/payments/pods/checkout/log")
    )

    assert answer.headers["content-type"] == "text/plain"
    assert answer.body == b""


# -- credentials, so a new integration needs none written -------------------


def test_every_integration_in_the_catalogue_gets_a_schema_valid_credential() -> None:
    """SC-005 for credentials: contributing a scenario writes no secret at all."""
    for entry in integration_catalogue():
        schema = entry.descriptor.schema
        schema.validate(synthesise_credential(schema))


# -- the real client path -----------------------------------------------------


async def _kubernetes_stack(*fixtures: EvidenceFixture) -> VendorStack:
    return await stand_up(("kubernetes",), fixtures, org_id=ORG_ID, team_id=TEAM_ID, at=AT)


async def _invoke(stack: VendorStack, capability: str, arguments: dict[str, Any]) -> Any:
    tool = capability_named(capability, _declared("kubernetes"))
    previous = bind(IntegrationAccess(transport=stack.transport, org_id=ORG_ID, team_id=TEAM_ID))
    try:
        return await tool.invoke(arguments)
    finally:
        restore(previous)


async def test_a_recorded_response_reaches_the_agent_through_the_real_client_and_proxy() -> None:
    """FR-007: nothing between the capability and the wire is a stand-in."""
    stack = await _kubernetes_stack(
        _fixture(
            RecordedResponse(
                match=ResponseMatch(path_contains="/events"),
                body={
                    "items": [
                        {
                            "reason": "OOMKilled",
                            "type": "Warning",
                            "message": "Container checkout exceeded its memory limit",
                            "count": 3,
                            "involvedObject": {"name": "checkout-7f4c"},
                            "lastTimestamp": "2026-08-07T11:58:02Z",
                        }
                    ],
                    "metadata": {"continue": ""},
                },
            )
        )
    )

    result = await _invoke(
        stack,
        "kubernetes_workload_events",
        {"namespace": "payments", "object_name": "checkout-7f4c"},
    )

    assert result.succeeded
    assert "OOMKilled" in result.evidence[0].summary
    assert stack.boundary.matched


async def test_a_capability_the_scenario_planted_no_evidence_for_succeeds_and_finds_nothing() -> (
    None
):
    """FR-008 on the real path: the agent learns 'nothing there', not 'broken'."""
    stack = await _kubernetes_stack()

    result = await _invoke(
        stack,
        "kubernetes_workload_events",
        {"namespace": "payments", "object_name": "checkout-7f4c"},
    )

    assert result.succeeded, result.error
    assert stack.boundary.unmatched


async def test_the_boundary_is_only_ever_reached_on_a_host_the_integration_declared() -> None:
    """Article IV holds inside the harness too: the proxy is the real one."""
    stack = await _kubernetes_stack()
    await _invoke(
        stack, "kubernetes_workload_events", {"namespace": "payments", "object_name": "checkout"}
    )

    entries = {entry.name: entry for entry in integration_catalogue()}
    permitted = {host.lower() for host in entries["kubernetes"].descriptor.rule.hosts}

    assert stack.boundary.reached_hosts <= permitted


async def test_no_credential_value_appears_in_what_the_capability_returned() -> None:
    stack = await _kubernetes_stack()
    result = await _invoke(
        stack, "kubernetes_workload_events", {"namespace": "payments", "object_name": "checkout"}
    )

    rendered = repr(result)
    for value in stack.credentials["kubernetes"].values():
        if len(value) > 8:
            assert value not in rendered


# -- recording ----------------------------------------------------------------


class _LiveVendor:
    """Stands in for a real vendor during a recording session."""

    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.content_type = content_type

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        return OutboundResponse(200, {"content-type": self.content_type}, self.body)


async def test_a_recording_session_writes_a_fixture_the_loader_can_read(tmp_path: Any) -> None:
    """FR-011: fixtures come from real responses, through a documented procedure."""
    vendor = _LiveVendor(json.dumps({"items": [{"reason": "OOMKilled"}]}).encode("utf-8"))
    recorder = RecordingSender(inner=vendor, hosts={"cluster.example": "kubernetes"})

    await recorder.send(_request("https://cluster.example/api/v1/events"), timeout_seconds=5.0)
    written = recorder.write(tmp_path)

    from tests.harness.schemas import read_json, validate_evidence

    assert [path.name for path in written] == ["kubernetes.json"]
    document = validate_evidence(read_json(written[0]), path=written[0])
    assert document["integration"] == "kubernetes"
    assert document["responses"][0]["body"] == {"items": [{"reason": "OOMKilled"}]}


async def test_a_credential_echoed_back_by_a_vendor_is_scrubbed_before_it_is_written() -> None:
    token = "eyJhbGciOiJSUzI1NiIsImtpZCI6IiJ9.payload.signature"
    vendor = _LiveVendor(json.dumps({"detail": f"invalid token {token}"}).encode("utf-8"))
    recorder = RecordingSender(inner=vendor, hosts={"h": "kubernetes"}, secrets=(token,))

    await recorder.send(_request("https://h/api/v1/events"), timeout_seconds=5.0)

    written = json.dumps(recorder.documents())
    assert token not in written
    assert REDACTED in written


def test_scrubbing_removes_the_shapes_nobody_thought_to_name() -> None:
    body = (
        '{"access_key": "AKIAIOSFODNN7EXAMPLE", '
        '"api_key": "0123456789abcdef0123456789abcdef", '
        '"url": "https://vendor.example/x?X-Amz-Signature=abcdef0123456789abcdef"}'
    )

    cleaned = scrub(body)

    assert "AKIAIOSFODNN7EXAMPLE" not in cleaned
    assert "0123456789abcdef0123456789abcdef" not in cleaned
    assert "abcdef0123456789abcdef" not in cleaned


def test_scrubbing_leaves_the_document_shape_the_client_parses_intact() -> None:
    document = {"items": [{"token": "sekrit-value-here", "reason": "OOMKilled"}]}

    cleaned = scrub_document(document, secrets=("sekrit-value-here",))

    assert cleaned["items"][0]["reason"] == "OOMKilled"
    assert cleaned["items"][0]["token"] == REDACTED
