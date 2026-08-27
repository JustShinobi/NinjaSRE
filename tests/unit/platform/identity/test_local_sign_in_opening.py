"""The door redefined: a deployment's local sign-in is open when it is *either*
the environment-configured account *or* a deliberately registered opening —
never when a principal happened to get created.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from platform.identity import local_accounts as local_accounts_module
from platform.identity.audit.recorder import AuditRecorder
from platform.identity.break_glass import verify_secret as _real_verify_secret
from platform.identity.errors import LocalSignInRejected
from platform.identity.local_accounts import LocalSignIn, hash_local_password
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.persistence.ports.identity_repository import PrincipalKind, RoleBinding, User

ORG = "acme"
AT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
GRACE_PASSWORD = "a passphrase that belongs to nobody but grace"
ADMIN_PASSWORD = "the administrator's own long passphrase"


async def _store() -> tuple[FakePersistence, TenantScope]:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return gateway, TenantScope(org_id=ORG)


def _sign_in(gateway: FakePersistence) -> LocalSignIn:
    """Return a sign-in path with no environment-configured account at all."""
    return LocalSignIn(
        gateway=gateway,
        tokens=TokenService(gateway=gateway, clock=lambda: AT),
        account=None,
        recorder=AuditRecorder(gateway=gateway, clock=lambda: AT),
        clock=lambda: AT,
    )


async def _open_the_door(gateway: FakePersistence, scope: TenantScope, *, opened_via: str) -> None:
    async with gateway.begin(scope) as uow:
        await uow.identity.open_local_sign_in(opened_at=AT, opened_via=opened_via)


async def _create_local_administrator(
    gateway: FakePersistence, scope: TenantScope, *, user_id: str, name: str, password: str
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id=user_id, email=name, display_name=name, kind=PrincipalKind.USER)
        )
        await uow.identity.set_local_password(user_id, password_hash=hash_local_password(password))
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id=f"{user_id}-owner", user_id=user_id, role="owner")
        )


async def test_a_registered_opening_admits_the_administrator_it_named() -> None:
    gateway, scope = await _store()
    await _open_the_door(gateway, scope, opened_via="cli")
    await _create_local_administrator(
        gateway, scope, user_id="admin-1", name="admin", password=ADMIN_PASSWORD
    )

    sign_in = _sign_in(gateway)
    issued = await sign_in.sign_in("admin", ADMIN_PASSWORD, org_id=ORG)

    resolved = await sign_in.tokens.authenticate(issued.secret)
    assert resolved.principal.principal_id == "admin-1"


async def test_without_an_opening_a_created_principal_is_still_refused() -> None:
    """The second half of the invariant: creating a principal never opens the
    door by itself, whether or not an opening mechanism now exists."""
    gateway, scope = await _store()
    await _create_local_administrator(
        gateway, scope, user_id="admin-1", name="admin", password=ADMIN_PASSWORD
    )

    with pytest.raises(LocalSignInRejected):
        await _sign_in(gateway).sign_in("admin", ADMIN_PASSWORD, org_id=ORG)


async def test_an_opening_with_no_matching_principal_still_refuses() -> None:
    gateway, scope = await _store()
    await _open_the_door(gateway, scope, opened_via="cli")

    with pytest.raises(LocalSignInRejected):
        await _sign_in(gateway).sign_in("nobody", "whatever this is", org_id=ORG)


async def test_the_opening_is_read_by_attempt_not_fixed_at_construction() -> None:
    """A ``LocalSignIn`` built before the door opened still admits somebody
    who registers after it was constructed — no restart needed."""
    gateway, scope = await _store()
    sign_in = _sign_in(gateway)

    with pytest.raises(LocalSignInRejected):
        await sign_in.sign_in("admin", ADMIN_PASSWORD, org_id=ORG)

    await _open_the_door(gateway, scope, opened_via="cli")
    await _create_local_administrator(
        gateway, scope, user_id="admin-1", name="admin", password=ADMIN_PASSWORD
    )

    issued = await sign_in.sign_in("admin", ADMIN_PASSWORD, org_id=ORG)
    assert issued.token.user_id == "admin-1"


async def test_the_refusal_when_nothing_is_open_names_no_credential() -> None:
    gateway, scope = await _store()

    with pytest.raises(LocalSignInRejected) as raised:
        await _sign_in(gateway).sign_in("whoever", "whatever", org_id=ORG)

    # The one message every refusal already shares — this path must not grow
    # a second, more specific one.
    assert str(raised.value) == "the credential was not accepted"


async def test_a_registered_administrator_pays_the_same_passphrase_check_regardless_of_the_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR: the opening read must not add a passphrase comparison. A name that
    exists (wrong password) and a name that does not must cost the same."""
    gateway, scope = await _store()
    await _open_the_door(gateway, scope, opened_via="cli")
    await _create_local_administrator(
        gateway, scope, user_id="admin-1", name="admin", password=ADMIN_PASSWORD
    )
    calls: dict[str, int] = {"unknown": 0, "known": 0}

    def counting(label: str) -> Callable[[str, str], bool]:
        def spy(secret: str, stored: str) -> bool:
            calls[label] += 1
            return _real_verify_secret(secret, stored)

        return spy

    monkeypatch.setattr(local_accounts_module, "verify_secret", counting("unknown"))
    with pytest.raises(LocalSignInRejected):
        await _sign_in(gateway).sign_in("nobody-at-all", "whatever", org_id=ORG)

    monkeypatch.setattr(local_accounts_module, "verify_secret", counting("known"))
    with pytest.raises(LocalSignInRejected):
        await _sign_in(gateway).sign_in("admin", "the wrong passphrase", org_id=ORG)

    assert calls["unknown"] == 1
    assert calls["known"] == 1
