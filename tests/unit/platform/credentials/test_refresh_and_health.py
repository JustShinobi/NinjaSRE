"""Short-lived credentials, and what the platform can say about a credential it cannot read.

Two halves of FR-013 are tested here and they are different behaviours.
Refreshing *ahead* of expiry is preventive: a credential inside the margin is
renewed before the request goes out, so a long vendor call cannot outlive the
token it started with. Retrying *after* an expiry rejection is corrective: the
vendor rejected something that had not reached its declared expiry, which means
the clocks disagree or the vendor revoked early.

Exactly one retry, and the test that asserts it is
``test_a_second_expiry_rejection_is_not_retried_again``. A second attempt would
be an attempt against a credential that has already been refreshed once, so the
failure is something other than expiry — repeating it spends the vendor's rate
limit to learn nothing.

The health half is the other side of the same coin: an operator has to be able
to tell "not configured" from "expired" from "the key that wrote this is gone",
because those are three different actions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.security import CREDENTIAL_REFRESH_MARGIN_SECONDS
from platform.credentials.errors import VaultKeyMismatch
from platform.credentials.health import (
    CredentialHealth,
    CredentialHealthState,
    verify_startup,
)
from platform.credentials.proxy.errors import ProxyErrorReason
from platform.credentials.proxy.refresh import (
    RefreshedCredential,
    is_expiry_failure,
    needs_refresh,
)
from tests.unit.platform.credentials.conftest import (
    INTEGRATION,
    OTHER_TEAM_ID,
    TEAM_ID,
    Harness,
    build_harness,
    json_response,
)
from tests.unit.platform.credentials.test_proxy_engine import FIRST_KEY, SECOND_KEY, request

pytestmark = pytest.mark.unit

AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


# -- the refresh window -------------------------------------------------------


def test_a_credential_with_no_expiry_is_never_refreshed() -> None:
    """Refreshing on a schedule nobody declared is how a working key gets replaced."""
    assert not needs_refresh(None, AT)


def test_a_credential_outside_the_margin_is_left_alone() -> None:
    assert not needs_refresh(AT + timedelta(seconds=CREDENTIAL_REFRESH_MARGIN_SECONDS + 1), AT)


def test_a_credential_inside_the_margin_is_refreshed() -> None:
    assert needs_refresh(AT + timedelta(seconds=CREDENTIAL_REFRESH_MARGIN_SECONDS - 1), AT)


def test_a_credential_already_past_its_expiry_is_refreshed() -> None:
    assert needs_refresh(AT - timedelta(hours=1), AT)


@pytest.mark.parametrize("status", [401, 403])
def test_the_statuses_that_mean_the_credential_was_rejected(status: int) -> None:
    """403 is included: several vendors answer an expired token with one."""
    assert is_expiry_failure(status)


@pytest.mark.parametrize("status", [200, 404, 429, 500])
def test_other_statuses_are_not_an_expiry_failure(status: int) -> None:
    assert not is_expiry_failure(status)


# -- refreshing ahead of expiry -----------------------------------------------


async def test_a_credential_expiring_mid_request_is_refreshed_first() -> None:
    """The request goes out with the fresh token, not the one about to die."""
    harness = await build_harness(now=AT, with_refresher=True)
    await harness.vault.store(
        harness.scope(),
        harness.handle(),
        {"api_key": FIRST_KEY},
        expires_at=AT + timedelta(seconds=5),
    )
    harness.refresher.issued.append(
        RefreshedCredential(values={"api_key": SECOND_KEY}, expires_at=AT + timedelta(hours=1))
    )
    harness.sender.responses.append(json_response({}))

    response = await harness.engine.forward(request())

    assert response.status_code == 200
    assert harness.refresher.calls == 1
    assert harness.sender.keys_seen() == (SECOND_KEY,)


async def test_a_refresh_the_vendor_refuses_fails_the_call_rather_than_sending_a_stale_key() -> (
    None
):
    harness = await build_harness(now=AT, with_refresher=True)
    await harness.vault.store(
        harness.scope(),
        harness.handle(),
        {"api_key": FIRST_KEY},
        expires_at=AT + timedelta(seconds=5),
    )
    harness.refresher.fails = True

    with pytest.raises(Exception) as raised:
        await harness.engine.forward(request())

    assert raised.value.reason is ProxyErrorReason.REFRESH_FAILED  # type: ignore[attr-defined]
    assert harness.sender.sent == []


# -- the single retry after an expiry rejection -------------------------------


async def test_a_rejected_credential_is_refreshed_and_the_request_retried_once() -> None:
    harness = await build_harness(now=AT, rule=_refreshable_rule(), with_refresher=True)
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.refresher.issued.append(
        RefreshedCredential(values={"api_key": SECOND_KEY}, expires_at=AT + timedelta(hours=1))
    )
    harness.sender.responses.extend(
        [json_response({"error": "expired"}, status=401), json_response({"ok": True})]
    )

    response = await harness.engine.forward(request())

    assert response.status_code == 200
    assert harness.refresher.calls == 1
    assert harness.sender.keys_seen() == (FIRST_KEY, SECOND_KEY)


async def test_a_second_expiry_rejection_is_not_retried_again() -> None:
    """FR-013's "exactly once". The second failure is not expiry, so repeating is waste."""
    harness = await build_harness(now=AT, rule=_refreshable_rule(), with_refresher=True)
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.refresher.issued.append(
        RefreshedCredential(values={"api_key": SECOND_KEY}, expires_at=AT + timedelta(hours=1))
    )
    harness.sender.responses.extend(
        [
            json_response({"error": "expired"}, status=401),
            json_response({"error": "still no"}, status=401),
        ]
    )

    response = await harness.engine.forward(request())

    assert response.status_code == 401
    assert len(harness.sender.sent) == 2
    assert harness.refresher.calls == 1


async def test_an_integration_that_is_not_refreshable_does_not_retry_a_401() -> None:
    """A long-lived key rejected with a 401 is a wrong key, and refreshing it is nonsense."""
    harness = await build_harness(now=AT, with_refresher=True)
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})
    harness.sender.responses.append(json_response({"error": "nope"}, status=401))

    response = await harness.engine.forward(request())

    assert response.status_code == 401
    assert len(harness.sender.sent) == 1
    assert harness.refresher.calls == 0


def test_a_refreshed_credential_does_not_print_its_values() -> None:
    """``repr`` reaches tracebacks and pytest output, and a secret escapes once."""
    refreshed = RefreshedCredential(values={"api_key": FIRST_KEY}, expires_at=AT)

    assert FIRST_KEY not in repr(refreshed)
    assert "api_key" in repr(refreshed)


# -- health, without reading anything -----------------------------------------


async def test_health_reports_a_configured_integration(harness: Harness) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})

    report = await CredentialHealth(vault=harness.vault).report(
        harness.scope(), integrations=(INTEGRATION,), team_id=TEAM_ID
    )

    assert report.healthy
    assert report.entries[0].state is CredentialHealthState.CONFIGURED
    assert report.entries[0].version == 1


async def test_health_tells_missing_apart_from_expired(harness: Harness) -> None:
    """Two different operator actions, so two different states."""
    await harness.vault.store(
        harness.scope(),
        harness.handle(),
        {"api_key": FIRST_KEY},
        expires_at=AT - timedelta(days=1),
    )

    report = await CredentialHealth(vault=harness.vault).report(
        harness.scope(), integrations=(INTEGRATION, "never-configured"), team_id=TEAM_ID, now=AT
    )

    by_name = {entry.integration: entry.state for entry in report.entries}
    assert by_name[INTEGRATION] is CredentialHealthState.EXPIRED
    assert by_name["never-configured"] is CredentialHealthState.MISSING
    assert not report.healthy
    assert len(report.unusable) == 2


async def test_health_follows_the_same_fallback_the_proxy_does(harness: Harness) -> None:
    """Reporting a team as unconfigured when its calls succeed would be a false alarm."""
    await harness.vault.store(harness.scope(), harness.handle().fallback(), {"api_key": FIRST_KEY})

    report = await CredentialHealth(vault=harness.vault).report(
        harness.scope(), integrations=(INTEGRATION,), team_id=OTHER_TEAM_ID
    )

    assert report.entries[0].state is CredentialHealthState.CONFIGURED
    assert report.entries[0].handle.endswith("/-")


async def test_the_health_record_carries_no_credential_material(harness: Harness) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})

    report = await CredentialHealth(vault=harness.vault).report(
        harness.scope(), integrations=(INTEGRATION,), team_id=TEAM_ID
    )

    assert FIRST_KEY not in str(report.to_record())


async def test_a_deployment_whose_credentials_all_decrypt_starts(harness: Harness) -> None:
    await harness.vault.store(harness.scope(), harness.handle(), {"api_key": FIRST_KEY})

    await verify_startup(harness.vault, harness.scope())


async def test_a_wrong_key_fails_at_boot_rather_than_at_three_in_the_morning(
    harness: Harness,
) -> None:
    """The failure this exists to move: a key that did not survive a restore."""

    class UndecryptableVault:
        async def undecryptable(self, scope: object) -> tuple[str, ...]:
            return ("acme-monitoring/payments@v1",)

    with pytest.raises(VaultKeyMismatch) as raised:
        await verify_startup(UndecryptableVault(), harness.scope())  # type: ignore[arg-type]

    assert "acme-monitoring/payments@v1" in str(raised.value)
    assert "restore the original key" in str(raised.value).lower()


def _refreshable_rule():
    """Return the harness rule marked as carrying a short-lived credential."""
    from dataclasses import replace

    from tests.unit.platform.credentials.conftest import RULE

    return replace(RULE, refreshable=True)
