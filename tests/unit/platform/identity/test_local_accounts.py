"""The ordinary way in: a name and a passphrase, verified in this process.

A deployment with no identity provider still has to let somebody in, and the
first person to arrive has nowhere to have got an API token from. So a local
account exists. It is not break-glass — that one is the emergency path, short
and loudly audited — and the two are kept apart here on purpose: nothing in this
file constructs a ``BreakGlass``, and a change that made one delegate to the
other would stop compiling rather than quietly give an ordinary sign-in
break-glass's fifteen minutes and its alarm.

What the suite pins down is the part that is easy to get wrong later: the
shipped passphrase works in the demo profile and refuses everywhere else, and
the refusals do not tell an attacker which half of the credential was wrong.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from config.constants.security import (
    LOCAL_ACCOUNT_DEFAULT_PASSWORD,
    LOCAL_ACCOUNT_DEMO_ENV,
    LOCAL_ACCOUNT_PASSWORD_HASH_ENV,
    LOCAL_ACCOUNT_PRINCIPAL_ID,
    LOCAL_ACCOUNT_USERNAME,
    LOCAL_ACCOUNT_USERNAME_ENV,
)
from platform.identity.audit.recorder import AuditRecorder
from platform.identity.break_glass import hash_secret
from platform.identity.errors import LocalSignInRejected
from platform.identity.local_accounts import (
    LocalAccount,
    LocalSignIn,
    UnsafeDefaultPassword,
)
from platform.identity.permissions import Permission
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope

ORG = "acme"
AT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
PASSWORD = "correct horse battery staple"


#: "Not given", as distinct from "given as no account at all" — which is a case
#: this suite tests and would otherwise silently get the default instead.
UNSET = object()


async def build(
    *, account: LocalAccount | None | object = UNSET
) -> tuple[LocalSignIn, FakePersistence, TenantScope]:
    """Return a sign-in path over a tenant that has nothing in it yet."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")

    chosen = (
        LocalAccount(password_hash=hash_secret(PASSWORD))
        if account is UNSET
        else cast(LocalAccount | None, account)
    )
    return (
        LocalSignIn(
            gateway=gateway,
            tokens=TokenService(gateway=gateway, clock=lambda: AT),
            account=chosen,
            recorder=AuditRecorder(gateway=gateway, clock=lambda: AT),
            clock=lambda: AT,
        ),
        gateway,
        TenantScope(org_id=ORG),
    )


# --- Signing in ------------------------------------------------------------------


async def test_a_name_and_a_passphrase_produce_a_token_the_gateway_accepts() -> None:
    """The credential a sign-in returns has to be one an ordinary request can use.

    This is the whole point of issuing a token rather than inventing a session
    format: what comes back goes into an ``Authorization: Bearer`` header on
    every read after it, and the only credential that header accepts is one
    ``TokenService.authenticate`` resolves.
    """
    sign_in, _, _ = await build()

    issued = await sign_in.sign_in(LOCAL_ACCOUNT_USERNAME, PASSWORD, org_id=ORG)
    resolved = await sign_in.tokens.authenticate(issued.secret)

    assert resolved.principal.principal_id == LOCAL_ACCOUNT_PRINCIPAL_ID


async def test_the_local_account_holds_owner_so_a_first_run_can_reach_everything() -> None:
    """A first run that could sign in and then do nothing is not a first run."""
    sign_in, _, _ = await build()

    issued = await sign_in.sign_in(LOCAL_ACCOUNT_USERNAME, PASSWORD, org_id=ORG)
    resolved = await sign_in.tokens.authenticate(issued.secret)

    assert Permission.CONFIG_WRITE in resolved.permissions.permissions_at(None)


async def test_signing_in_twice_reuses_the_account_rather_than_making_a_second_one() -> None:
    """The principal is upserted, so a restart does not accumulate admins."""
    sign_in, gateway, scope = await build()

    await sign_in.sign_in(LOCAL_ACCOUNT_USERNAME, PASSWORD, org_id=ORG)
    await sign_in.sign_in(LOCAL_ACCOUNT_USERNAME, PASSWORD, org_id=ORG)

    async with gateway.begin(scope) as uow:
        users = await uow.identity.list_users()
    assert [user.user_id for user in users] == [LOCAL_ACCOUNT_PRINCIPAL_ID]


# --- Refusing --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (LOCAL_ACCOUNT_USERNAME, "not the passphrase"),
        ("somebody-else", PASSWORD),
        ("somebody-else", "not the passphrase"),
    ],
)
async def test_every_refusal_says_the_same_thing(username: str, password: str) -> None:
    """A wrong name and a wrong passphrase are one refusal, in one wording.

    A message that distinguished them would answer "does this account exist" for
    anybody willing to ask, which is the question the sign-in page must not be a
    way of asking.
    """
    sign_in, _, _ = await build()

    with pytest.raises(LocalSignInRejected) as refused:
        await sign_in.sign_in(username, password, org_id=ORG)

    assert str(refused.value) == "the credential was not accepted"


async def test_a_deployment_with_no_local_account_refuses_rather_than_letting_anybody_in() -> None:
    """No account configured is not an account that accepts anything."""
    sign_in, _, _ = await build(account=None)

    with pytest.raises(LocalSignInRejected):
        await sign_in.sign_in(LOCAL_ACCOUNT_USERNAME, PASSWORD, org_id=ORG)


# --- The shipped passphrase ------------------------------------------------------


def test_the_demo_profile_ships_a_working_default() -> None:
    """The first run is a sign-in, not a scavenger hunt for a token."""
    account = LocalAccount.from_environment({LOCAL_ACCOUNT_DEMO_ENV: "1"})

    assert account is not None
    assert account.verify(LOCAL_ACCOUNT_USERNAME, LOCAL_ACCOUNT_DEFAULT_PASSWORD)


def test_the_shipped_passphrase_is_refused_when_the_profile_is_not_the_demo() -> None:
    """Reaching production with the documented passphrase has to be impossible.

    Not "discouraged". The default is only acceptable to a deployment that also
    set the demo flag, so an operator cannot arrive here by forgetting to change
    something — they would have had to set a second thing as well.
    """
    with pytest.raises(UnsafeDefaultPassword):
        LocalAccount.from_environment(
            {LOCAL_ACCOUNT_PASSWORD_HASH_ENV: hash_secret(LOCAL_ACCOUNT_DEFAULT_PASSWORD)}
        )


def test_a_deployment_that_configured_its_own_passphrase_needs_no_flag() -> None:
    """The demo flag is about the shipped default, not about local accounts."""
    account = LocalAccount.from_environment(
        {
            LOCAL_ACCOUNT_USERNAME_ENV: "operator",
            LOCAL_ACCOUNT_PASSWORD_HASH_ENV: hash_secret(PASSWORD),
        }
    )

    assert account is not None
    assert account.verify("operator", PASSWORD)
    assert not account.verify("operator", LOCAL_ACCOUNT_DEFAULT_PASSWORD)


def test_a_deployment_that_configured_nothing_has_no_local_account() -> None:
    """Absent rather than default-on: an account nobody asked for is a way in."""
    assert LocalAccount.from_environment({}) is None
