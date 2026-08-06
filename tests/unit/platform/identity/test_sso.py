"""Signing in through the operator's provider, and the mapping that follows.

The interesting assertions are about the failure paths, because the happy path
of an OIDC flow is well-trodden and the failure paths are where a deployment
locks itself out: a configuration activated without ever completing a sign-in, a
provider that stops returning group claims, a redirect replayed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.security import OIDC_CODE_CHALLENGE_METHOD
from platform.identity import oidc
from platform.identity.errors import SsoConfigInvalid, SsoExchangeFailed, SsoNotVerified
from platform.identity.sso_config import (
    ClaimMapping,
    SsoConfig,
    SsoTestResult,
    activate,
    map_groups,
)

AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
PAYMENTS = "payments"
PLATFORM = "platform"
EVERYONE = "everyone"


def config(**changes: object) -> SsoConfig:
    """Return a valid provider configuration, with ``changes`` applied."""
    settings: dict[str, object] = {
        "provider": "okta",
        "issuer": "https://acme.okta.com",
        "client_id": "0oa1234",
        "authorisation_endpoint": "https://acme.okta.com/oauth2/v1/authorize",
        "token_endpoint": "https://acme.okta.com/oauth2/v1/token",
        "jwks_uri": "https://acme.okta.com/oauth2/v1/keys",
        "redirect_uri": "https://ninjasre.acme.example/auth/callback",
        "group_to_node": {"sre-payments": PAYMENTS, "sre-platform": PLATFORM},
        "default_node_id": EVERYONE,
    }
    settings.update(changes)
    return SsoConfig(**settings)  # type: ignore[arg-type]


def claims(**changes: object) -> dict[str, object]:
    """Return a verified claim set, with ``changes`` applied."""
    payload: dict[str, object] = {
        "iss": "https://acme.okta.com",
        "sub": "00u1234",
        "email": "ada@acme.example",
        "name": "Ada Lovelace",
        "groups": ["sre-payments", "engineering"],
        "exp": (AT + timedelta(minutes=5)).timestamp(),
    }
    payload.update(changes)
    return payload


# --- Configuration ------------------------------------------------------------


def test_a_configuration_over_plain_http_is_refused() -> None:
    """An identity flow that is not encrypted is not one."""
    with pytest.raises(SsoConfigInvalid) as raised:
        config(issuer="http://acme.okta.com")
    assert "https" in str(raised.value)


def test_a_configuration_without_a_default_team_is_refused() -> None:
    """An unmapped user has to have somewhere to land."""
    with pytest.raises(SsoConfigInvalid):
        config(default_node_id=None)


def test_a_configuration_without_the_openid_scope_is_refused() -> None:
    """Without it the provider issues no identity token and the flow reads nothing."""
    with pytest.raises(SsoConfigInvalid):
        config(scopes=("profile", "email"))


# --- Test before activate -----------------------------------


def test_an_untested_configuration_cannot_be_activated() -> None:
    """A misconfiguration cannot reach live sign-in."""
    with pytest.raises(SsoNotVerified):
        activate(config(), None)


def test_a_failed_test_does_not_permit_activation() -> None:
    """A test that ran is not a test that passed."""
    settings = config()
    failed = SsoTestResult(fingerprint=settings.fingerprint, succeeded=False)
    with pytest.raises(SsoNotVerified):
        activate(settings, failed)


def test_a_passing_test_permits_activation() -> None:
    """The positive control, so the refusals above are not vacuous."""
    settings = config()
    passed = SsoTestResult(fingerprint=settings.fingerprint, succeeded=True)
    assert activate(settings, passed).is_active


def test_editing_a_configuration_invalidates_its_test() -> None:
    """A result belongs to the settings that produced it, not to the provider.

    Without this, an operator could test a working configuration, change the
    client id, and activate the change on the strength of the old result.
    """
    tested = config()
    passed = SsoTestResult(fingerprint=tested.fingerprint, succeeded=True)
    edited = config(client_id="0oa-different")

    with pytest.raises(SsoNotVerified):
        activate(edited, passed)


def test_a_cosmetic_difference_does_not_invalidate_a_test() -> None:
    """The fingerprint covers what changes a sign-in, and only that."""
    tested = config()
    passed = SsoTestResult(fingerprint=tested.fingerprint, succeeded=True)
    assert activate(config(is_active=False), passed).is_active


# --- Group mapping ----------------------------------


def test_a_mapped_group_decides_the_team() -> None:
    """The ordinary case."""
    mapped = map_groups(config(), ("sre-payments",))
    assert mapped.node_id == PAYMENTS
    assert not mapped.used_default


def test_the_first_mapped_group_wins_when_somebody_is_in_two() -> None:
    """Deterministic, and in the order the directory returned them."""
    assert map_groups(config(), ("sre-platform", "sre-payments")).node_id == PLATFORM


def test_no_group_claims_falls_back_to_the_default_and_says_so() -> None:
    """The fallback is recorded rather than silent."""
    mapped = map_groups(config(), ())
    assert mapped.node_id == EVERYONE
    assert mapped.used_default


def test_groups_nobody_mapped_fall_back_too() -> None:
    """A directory carries groups this deployment has never heard of."""
    mapped = map_groups(config(), ("finance", "all-staff"))
    assert mapped.node_id == EVERYONE
    assert mapped.used_default


# --- The flow -----------------------------------------------------------------


def test_the_authorisation_request_uses_pkce_with_a_hashed_challenge() -> None:
    """Authorization code with PKCE, and never the ``plain`` method."""
    request = oidc.begin(config(), clock=lambda: AT)

    assert f"code_challenge_method={OIDC_CODE_CHALLENGE_METHOD}" in request.url
    assert "response_type=code" in request.url
    assert request.verifier not in request.url
    assert request.challenge in request.url


def test_two_authorisation_requests_never_share_a_state_or_verifier() -> None:
    """Both are what tie a redirect to a request we made."""
    first = oidc.begin(config(), clock=lambda: AT)
    second = oidc.begin(config(), clock=lambda: AT)
    assert first.state != second.state
    assert first.verifier != second.verifier


def test_a_redirect_can_be_claimed_once() -> None:
    """A replayed callback finds nothing, which is what one-time state means."""
    pending = oidc.PendingAuthorisations(clock=lambda: AT)
    request = oidc.begin(config(), clock=lambda: AT)
    pending.remember(request)

    assert pending.claim(request.state).verifier == request.verifier
    with pytest.raises(SsoExchangeFailed):
        pending.claim(request.state)


def test_an_abandoned_sign_in_expires_rather_than_accumulating() -> None:
    """A redirect nobody completed is not a replay window left open."""
    clock = _Clock()
    pending = oidc.PendingAuthorisations(clock=clock)
    pending.remember(oidc.begin(config(), clock=clock))
    assert len(pending) == 1

    clock.now += oidc.AUTHORISATION_TTL + timedelta(seconds=1)
    pending.prune()
    assert len(pending) == 0


def test_verified_claims_become_an_identity_with_its_team() -> None:
    """The whole point of the exchange, in one assertion."""
    identity = oidc.read_claims(config(), claims(), now=AT)

    assert identity.subject == "00u1234"
    assert identity.email == "ada@acme.example"
    assert identity.display_name == "Ada Lovelace"
    assert identity.node_id == PAYMENTS
    assert not identity.used_default_team


def test_claims_from_another_issuer_are_refused() -> None:
    """A token from a provider we did not configure is not a sign-in."""
    with pytest.raises(SsoExchangeFailed):
        oidc.read_claims(config(), claims(iss="https://evil.example"), now=AT)


def test_expired_claims_are_refused() -> None:
    """Beyond the skew tolerance, which the next test asserts exists."""
    stale = claims(exp=(AT - timedelta(hours=1)).timestamp())
    with pytest.raises(SsoExchangeFailed):
        oidc.read_claims(config(), stale, now=AT)


def test_claims_that_expired_within_the_skew_tolerance_are_accepted() -> None:
    """Two hosts' clocks disagree, and a sign-in should not be the casualty."""
    borderline = claims(exp=(AT - timedelta(seconds=10)).timestamp())
    assert oidc.read_claims(config(), borderline, now=AT).subject == "00u1234"


def test_claims_without_a_subject_or_an_email_are_refused() -> None:
    """A principal with neither cannot be stored or named in an audit row."""
    with pytest.raises(SsoExchangeFailed):
        oidc.read_claims(config(), claims(sub=""), now=AT)
    with pytest.raises(SsoExchangeFailed):
        oidc.read_claims(config(), claims(email=""), now=AT)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(["sre-payments"], id="list"),
        pytest.param("sre-payments engineering", id="space-separated"),
        pytest.param("sre-payments,engineering", id="comma-separated"),
    ],
)
def test_the_group_claim_is_read_whichever_shape_the_provider_used(value: object) -> None:
    """A deployment does not get to choose how its directory spells this."""
    assert oidc.read_claims(config(), claims(groups=value), now=AT).node_id == PAYMENTS


def test_a_provider_returning_no_groups_still_signs_in() -> None:
    """The group fallback, at the level a user experiences it."""
    identity = oidc.read_claims(config(), claims(groups=None), now=AT)
    assert identity.node_id == EVERYONE
    assert identity.used_default_team


def test_a_renamed_group_claim_is_honoured() -> None:
    """ "groups" is spelled four ways across the providers operators run."""
    settings = config(claims=ClaimMapping(groups="roles"))
    payload = claims(groups=None)
    payload["roles"] = ["sre-platform"]

    assert oidc.read_claims(settings, payload, now=AT).node_id == PLATFORM


def test_group_membership_is_read_fresh_at_each_sign_in() -> None:
    """Nothing about a team survives from the previous session."""
    settings = config()
    before = oidc.read_claims(settings, claims(groups=["sre-payments"]), now=AT)
    after = oidc.read_claims(settings, claims(groups=["sre-platform"]), now=AT)

    assert before.node_id == PAYMENTS
    assert after.node_id == PLATFORM


class _Clock:
    """A clock a test moves on purpose."""

    def __init__(self) -> None:
        self.now = AT

    def __call__(self) -> datetime:
        return self.now
