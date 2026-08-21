"""The base client: FR-016's six behaviours, and the one thing it will not do.

Every vendor client inherits these, so they are tested once here rather than
eighty-five times. The retry and pagination bounds are the ones worth reading
closely — both exist because an unbounded version of them has produced a real
outage, and both fail *loudly* rather than quietly returning less than was asked
for.

The last group is the constructor. A client cannot be built holding a credential
because there is no parameter for one, and a client that does not declare an
integration cannot be built at all — the proxy would have no rule to apply and
the request would leave unauthenticated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from core.capability.result import CapabilityErrorClass
from integrations._base.client import (
    MAX_RESPONSE_BYTES,
    ClientResponse,
    IntegrationClient,
)
from integrations._base.errors import (
    IntegrationError,
    IntegrationErrorReason,
    reason_for_status,
)
from integrations._base.pagination import MAX_PAGES_PER_CALL, Page, collect, iterate
from integrations._base.retry import (
    MAX_HONOURED_RETRY_AFTER_SECONDS,
    RetryPolicy,
    parse_retry_after,
)
from integrations._base.transport import RequestContext
from platform.credentials.proxy.errors import (
    CredentialUnavailable,
    EgressDenied,
    TenantRateLimited,
)
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

pytestmark = pytest.mark.unit

CONTEXT = RequestContext(org_id="acme", team_id="payments", capability="vendor_search")


@dataclass(slots=True)
class ScriptedTransport:
    """A proxy that answers from a queue and remembers what it was asked."""

    responses: list[OutboundResponse | Exception] = field(default_factory=list)
    seen: list[ProxyRequest] = field(default_factory=list)

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Return the next scripted answer, raising it if it is an exception."""
        self.seen.append(request)
        answer = self.responses.pop(0) if self.responses else OutboundResponse(200, {}, b"{}")
        if isinstance(answer, Exception):
            raise answer
        return answer


class VendorClient(IntegrationClient):
    """A minimal client, standing in for any of the eighty-five."""

    integration = "vendor"


def a_client(
    transport: ScriptedTransport,
    *,
    retry: RetryPolicy | None = None,
) -> VendorClient:
    """Return a client on ``transport``, with retries off unless asked for."""
    return VendorClient(
        transport=transport,
        context=CONTEXT,
        base_url="https://api.vendor.example",
        retry=retry if retry is not None else RetryPolicy(max_attempts=1),
    )


def ok(payload: object) -> OutboundResponse:
    """Return a scripted 200 carrying ``payload`` as JSON."""
    return OutboundResponse(200, {"content-type": "application/json"}, json.dumps(payload).encode())


# -- proxy routing ------------------------------------------------------------


async def test_the_request_carries_the_context_and_no_credential() -> None:
    transport = ScriptedTransport()

    await a_client(transport).get("/v1/logs", params={"q": "error"})

    sent = transport.seen[0]
    assert sent.integration == "vendor"
    assert sent.org_id == "acme"
    assert sent.team_id == "payments"
    assert sent.capability == "vendor_search"
    assert sent.url == "https://api.vendor.example/v1/logs?q=error"


async def test_a_relative_path_is_resolved_against_the_base_url() -> None:
    transport = ScriptedTransport()

    await a_client(transport).get("v1/logs")

    assert transport.seen[0].url == "https://api.vendor.example/v1/logs"


async def test_an_absolute_url_is_used_as_given() -> None:
    """How a client follows a vendor's own pagination link. The allow-list still applies."""
    transport = ScriptedTransport()

    await a_client(transport).get("https://api.vendor.example/v1/logs?cursor=abc")

    assert transport.seen[0].url == "https://api.vendor.example/v1/logs?cursor=abc"


async def test_a_json_body_is_encoded_and_declared() -> None:
    transport = ScriptedTransport()

    await a_client(transport).post("/v1/search", json_body={"query": "error"})

    sent = transport.seen[0]
    assert sent.body == b'{"query": "error"}'
    assert sent.headers["content-type"] == "application/json"


async def test_a_request_carries_either_json_or_bytes_and_not_both() -> None:
    with pytest.raises(ValueError, match="not both"):
        await a_client(ScriptedTransport()).request("POST", "/v1", json_body={"a": 1}, body=b"raw")


# -- structured errors --------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, IntegrationErrorReason.INVALID_REQUEST),
        (401, IntegrationErrorReason.UNAUTHENTICATED),
        (403, IntegrationErrorReason.FORBIDDEN),
        (404, IntegrationErrorReason.NOT_FOUND),
        (429, IntegrationErrorReason.RATE_LIMITED),
        (500, IntegrationErrorReason.UPSTREAM_ERROR),
        (503, IntegrationErrorReason.UPSTREAM_ERROR),
        (418, IntegrationErrorReason.INVALID_REQUEST),
    ],
)
def test_a_vendor_status_maps_to_a_classification(
    status: int, expected: IntegrationErrorReason
) -> None:
    assert reason_for_status(status) is expected


async def test_a_vendor_error_names_the_call_that_produced_it() -> None:
    transport = ScriptedTransport(responses=[OutboundResponse(404, {}, b"no such log group")])

    with pytest.raises(IntegrationError) as raised:
        await a_client(transport).get("/v1/logs")

    assert raised.value.status_code == 404
    assert "GET /v1/logs" in str(raised.value)
    assert "no such log group" in str(raised.value)


async def test_a_proxy_refusal_arrives_classified_rather_than_as_a_status() -> None:
    transport = ScriptedTransport(
        responses=[
            CredentialUnavailable(
                "vendor", handle="vendor/payments", org_id="acme", team_id="payments"
            )
        ]
    )

    with pytest.raises(CredentialUnavailable):
        await a_client(transport).get("/v1/logs")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            CredentialUnavailable("v", handle="v/t", org_id="o", team_id="t"),
            CapabilityErrorClass.PERMISSION_DENIED,
        ),
        (EgressDenied("v", host="x", allowed=("y",)), CapabilityErrorClass.PERMISSION_DENIED),
        (
            TenantRateLimited("v", org_id="o", limit=1, window_seconds=60.0),
            CapabilityErrorClass.RATE_LIMITED,
        ),
    ],
)
def test_a_proxy_refusal_becomes_a_capability_error_the_model_can_act_on(
    error: Exception, expected: CapabilityErrorClass
) -> None:
    """FR-012. The loop reads the classification and decides what to do next."""
    translated = IntegrationError.from_proxy(error)  # type: ignore[arg-type]

    assert translated.to_capability_error().classification is expected


async def test_a_response_larger_than_the_bound_is_refused_rather_than_truncated() -> None:
    """A quietly shortened answer is how an investigation concludes nothing happened."""
    transport = ScriptedTransport(
        responses=[OutboundResponse(200, {}, b"x" * (MAX_RESPONSE_BYTES + 1))]
    )

    with pytest.raises(IntegrationError, match="Narrow the query"):
        await a_client(transport).get("/v1/logs")


def test_a_body_that_is_not_json_says_so_rather_than_raising_a_decode_error() -> None:
    with pytest.raises(ValueError, match="not JSON"):
        ClientResponse(status_code=200, body=b"<html>oops</html>").json()


# -- retry --------------------------------------------------------------------


async def test_a_retryable_failure_is_retried_and_can_succeed() -> None:
    transport = ScriptedTransport(responses=[OutboundResponse(503, {}, b"down"), ok({"ok": True})])
    client = a_client(
        transport, retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0, jitter_ratio=0.0)
    )

    response = await client.get("/v1/logs")

    assert response.json() == {"ok": True}
    assert len(transport.seen) == 2


async def test_a_non_retryable_failure_is_not_retried() -> None:
    """Re-sending invalid arguments produces the same invalid arguments."""
    transport = ScriptedTransport(responses=[OutboundResponse(400, {}, b"bad"), ok({"ok": True})])
    client = a_client(transport, retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0))

    with pytest.raises(IntegrationError):
        await client.get("/v1/logs")
    assert len(transport.seen) == 1


async def test_the_attempt_ceiling_is_the_number_of_calls_and_not_of_retries() -> None:
    transport = ScriptedTransport(responses=[OutboundResponse(503, {}, b"") for _ in range(5)])
    client = a_client(
        transport, retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0, jitter_ratio=0.0)
    )

    with pytest.raises(IntegrationError):
        await client.get("/v1/logs")
    assert len(transport.seen) == 3


def test_the_delay_grows_and_is_capped() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=4.0, jitter_ratio=0.0)

    assert [policy.delay_for(n, jitter=0.5) for n in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 4.0]


def test_jitter_spreads_the_retry_around_the_backoff() -> None:
    """Several capabilities retrying at the same instant is the herd that caused the limit."""
    policy = RetryPolicy(base_delay_seconds=1.0, jitter_ratio=0.5)

    assert policy.delay_for(1, jitter=0.0) == pytest.approx(0.5)
    assert policy.delay_for(1, jitter=1.0) == pytest.approx(1.5)


def test_a_vendors_own_retry_after_wins_over_the_backoff() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0)

    assert policy.delay_for(1, retry_after=7.0) == 7.0


def test_an_unreasonable_retry_after_is_capped_rather_than_honoured() -> None:
    """An investigation that sleeps for an hour has already failed."""
    policy = RetryPolicy()

    assert policy.delay_for(1, retry_after=3600.0) == MAX_HONOURED_RETRY_AFTER_SECONDS


@pytest.mark.parametrize(
    ("header", "expected"),
    [("12", 12.0), ("0", 0.0), ("", None), (None, None), ("-1", None), ("Wed, 21 Oct 2015", None)],
)
def test_retry_after_parses_the_delta_seconds_form_only(
    header: str | None, expected: float | None
) -> None:
    """Parsing an HTTP-date in the wrong timezone produces a wait of hours."""
    assert parse_retry_after(header) == expected


async def test_a_rate_limited_response_carries_the_vendors_wait_into_the_retry() -> None:
    transport = ScriptedTransport(
        responses=[OutboundResponse(429, {"Retry-After": "0"}, b"slow down"), ok({"ok": True})]
    )
    client = a_client(transport, retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.0))

    response = await client.get("/v1/logs")

    assert response.status_code == 200
    assert len(transport.seen) == 2


def test_a_retry_policy_that_permits_no_attempt_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one attempt"):
        RetryPolicy(max_attempts=0)


# -- pagination ---------------------------------------------------------------


async def test_a_page_walk_follows_the_cursor_to_the_end() -> None:
    pages = {None: Page((1, 2), cursor="a"), "a": Page((3,), cursor=None)}

    collected = await collect(lambda cursor: _ready(pages[cursor]))

    assert collected.items == (1, 2, 3)
    assert collected.pages_followed == 2
    assert not collected.truncated


async def test_a_cursor_that_never_terminates_is_bounded_and_says_so() -> None:
    """A vendor whose next-page token points at the same page under load."""
    collected = await collect(lambda _cursor: _ready(Page((1,), cursor="always")), max_pages=3)

    assert collected.pages_followed == 3
    assert collected.truncated


async def test_an_item_ceiling_truncates_and_says_so() -> None:
    """The caller has to pass ``truncated`` on, or "no more" and "we stopped" merge."""
    collected = await collect(
        lambda _cursor: _ready(Page((1, 2, 3, 4, 5), cursor="more")), max_items=3
    )

    assert collected.items == (1, 2, 3)
    assert collected.truncated


async def test_a_single_complete_page_is_not_truncated() -> None:
    collected = await collect(lambda _cursor: _ready(Page((1, 2), cursor=None)), max_items=10)

    assert collected.items == (1, 2)
    assert not collected.truncated


async def test_streaming_respects_the_same_page_bound() -> None:
    seen = [item async for item in iterate(lambda _cursor: _ready(Page((1,), cursor="always")))]

    assert len(seen) == MAX_PAGES_PER_CALL


# -- the constructor ----------------------------------------------------------


def test_a_client_that_declares_no_integration_cannot_be_built() -> None:
    """The proxy would have no rule, so the request would leave unauthenticated."""

    class Nameless(IntegrationClient):
        pass

    with pytest.raises(ValueError, match="does not declare an integration"):
        Nameless(transport=ScriptedTransport(), context=CONTEXT, base_url="https://api.example")


def test_the_base_client_has_no_parameter_for_a_credential() -> None:
    """FR-015, as a property of the signature rather than of a convention."""
    import inspect

    parameters = set(inspect.signature(IntegrationClient.__init__).parameters)

    assert parameters == {
        "self",
        "transport",
        "context",
        "base_url",
        "retry",
        "timeout_seconds",
    }


def test_the_request_context_carries_nothing_that_could_be_a_secret() -> None:
    fields = set(RequestContext.__dataclass_fields__)

    assert fields == {"org_id", "team_id", "capability"}


async def _ready(page: Page[int]) -> Page[int]:
    """Return ``page``, for a fetch callable that needs no I/O."""
    return page
