"""The seven ways a secret enters a request (FR-008), each asserted once.

The value of a declarative injection is that these are the only seven, and each
is tested here rather than once per vendor. A vendor that wants its key in a
query string gets ``QueryParameterInjection`` and inherits this test; the
alternative — a branch per vendor — would be eighty-five paths of which some
number are wrong in a way nobody looks at until a 401.

The last group is about the rule rather than the injections: an integration that
declares no host permits nothing and one that declares no injection sends
unauthenticated requests, so both are refused at construction. Failing when the
rule is written is much better than failing when it is used, because the person
who wrote it is the person who can fix it.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest

from platform.credentials.errors import UnknownIntegration
from platform.credentials.proxy.injection import (
    AUTHORIZATION_HEADER,
    BasicAuthInjection,
    BearerTokenInjection,
    BodyFieldInjection,
    HeaderInjection,
    InjectionRule,
    InjectionRuleRegistry,
    PathSegmentInjection,
    QueryParameterInjection,
    SignatureInjection,
)
from platform.credentials.proxy.model import OutboundRequest

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
VALUES = {
    "api_key": "the-key",
    "token": "the-token",
    "user": "svc",
    "password": "p4ss",
}


def a_request(*, url: str = "https://api.vendor.example/v1/logs", body: bytes | None = None):
    """Return a bare request for an injection to act on."""
    return OutboundRequest(method="GET", url=url, headers={}, body=body)


# -- the seven ----------------------------------------------------------------


def test_a_header_injection_sets_the_header() -> None:
    injected = HeaderInjection(header="X-Api-Key", field="api_key").apply(
        a_request(), VALUES, now=NOW
    )

    assert injected.headers["X-Api-Key"] == "the-key"


def test_a_header_injection_can_wrap_the_value_in_a_template() -> None:
    """Some vendors want the value in the middle, not only as a prefix."""
    injected = HeaderInjection(
        header="Authorization", field="api_key", template="Token token={value}"
    ).apply(a_request(), VALUES, now=NOW)

    assert injected.headers["Authorization"] == "Token token=the-key"


def test_a_query_parameter_injection_adds_to_the_query_string() -> None:
    injected = QueryParameterInjection(parameter="apiKey", field="api_key").apply(
        a_request(url="https://api.vendor.example/v1/logs?q=error"), VALUES, now=NOW
    )

    assert "apiKey=the-key" in injected.url
    assert "q=error" in injected.url


def test_a_query_parameter_replaces_rather_than_repeats() -> None:
    """Which of two same-named parameters a vendor picks is its framework's business."""
    injected = QueryParameterInjection(parameter="apiKey", field="api_key").apply(
        a_request(url="https://api.vendor.example/v1?apiKey=stale"), VALUES, now=NOW
    )

    assert injected.url.count("apiKey=") == 1
    assert "apiKey=the-key" in injected.url


def test_a_path_segment_injection_fills_its_placeholder() -> None:
    injected = PathSegmentInjection(placeholder="token", field="token").apply(
        a_request(url="https://api.vendor.example/services/{token}/events"), VALUES, now=NOW
    )

    assert injected.path == "/services/the-token/events"


def test_a_path_segment_injection_refuses_a_path_with_no_placeholder() -> None:
    """Sending a literal ``{token}`` gets a 404 that looks like a missing resource."""
    with pytest.raises(ValueError, match="path-segment injection"):
        PathSegmentInjection(placeholder="token", field="token").apply(
            a_request(url="https://api.vendor.example/services/events"), VALUES, now=NOW
        )


def test_a_body_field_injection_adds_to_a_json_body() -> None:
    injected = BodyFieldInjection(body_field="auth_token", field="token").apply(
        a_request(body=json.dumps({"query": "error"}).encode()), VALUES, now=NOW
    )

    assert injected.body is not None
    assert json.loads(injected.body) == {"query": "error", "auth_token": "the-token"}


def test_a_body_field_injection_refuses_a_body_that_is_not_a_json_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        BodyFieldInjection(body_field="auth_token", field="token").apply(
            a_request(body=b"[1, 2, 3]"), VALUES, now=NOW
        )


def test_basic_auth_encodes_the_pair() -> None:
    injected = BasicAuthInjection(username_field="user", password_field="password").apply(
        a_request(), VALUES, now=NOW
    )

    scheme, encoded = injected.headers[AUTHORIZATION_HEADER].split(" ", 1)
    assert scheme == "Basic"
    assert base64.b64decode(encoded).decode() == "svc:p4ss"


def test_a_bearer_injection_sets_the_authorization_header() -> None:
    injected = BearerTokenInjection(field="token").apply(a_request(), VALUES, now=NOW)

    assert injected.headers[AUTHORIZATION_HEADER] == "Bearer the-token"


def test_a_signature_injection_delegates_to_its_signer() -> None:
    class StubSigner:
        def fields(self) -> tuple[str, ...]:
            return ("api_key",)

        def sign(self, request, values, *, now):
            return request.with_header("X-Signature", f"signed-{values['api_key']}-{now.year}")

    injected = SignatureInjection(signer=StubSigner()).apply(a_request(), VALUES, now=NOW)

    assert injected.headers["X-Signature"] == "signed-the-key-2026"


# -- what an injection declares -----------------------------------------------


@pytest.mark.parametrize(
    ("injection", "expected"),
    [
        (HeaderInjection(header="X", field="api_key"), ("api_key",)),
        (QueryParameterInjection(parameter="k", field="api_key"), ("api_key",)),
        (PathSegmentInjection(placeholder="t", field="token"), ("token",)),
        (BodyFieldInjection(body_field="t", field="token"), ("token",)),
        (
            BasicAuthInjection(username_field="user", password_field="password"),
            ("user", "password"),
        ),
        (BearerTokenInjection(field="token"), ("token",)),
    ],
)
def test_every_injection_names_the_fields_it_reads(injection, expected) -> None:
    """What lets the catalogue suite catch a schema and a rule that have drifted."""
    assert injection.fields() == expected


# -- composition and the rule itself ------------------------------------------


def test_injections_compose_in_declared_order() -> None:
    rule = InjectionRule(
        integration="vendor",
        hosts=("api.vendor.example",),
        injections=(
            HeaderInjection(header="X-Api-Key", field="api_key"),
            BearerTokenInjection(field="token"),
        ),
    )

    injected = rule.apply(a_request(), VALUES, now=NOW)

    assert injected.headers["X-Api-Key"] == "the-key"
    assert injected.headers[AUTHORIZATION_HEADER] == "Bearer the-token"


def test_a_rule_reports_every_field_its_injections_read_once() -> None:
    rule = InjectionRule(
        integration="vendor",
        hosts=("api.vendor.example",),
        injections=(
            HeaderInjection(header="X-One", field="api_key"),
            HeaderInjection(header="X-Two", field="api_key"),
            BearerTokenInjection(field="token"),
        ),
    )

    assert rule.required_fields() == ("api_key", "token")


def test_a_rule_with_no_hosts_is_refused_when_it_is_written() -> None:
    with pytest.raises(ValueError, match="declares no hosts"):
        InjectionRule(
            integration="vendor",
            hosts=(),
            injections=(HeaderInjection(header="X", field="api_key"),),
        )


def test_a_rule_with_no_injection_is_refused_when_it_is_written() -> None:
    with pytest.raises(ValueError, match="unauthenticated"):
        InjectionRule(integration="vendor", hosts=("api.vendor.example",), injections=())


@pytest.mark.parametrize("host", ["https://api.vendor.example", "api.vendor.example:443"])
def test_an_allow_list_entry_is_a_host_and_not_a_url(host: str) -> None:
    """A port is not a security boundary, and including one makes the list wrong."""
    with pytest.raises(ValueError, match="not a host name"):
        InjectionRule(
            integration="vendor",
            hosts=(host,),
            injections=(HeaderInjection(header="X", field="api_key"),),
        )


def test_host_matching_is_case_insensitive_and_exact() -> None:
    """No wildcards: one delegated subdomain away from permitting somebody else's host."""
    rule = InjectionRule(
        integration="vendor",
        hosts=("api.vendor.example",),
        injections=(HeaderInjection(header="X", field="api_key"),),
    )

    assert rule.permits("API.Vendor.Example")
    assert not rule.permits("evil.api.vendor.example")
    assert not rule.permits("api.vendor.example.attacker.test")


def test_the_registry_names_what_it_knows_when_asked_for_what_it_does_not() -> None:
    registry = InjectionRuleRegistry.from_rules(
        InjectionRule(
            integration="vendor",
            hosts=("api.vendor.example",),
            injections=(HeaderInjection(header="X", field="api_key"),),
        )
    )

    with pytest.raises(UnknownIntegration) as raised:
        registry.get("typo")

    assert "vendor" in str(raised.value)
