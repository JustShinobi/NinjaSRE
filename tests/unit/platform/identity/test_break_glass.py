"""The way in when the identity provider is not, bounded and loud.

The suite is deliberately arranged so that the provider is *absent* rather than
mocked out: nothing in this file constructs an ``SsoConfig``, resolves a claim,
or reaches a directory, because the property being asserted is that none of that
is on the path. If break-glass needed any of it, this file would not compile.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.security import (
    BREAK_GLASS_MAX_DURATION_SECONDS,
    BREAK_GLASS_MIN_REASON_CHARS,
    BREAK_GLASS_PRINCIPAL_ID,
)
from platform.identity.audit.recorder import AuditRecorder
from platform.identity.break_glass import (
    BreakGlass,
    BreakGlassAccount,
    hash_secret,
    verify_secret,
)
from platform.identity.errors import BreakGlassRejected
from platform.identity.permissions import Permission
from platform.identity.sessions import SessionSigner, SessionStore
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

ORG = "acme"
AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
SECRET = "correct horse battery staple"
REASON = "the identity provider is returning 503 and nobody can sign in"
SOURCE = "203.0.113.7"

MAX_DURATION = timedelta(seconds=BREAK_GLASS_MAX_DURATION_SECONDS)


async def build(*, enabled: bool = True) -> tuple[BreakGlass, FakePersistence, TenantScope]:
    """Return a break-glass path over a tenant with no identity provider at all."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")

    return (
        BreakGlass(
            sessions=SessionStore(signer=SessionSigner(key=b"key"), clock=lambda: AT),
            account=BreakGlassAccount(secret_hash=hash_secret(SECRET), enabled=enabled),
            recorder=AuditRecorder(gateway=gateway, clock=lambda: AT),
            clock=lambda: AT,
        ),
        gateway,
        TenantScope(org_id=ORG),
    )


async def test_break_glass_works_with_no_identity_provider_present() -> None:
    """This is the path for when the provider is unreachable."""
    glass, _, scope = await build()
    issued = await glass.open(scope, secret=SECRET, reason=REASON, source_address=SOURCE)

    assert issued.session.principal_id == BREAK_GLASS_PRINCIPAL_ID
    assert issued.session.break_glass


async def test_a_break_glass_session_is_time_limited() -> None:
    """It should expire before the outage does."""
    glass, _, scope = await build()
    issued = await glass.open(scope, secret=SECRET, reason=REASON)

    assert issued.session.expires_at == AT + MAX_DURATION


async def test_a_break_glass_session_cannot_be_asked_to_last_longer() -> None:
    """The ceiling is not a default a caller talks past."""
    glass, _, scope = await build()
    glass.duration = MAX_DURATION + timedelta(hours=1)

    with pytest.raises(BreakGlassRejected):
        await glass.open(scope, secret=SECRET, reason=REASON)


async def test_the_wrong_secret_is_refused() -> None:
    """The obvious assertion, so the ones below are about a real credential."""
    glass, _, scope = await build()
    with pytest.raises(BreakGlassRejected):
        await glass.open(scope, secret="not it", reason=REASON)


async def test_a_disabled_account_is_refused() -> None:
    """A deployment that never wants this has no account to attack."""
    glass, _, scope = await build(enabled=False)
    with pytest.raises(BreakGlassRejected):
        await glass.open(scope, secret=SECRET, reason=REASON)


async def test_a_sign_in_without_a_stated_reason_is_refused() -> None:
    """The audit row six months later has to answer "why"."""
    glass, _, scope = await build()
    with pytest.raises(BreakGlassRejected):
        await glass.open(scope, secret=SECRET, reason="urgent")

    assert len("urgent") < BREAK_GLASS_MIN_REASON_CHARS


async def test_a_successful_sign_in_is_prominently_audited() -> None:
    """Prominently, meaning flagged rather than merely present."""
    glass, gateway, scope = await build()
    await glass.open(scope, secret=SECRET, reason=REASON, source_address=SOURCE)

    async with gateway.begin(scope) as uow:
        events = await uow.audit.query(action="break_glass.open")

    assert len(events) == 1
    assert events[0].detail["break_glass"] is True
    assert events[0].detail["reason"] == REASON
    assert events[0].detail["source_address"] == SOURCE


async def test_a_refused_attempt_is_audited_too() -> None:
    """Somebody guessing at this account is exactly what a reviewer wants to see."""
    glass, gateway, scope = await build()
    with pytest.raises(BreakGlassRejected):
        await glass.open(scope, secret="not it", reason=REASON, source_address=SOURCE)

    async with gateway.begin(scope) as uow:
        events = await uow.audit.query(action="break_glass.open")
    assert [event.detail["result"] for event in events] == ["rejected"]


async def test_the_break_glass_principal_can_repair_an_organisation() -> None:
    """The two reasons this path exists: the provider is down, or nobody is owner."""
    glass, _, _ = await build()
    assert glass.account is not None
    held = glass.account.permissions()

    assert held.allows(Permission.OWNER_ASSIGN)
    assert held.allows(Permission.SSO_MANAGE)
    assert held.allows(Permission.IDENTITY_WRITE)


async def test_every_action_in_a_break_glass_session_is_flagged() -> None:
    """Not just the sign-in: what was done under it has to be findable."""
    glass, _, _ = await build()
    context = glass.context(SOURCE)

    assert context.break_glass
    assert context.actor_id == BREAK_GLASS_PRINCIPAL_ID


def test_the_stored_secret_is_a_slow_hash_and_never_the_secret() -> None:
    """A passphrase's whole defence against an offline attack is the cost per guess."""
    stored = hash_secret(SECRET)

    assert SECRET not in stored
    assert stored.startswith("scrypt$")
    assert verify_secret(SECRET, stored)
    assert not verify_secret("close but no", stored)


def test_two_hashes_of_one_secret_differ() -> None:
    """Per-account salt, so two deployments sharing a passphrase do not share a hash."""
    assert hash_secret(SECRET) != hash_secret(SECRET)


def test_a_malformed_stored_hash_verifies_nothing() -> None:
    """Corrupt configuration fails closed rather than crashing the sign-in path."""
    for rubbish in ("", "scrypt$", "bcrypt$aa$bb", "not-a-hash"):
        assert not verify_secret(SECRET, rubbish)
