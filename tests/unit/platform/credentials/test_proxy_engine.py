"""The proxy's sequence, and the properties that depend on its order.

SC-004 and SC-007 live here, along with FR-009's allow-list and FR-014's rate
limit. Each is a claim about what the engine does *before* something else:
rotation takes effect because nothing caches, the allow-list runs before the
vault, one tenant's limit is counted separately from another's.

The one to read carefully is
``test_an_undeclared_host_is_refused_before_the_vault_is_touched``. It is not
asserting that a bad host is refused — the test above it does that — it is
asserting the *ordering*, by checking that no credential was ever resolved. A
proxy that refused the host after decrypting would pass every other test in this
file and would let a prompt-injected URL make the vault do work.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.security import CREDENTIAL_PROXY_MAX_REQUESTS_PER_TENANT
from platform.credentials.proxy.errors import (
    CredentialUnavailable,
    EgressDenied,
    IntegrationNotDeclared,
    ProxyErrorReason,
    TenantRateLimited,
    UpstreamUnreachable,
)
from platform.credentials.proxy.injection import HeaderInjection, InjectionRule
from platform.credentials.proxy.model import ProxyRequest
from platform.credentials.proxy.rate_limit import TenantRateLimiter
from platform.persistence.ports import AuditOutcome
from tests.unit.platform.credentials.conftest import (
    CAPABILITY,
    HOST,
    INTEGRATION,
    ORG_ID,
    OTHER_TEAM_ID,
    TEAM_ID,
    URL,
    Harness,
    build_harness,
    json_response,
)

pytestmark = pytest.mark.unit

FIRST_KEY = "111111111111111111111111"
SECOND_KEY = "222222222222222222222222"
OTHER_TEAM_KEY = "999999999999999999999999"


def request(*, team_id: str = TEAM_ID, url: str = URL, method: str = "GET") -> ProxyRequest:
    """Return a proxy request from a capability that holds no credential."""
    return ProxyRequest(
        integration=INTEGRATION,
        org_id=ORG_ID,
        team_id=team_id,
        capability=CAPABILITY,
        method=method,
        url=url,
    )


# -- the happy path -----------------------------------------------------------


async def test_the_credential_is_injected_at_the_edge(harness: Harness) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.append(json_response({"logs": []}))

    response = await harness.engine.forward(request())

    assert response.status_code == 200
    assert harness.sender.keys_seen() == (FIRST_KEY,)


async def test_the_request_that_arrives_at_the_proxy_carries_no_credential(
    harness: Harness,
) -> None:
    """The whole envelope is safe in a trace, which is why a handle is worth having."""
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})

    incoming = request()

    assert FIRST_KEY not in repr(incoming)
    assert FIRST_KEY not in str(incoming.headers)


# -- SC-004: rotation, with no restart ----------------------------------------


async def test_a_rotated_credential_takes_effect_on_the_next_request(
    harness: Harness,
) -> None:
    """SC-004. Nothing is cached, so there is nothing to invalidate."""
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.extend([json_response({}), json_response({})])

    await harness.engine.forward(request())
    await harness.vault.rotate(harness.scope(), harness.handle(), {"api_key": SECOND_KEY})
    await harness.engine.forward(request())

    assert harness.sender.keys_seen() == (FIRST_KEY, SECOND_KEY)


async def test_a_rollback_takes_effect_on_the_next_request_too(harness: Harness) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    await harness.vault.rotate(harness.scope(), harness.handle(), {"api_key": SECOND_KEY})
    harness.sender.responses.extend([json_response({}), json_response({})])

    await harness.engine.forward(request())
    await harness.vault.activate(harness.scope(), harness.handle(), 1)
    await harness.engine.forward(request())

    assert harness.sender.keys_seen() == (SECOND_KEY, FIRST_KEY)


# -- SC-007: per-team isolation -----------------------------------------------


async def test_two_teams_with_different_credentials_never_cross_resolve(
    harness: Harness,
) -> None:
    """SC-007. Same vendor, same organisation, two keys, and no path between them."""
    await harness.vault.store(harness.scope(), harness.handle(TEAM_ID), {"api_key": FIRST_KEY})
    await harness.vault.store(
        harness.scope(OTHER_TEAM_ID), harness.handle(OTHER_TEAM_ID), {"api_key": OTHER_TEAM_KEY}
    )
    harness.sender.responses.extend([json_response({}), json_response({})])

    await harness.engine.forward(request(team_id=TEAM_ID))
    await harness.engine.forward(request(team_id=OTHER_TEAM_ID))

    assert harness.sender.keys_seen() == (FIRST_KEY, OTHER_TEAM_KEY)


async def test_a_team_without_its_own_credential_uses_the_organisation_one(
    harness: Harness,
) -> None:
    await harness.vault.store(harness.scope(), harness.handle().fallback(), {"api_key": FIRST_KEY})
    harness.sender.responses.append(json_response({}))

    await harness.engine.forward(request(team_id=OTHER_TEAM_ID))

    assert harness.sender.keys_seen() == (FIRST_KEY,)


async def test_a_team_credential_wins_over_the_organisation_one(harness: Harness) -> None:
    await harness.vault.store(
        harness.scope(), harness.handle().fallback(), {"api_key": OTHER_TEAM_KEY}
    )
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.append(json_response({}))

    await harness.engine.forward(request())

    assert harness.sender.keys_seen() == (FIRST_KEY,)


# -- FR-009: the allow-list, and when it runs ---------------------------------


async def test_a_request_to_an_undeclared_host_is_rejected(harness: Harness) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})

    with pytest.raises(EgressDenied) as raised:
        await harness.engine.forward(request(url="https://attacker.example/collect"))

    assert raised.value.host == "attacker.example"
    assert HOST in str(raised.value)
    assert harness.sender.sent == []


async def test_an_undeclared_host_is_refused_before_the_vault_is_touched(
    harness: Harness,
) -> None:
    """The ordering assertion. A refusal after decryption would pass every other test."""
    with pytest.raises(EgressDenied):
        await harness.engine.forward(request(url="https://attacker.example/collect"))

    events = await harness.audit_events()
    assert len(events) == 1
    assert events[0].detail["reason"] == ProxyErrorReason.EGRESS_DENIED
    assert "handle" not in events[0].detail, (
        "a handle in the audit line means the vault was consulted before the host was checked"
    )


async def test_plain_http_is_refused_even_to_a_declared_host(harness: Harness) -> None:
    """A vendor reachable over HTTP is a vendor whose key is on the wire in clear."""
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})

    with pytest.raises(EgressDenied):
        await harness.engine.forward(request(url=f"http://{HOST}/v1/logs"))


async def test_an_integration_with_no_rule_cannot_send_anything(harness: Harness) -> None:
    unknown = ProxyRequest(
        integration="nowhere",
        org_id=ORG_ID,
        team_id=TEAM_ID,
        capability=CAPABILITY,
        method="GET",
        url=URL,
    )

    with pytest.raises(IntegrationNotDeclared) as raised:
        await harness.engine.forward(unknown)

    assert INTEGRATION in str(raised.value)
    assert harness.sender.sent == []


# -- FR-012: structured failure -----------------------------------------------


async def test_a_missing_credential_names_the_integration_and_the_handle(
    harness: Harness,
) -> None:
    with pytest.raises(CredentialUnavailable) as raised:
        await harness.engine.forward(request())

    record = raised.value.to_record()
    assert record["integration"] == INTEGRATION
    assert record["reason"] == ProxyErrorReason.CREDENTIAL_NOT_CONFIGURED
    assert record["retryable"] is False
    assert INTEGRATION in record["message"]


async def test_a_vendor_that_does_not_answer_is_told_apart_from_one_that_errors(
    harness: Harness,
) -> None:
    """Different operator actions, so different classifications."""
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.failures.append(ConnectionError("no route"))

    with pytest.raises(UpstreamUnreachable) as raised:
        await harness.engine.forward(request())

    assert raised.value.reason.retryable


async def test_a_vendor_error_status_comes_back_as_a_response(harness: Harness) -> None:
    """A 500 from the vendor is the vendor's answer, not the proxy's failure."""
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.append(json_response({"error": "boom"}, status=500))

    response = await harness.engine.forward(request())

    assert response.status_code == 500
    assert not response.succeeded


# -- FR-014: per-tenant rate limiting -----------------------------------------


def test_a_tenant_past_its_limit_is_refused_rather_than_queued() -> None:
    limiter = TenantRateLimiter(max_requests=2, window_seconds=60.0, clock=lambda: 0.0)

    limiter.check(ORG_ID)
    limiter.check(ORG_ID)

    with pytest.raises(TenantRateLimited) as raised:
        limiter.check(ORG_ID)
    assert raised.value.limit == 2
    assert raised.value.reason.retryable


def test_one_tenant_over_its_limit_does_not_affect_another() -> None:
    limiter = TenantRateLimiter(max_requests=1, window_seconds=60.0, clock=lambda: 0.0)

    limiter.check("noisy")
    with pytest.raises(TenantRateLimited):
        limiter.check("noisy")

    limiter.check("quiet")


def test_the_window_rolls_over() -> None:
    now = 0.0
    limiter = TenantRateLimiter(max_requests=1, window_seconds=10.0, clock=lambda: now)

    limiter.check(ORG_ID)
    with pytest.raises(TenantRateLimited):
        limiter.check(ORG_ID)

    now = 11.0
    limiter.check(ORG_ID)


def test_a_refused_request_still_counts() -> None:
    """Otherwise a tenant hammering past its limit gets a free window per failure."""
    limiter = TenantRateLimiter(max_requests=1, window_seconds=60.0, clock=lambda: 0.0)

    limiter.check(ORG_ID)
    for _ in range(3):
        with pytest.raises(TenantRateLimited):
            limiter.check(ORG_ID)

    assert limiter.snapshot()[ORG_ID] == 4


def test_the_default_limit_comes_from_a_named_constant() -> None:
    """Article II: a magic number at a call site is a defect."""
    assert TenantRateLimiter().max_requests == CREDENTIAL_PROXY_MAX_REQUESTS_PER_TENANT


async def test_the_rate_limit_runs_before_the_vault(harness: Harness) -> None:
    harness.limiter.max_requests = 0

    with pytest.raises(TenantRateLimited):
        await harness.engine.forward(request())

    events = await harness.audit_events()
    assert events[0].detail["reason"] == ProxyErrorReason.RATE_LIMITED
    assert "host" not in events[0].detail


# -- FR-019: the audit trail --------------------------------------------------


async def test_a_successful_resolution_is_recorded_without_the_value(
    harness: Harness,
) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.append(json_response({}))

    await harness.engine.forward(request())

    events = await harness.audit_events()
    assert len(events) == 1
    assert events[0].outcome is AuditOutcome.ALLOWED
    assert events[0].detail["integration"] == INTEGRATION
    assert events[0].detail["capability"] == CAPABILITY
    assert events[0].detail["team_id"] == TEAM_ID
    assert events[0].detail["version"] == 1
    assert FIRST_KEY not in str(events[0].detail)


async def test_the_audit_line_names_the_version_that_answered(harness: Harness) -> None:
    """ "The call that failed used version 3, and version 4 landed two minutes later"."""
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    await harness.vault.rotate(harness.scope(), harness.handle(), {"api_key": SECOND_KEY})
    harness.sender.responses.append(json_response({}))

    await harness.engine.forward(request())

    events = await harness.audit_events()
    assert events[0].detail["version"] == 2


async def test_every_refusal_is_audited(harness: Harness) -> None:
    """The denied resolutions are the ones an operator most needs to see."""
    with pytest.raises(CredentialUnavailable):
        await harness.engine.forward(request())
    with pytest.raises(EgressDenied):
        await harness.engine.forward(request(url="https://attacker.example/x"))

    events = await harness.audit_events()
    assert len(events) == 2
    assert all(event.outcome is AuditOutcome.DENIED for event in events)


# -- an optional credential: self-hosted vendors with no auth to hold ---------

OPTIONAL_RULE = InjectionRule(
    integration=INTEGRATION,
    hosts=(HOST,),
    injections=(HeaderInjection(header="X-Api-Key", field="api_key"),),
    credential_optional=True,
)


async def test_an_optional_credential_rule_forwards_bare_when_nothing_is_configured() -> None:
    harness = await build_harness(rule=OPTIONAL_RULE)
    harness.sender.responses.append(json_response({}))

    response = await harness.engine.forward(request())

    assert response.status_code == 200
    assert harness.sender.sent[0].headers.get("X-Api-Key") is None


async def test_an_optional_credential_rule_still_injects_one_that_is_configured() -> None:
    """The flag only relaxes absence: a rule with injections still authenticates a call it can."""
    harness = await build_harness(rule=OPTIONAL_RULE)
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.append(json_response({}))

    await harness.engine.forward(request())

    assert harness.sender.keys_seen() == (FIRST_KEY,)


async def test_an_optional_credential_call_without_one_is_still_audited_allowed() -> None:
    harness = await build_harness(rule=OPTIONAL_RULE)
    harness.sender.responses.append(json_response({}))

    await harness.engine.forward(request())

    events = await harness.audit_events()
    assert len(events) == 1
    assert events[0].outcome is AuditOutcome.ALLOWED
    assert events[0].detail["handle"]
    assert "version" not in events[0].detail


# -- health -------------------------------------------------------------------


async def test_health_reports_what_can_be_authenticated_and_no_more(
    harness: Harness,
) -> None:
    health = await harness.engine.health()

    assert health.ready
    assert health.integrations == (INTEGRATION,)
    assert "api_key" not in str(health.to_record())


# -- expiry -------------------------------------------------------------------


async def test_an_expiring_credential_without_a_refresher_fails_rather_than_being_used(
    harness: Harness,
) -> None:
    """Sending an expired credential would produce a 401 that blames the key."""
    expiry = datetime.now(UTC) + timedelta(seconds=1)
    await harness.vault.store(
        harness.scope(), harness.handle(), {"api_key": FIRST_KEY}, expires_at=expiry
    )

    with pytest.raises(Exception) as raised:
        await harness.engine.forward(request())

    assert raised.value.reason is ProxyErrorReason.CREDENTIAL_EXPIRED  # type: ignore[attr-defined]
    assert harness.sender.sent == []


async def test_a_credential_well_inside_its_expiry_is_used_unchanged() -> None:
    harness = await build_harness(with_refresher=True)
    await harness.vault.store(
        harness.scope(),
        harness.handle(),
        {"api_key": FIRST_KEY},
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    harness.sender.responses.append(json_response({}))

    await harness.engine.forward(request())

    assert harness.refresher.calls == 0
    assert harness.sender.keys_seen() == (FIRST_KEY,)
