"""Human sessions: signed, bounded twice, and revocable before they expire.

A session is a signed value rather than a row, because validating one is on the
path of every request a human makes and a database read there buys nothing — the
cookie already carries everything the check needs. What a signed value cannot do
is stop being valid early, so revocation is a list of the sessions that have been
withdrawn, which is small by construction: it only ever holds sessions that were
signed out or revoked *and* have not yet reached their absolute expiry.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.security import (
    SESSION_ABSOLUTE_LIFETIME_SECONDS,
    SESSION_IDLE_TIMEOUT_SECONDS,
)
from platform.identity.errors import SessionRejected
from platform.identity.sessions import (
    InMemoryRevocationList,
    SessionSigner,
    SessionStore,
)

ORG = "acme"
WHO = "ada"
AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

IDLE = timedelta(seconds=SESSION_IDLE_TIMEOUT_SECONDS)
ABSOLUTE = timedelta(seconds=SESSION_ABSOLUTE_LIFETIME_SECONDS)


class Clock:
    """A clock a test moves on purpose."""

    def __init__(self, now: datetime = AT) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def store(clock: Clock, *, key: bytes = b"a-deployment-signing-key") -> SessionStore:
    """Return a session store with a fixed clock."""
    return SessionStore(signer=SessionSigner(key=key), clock=clock)


def test_a_new_session_carries_both_bounds() -> None:
    """An idle timeout and an absolute lifetime, both from named constants."""
    sessions = store(Clock())
    issued = sessions.issue(principal_id=WHO, org_id=ORG)

    assert issued.session.issued_at == AT
    assert issued.session.last_seen_at == AT
    assert issued.session.expires_at == AT + ABSOLUTE


def test_a_fresh_session_validates_to_its_principal() -> None:
    """The happy path, and the shape a transport receives."""
    sessions = store(Clock())
    issued = sessions.issue(principal_id=WHO, org_id=ORG)

    validated = sessions.validate(issued.cookie)
    assert validated.principal_id == WHO
    assert validated.org_id == ORG


def test_a_tampered_payload_is_refused() -> None:
    """The signature is the whole of the trust in a stateless session.

    The payload is rewritten properly — decoded, edited, re-encoded — rather
    than string-substituted, because base64 would swallow a naive substitution
    and the test would pass against a store that checked nothing.
    """
    sessions = store(Clock())
    issued = sessions.issue(principal_id=WHO, org_id=ORG)

    body, _, signature = issued.cookie.partition(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["sub"] = "mallory"
    forged_body = (
        base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode().rstrip("=")
    )

    with pytest.raises(SessionRejected):
        sessions.validate(f"{forged_body}.{signature}")


def test_a_cookie_signed_by_another_deployment_is_refused() -> None:
    """A session from a staging environment is not a session here."""
    elsewhere = store(Clock(), key=b"a-different-key")
    issued = elsewhere.issue(principal_id=WHO, org_id=ORG)

    with pytest.raises(SessionRejected):
        store(Clock()).validate(issued.cookie)


def test_a_malformed_cookie_is_refused_rather_than_crashing() -> None:
    """Untrusted input reaches this function before anything else does."""
    sessions = store(Clock())
    for rubbish in ("", "not-a-session", "a.b", "...."):
        with pytest.raises(SessionRejected):
            sessions.validate(rubbish)


def test_a_session_past_its_absolute_lifetime_is_refused() -> None:
    """The bound that a busy user cannot extend."""
    clock = Clock()
    sessions = store(clock)
    issued = sessions.issue(principal_id=WHO, org_id=ORG)

    clock.advance(ABSOLUTE + timedelta(seconds=1))
    with pytest.raises(SessionRejected):
        sessions.validate(issued.cookie)


def test_a_session_left_idle_is_refused() -> None:
    """The bound that an unattended laptop crosses."""
    clock = Clock()
    sessions = store(clock)
    issued = sessions.issue(principal_id=WHO, org_id=ORG)

    clock.advance(IDLE + timedelta(seconds=1))
    with pytest.raises(SessionRejected):
        sessions.validate(issued.cookie)


def test_touching_a_session_pushes_the_idle_bound_but_not_the_absolute_one() -> None:
    """Activity keeps a session alive, up to the point where nothing does."""
    clock = Clock()
    sessions = store(clock)
    issued = sessions.issue(principal_id=WHO, org_id=ORG)

    cookie = issued.cookie
    for _ in range(4):
        clock.advance(IDLE - timedelta(minutes=1))
        cookie = sessions.touch(cookie).cookie

    assert sessions.validate(cookie).principal_id == WHO

    clock.advance(ABSOLUTE)
    with pytest.raises(SessionRejected):
        sessions.validate(cookie)


def test_a_revoked_session_is_refused_before_it_expires() -> None:
    """What signing out has to mean, given the cookie itself stays valid."""
    sessions = store(Clock())
    issued = sessions.issue(principal_id=WHO, org_id=ORG)

    sessions.revoke(issued.session.session_id)
    with pytest.raises(SessionRejected):
        sessions.validate(issued.cookie)


def test_revoking_every_session_a_principal_holds() -> None:
    """What a password reset, a role removal, or an incident reaches for."""
    sessions = store(Clock())
    mine = [sessions.issue(principal_id=WHO, org_id=ORG) for _ in range(3)]
    theirs = sessions.issue(principal_id="grace", org_id=ORG)

    sessions.revoke_for_principal(WHO)

    for issued in mine:
        with pytest.raises(SessionRejected):
            sessions.validate(issued.cookie)
    assert sessions.validate(theirs.cookie).principal_id == "grace"


def test_the_revocation_list_forgets_sessions_that_have_expired_anyway() -> None:
    """The list stays small because an expired session needs no entry.

    Without this it grows without bound in a deployment nobody restarts, which
    is the failure mode of every revocation list ever written.
    """
    clock = Clock()
    withdrawals = InMemoryRevocationList()
    sessions = SessionStore(
        signer=SessionSigner(key=b"a-deployment-signing-key"),
        revoked=withdrawals,
        clock=clock,
    )
    issued = sessions.issue(principal_id=WHO, org_id=ORG)
    sessions.revoke(issued.session.session_id)
    assert len(withdrawals) == 1

    clock.advance(ABSOLUTE + timedelta(seconds=1))
    sessions.prune()
    assert len(withdrawals) == 0


def test_concurrent_sessions_for_one_user_are_independent() -> None:
    """The edge case the specification names: one person, several surfaces."""
    sessions = store(Clock())
    console = sessions.issue(principal_id=WHO, org_id=ORG)
    cli = sessions.issue(principal_id=WHO, org_id=ORG)

    assert console.session.session_id != cli.session.session_id

    sessions.revoke(console.session.session_id)
    with pytest.raises(SessionRejected):
        sessions.validate(console.cookie)
    assert sessions.validate(cli.cookie).principal_id == WHO


def test_a_session_remembers_the_groups_its_sign_in_produced() -> None:
    """Re-evaluating groups needs something to compare the next sign-in against."""
    sessions = store(Clock())
    issued = sessions.issue(
        principal_id=WHO, org_id=ORG, node_id="payments", groups=("sre", "payments")
    )
    validated = sessions.validate(issued.cookie)

    assert validated.node_id == "payments"
    assert validated.groups == ("sre", "payments")


def test_a_break_glass_session_says_so_on_the_value_itself() -> None:
    """Everything downstream has to be able to tell, including the audit trail."""
    sessions = store(Clock())
    issued = sessions.issue(principal_id="break-glass", org_id=ORG, break_glass=True)
    assert sessions.validate(issued.cookie).break_glass
