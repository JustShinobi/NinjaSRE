"""Contract: users, token hashes, and role bindings."""

from __future__ import annotations

import asyncio

import pytest
from conftest import POSTGRES, PRIMARY_ORG, at

from platform.persistence.errors import DuplicateRecord
from platform.persistence.ports import (
    ApiToken,
    PersistenceGateway,
    RoleBinding,
    TenantScope,
    User,
)

pytestmark = pytest.mark.contract

ADA = User(user_id="u-ada", email="Ada@example.com", display_name="Ada")


async def test_a_user_round_trips(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        found = await uow.identity.get_user("u-ada")

    assert found is not None
    assert found.display_name == "Ada"


async def test_a_local_password_is_stored_by_hash_and_survives_an_unrelated_upsert(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The hash lives apart from the general-purpose upsert on purpose: a later
    # write that only means to change a display name must not silently clear
    # a password nobody asked it to touch.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        assert await uow.identity.set_local_password("u-ada", password_hash="scrypt:abc") is True
        await uow.identity.upsert_user(
            User(user_id="u-ada", email="ada@example.com", display_name="Ada A.")
        )
        found = await uow.identity.get_user("u-ada")

    assert found is not None
    assert found.display_name == "Ada A."
    assert found.local_password_hash == "scrypt:abc"


async def test_setting_a_password_for_nobody_reports_it(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        assert (
            await uow.identity.set_local_password("u-nobody", password_hash="scrypt:abc") is False
        )


async def test_email_lookup_ignores_case(gateway: PersistenceGateway, scope: TenantScope) -> None:
    # An operator typing their address into a login form does not reproduce the
    # capitalisation their identity provider stored, and a store that cared
    # would create a second account for the same person.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        found = await uow.identity.find_user_by_email("ADA@EXAMPLE.COM")

    assert found is not None
    assert found.user_id == "u-ada"


async def test_a_user_is_found_by_their_sso_subject(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(
                user_id="u-grace",
                email="grace@example.com",
                display_name="Grace",
                external_subject="okta|1234",
            )
        )
        found = await uow.identity.find_user_by_subject("okta|1234")

    assert found is not None
    assert found.user_id == "u-grace"


async def test_two_tokens_cannot_share_a_hash(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # A collision is either a generation bug or two principals sharing a
    # credential. Overwriting would make the second one invisible.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        await uow.identity.store_token(
            ApiToken(token_id="t-1", user_id="u-ada", name="laptop", token_hash="sha256:aaa")
        )

        with pytest.raises(DuplicateRecord):
            await uow.identity.store_token(
                ApiToken(token_id="t-2", user_id="u-ada", name="ci", token_hash="sha256:aaa")
            )


async def test_revoking_is_reported_once(gateway: PersistenceGateway, scope: TenantScope) -> None:
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        await uow.identity.store_token(
            ApiToken(token_id="t-1", user_id="u-ada", name="laptop", token_hash="sha256:aaa")
        )

        assert await uow.identity.revoke_token("t-1", revoked_at=at()) is True
        assert await uow.identity.revoke_token("t-1", revoked_at=at(1)) is False


async def test_role_bindings_are_added_listed_and_removed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id="b-1", user_id="u-ada", role="responder")
        )
        await uow.identity.upsert_role_binding(
            RoleBinding(binding_id="b-2", user_id="u-ada", role="approver", node_id="payments")
        )

        held = await uow.identity.role_bindings_for_user("u-ada")
        assert [binding.role for binding in held] == ["approver", "responder"]

        assert await uow.identity.remove_role_binding("b-1") is True
        assert await uow.identity.remove_role_binding("b-1") is False


async def test_a_live_token_resolves_to_its_tenant(gateway: PersistenceGateway) -> None:
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        await uow.identity.upsert_user(ADA)
        await uow.identity.store_token(
            ApiToken(
                token_id="t-1",
                user_id="u-ada",
                name="laptop",
                token_hash="sha256:aaa",
                scopes=("investigations:read",),
            )
        )

    async with gateway.begin_system() as system:
        resolved = await system.tokens.resolve_token("sha256:aaa", now=at())

    assert resolved is not None
    # This is what makes "every other port takes no organisation argument"
    # workable: resolution is how the caller learns which scope to open.
    assert resolved.org_id == PRIMARY_ORG
    assert resolved.scopes == ("investigations:read",)


@pytest.mark.parametrize(
    ("label", "revoke", "expires_minutes"),
    [
        ("revoked", True, None),
        ("expired", False, -1.0),
    ],
)
async def test_a_token_that_should_not_work_resolves_to_nothing(
    gateway: PersistenceGateway,
    scope: TenantScope,
    label: str,
    revoke: bool,
    expires_minutes: float | None,
) -> None:
    # Unknown, revoked, and expired are all ``None``. Distinguishing them would
    # tell an attacker which of their guesses was a real token.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        await uow.identity.store_token(
            ApiToken(
                token_id="t-1",
                user_id="u-ada",
                name=label,
                token_hash="sha256:aaa",
                expires_at=at(expires_minutes) if expires_minutes is not None else None,
            )
        )
        if revoke:
            await uow.identity.revoke_token("t-1", revoked_at=at(-1))

    async with gateway.begin_system() as system:
        assert await system.tokens.resolve_token("sha256:aaa", now=at()) is None
        assert await system.tokens.resolve_token("sha256:unknown", now=at()) is None


async def test_a_token_carries_its_team_description_and_last_use(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Everything that bounds what a token may do is on the record, and survives
    # the round trip. A backend that dropped the team would produce a token that
    # silently reached the whole organisation.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        stored = await uow.identity.store_token(
            ApiToken(
                token_id="t-1",
                user_id="u-ada",
                name="payments bot",
                token_hash="sha256:aaa",
                scopes=("config.read",),
                team_node_id="payments",
                description="posts investigations into the payments channel",
                expires_at=at(60),
            )
        )

    assert stored.team_node_id == "payments"
    assert stored.description == "posts investigations into the payments channel"
    assert stored.last_used_at is None

    async with gateway.begin(scope) as uow:
        assert await uow.identity.record_token_use("t-1", used_at=at(5)) is True
        assert await uow.identity.record_token_use("t-unknown", used_at=at(5)) is False
        [reread] = await uow.identity.tokens_for_user("u-ada")

    assert reread.last_used_at == at(5)


async def test_a_scoped_token_resolves_to_its_team(gateway: PersistenceGateway) -> None:
    # The resolution is what a request's permissions are then narrowed against,
    # so a backend that lost the team here would widen every scoped token.
    async with gateway.begin(TenantScope(org_id=PRIMARY_ORG)) as uow:
        await uow.identity.upsert_user(ADA)
        await uow.identity.store_token(
            ApiToken(
                token_id="t-1",
                user_id="u-ada",
                name="payments bot",
                token_hash="sha256:aaa",
                team_node_id="payments",
            )
        )

    async with gateway.begin_system() as system:
        resolved = await system.tokens.resolve_token("sha256:aaa", now=at())

    assert resolved is not None
    assert resolved.team_node_id == "payments"


async def test_listing_covers_every_token_in_the_tenant(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # What the inactivity policy and the expiry sweep read. Per-user listing
    # would miss the tokens of a user somebody had already deactivated.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        await uow.identity.upsert_user(User(user_id="u-grace", email="g@e.com", display_name="G"))
        for index, owner in enumerate(("u-ada", "u-grace", "u-ada")):
            await uow.identity.store_token(
                ApiToken(
                    token_id=f"t-{index}",
                    user_id=owner,
                    name=f"token {index}",
                    token_hash=f"sha256:{index}",
                    created_at=at(index),
                )
            )
        listed = await uow.identity.list_tokens()

    assert [token.token_id for token in listed] == ["t-2", "t-1", "t-0"]


async def test_bulk_revocation_reports_only_what_it_changed(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # An id that was already revoked, or that belongs to nothing, is absent from
    # the answer rather than counted — an incident response that reported having
    # revoked something it had not is worse than one that reported less.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        for index in range(3):
            await uow.identity.store_token(
                ApiToken(
                    token_id=f"t-{index}",
                    user_id="u-ada",
                    name=f"token {index}",
                    token_hash=f"sha256:{index}",
                )
            )
        await uow.identity.revoke_token("t-0", revoked_at=at(-1))

        revoked = await uow.identity.revoke_tokens(
            ("t-0", "t-1", "t-2", "t-absent"), revoked_at=at()
        )
        assert set(revoked) == {"t-1", "t-2"}

        assert await uow.identity.revoke_tokens((), revoked_at=at()) == ()
        assert await uow.identity.revoke_tokens(("t-1",), revoked_at=at()) == ()


async def test_a_token_hash_is_locatable_for_the_audit_trail(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # ``resolve_token`` refuses to say why a token failed, which is right on the
    # authentication path and is also why a rejected attempt would otherwise
    # have no tenant to be recorded against.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        await uow.identity.store_token(
            ApiToken(
                token_id="t-1",
                user_id="u-ada",
                name="expired",
                token_hash="sha256:aaa",
                expires_at=at(-1),
            )
        )

    async with gateway.begin_system() as system:
        assert await system.tokens.resolve_token("sha256:aaa", now=at()) is None

        located = await system.tokens.find_token_by_hash("sha256:aaa")
        assert located is not None
        assert located.org_id == PRIMARY_ORG
        assert located.token.token_id == "t-1"

        assert await system.tokens.find_token_by_hash("sha256:unknown") is None


async def test_a_deployment_can_hold_more_than_one_addressless_principal(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The bootstrap service account already has no address. A second one —
    # any other service account nobody gave an address — used to collide with
    # it on the email uniqueness rule; this is that defect, closed.
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id="svc-1", email="", display_name="First service account")
        )
        await uow.identity.upsert_user(
            User(user_id="svc-2", email="", display_name="Second service account")
        )
        first = await uow.identity.get_user("svc-1")
        second = await uow.identity.get_user("svc-2")

    assert first is not None
    assert second is not None
    assert first.email == ""
    assert second.email == ""


async def test_an_empty_address_search_finds_nobody(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id="svc-1", email="", display_name="First service account")
        )
        await uow.identity.upsert_user(
            User(user_id="svc-2", email="", display_name="Second service account")
        )
        found = await uow.identity.find_user_by_email("")

    assert found is None


async def test_a_real_address_collision_names_the_address_not_a_constraint(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.identity.upsert_user(ADA)
        with pytest.raises(DuplicateRecord) as raised:
            await uow.identity.upsert_user(
                User(user_id="u-ada-2", email="ADA@EXAMPLE.COM", display_name="Impostor")
            )

    message = str(raised.value)
    assert "ada@example.com" in message.lower() or "ADA@EXAMPLE.COM" in message
    assert "ix_users_email" not in message
    assert "constraint" not in message.lower()
    assert "sqlstate" not in message.lower()
    assert "asyncpg" not in message.lower()


LOCAL_SIGN_IN_RACE_ATTEMPTS = 8


@pytest.fixture
def postgres_only(backend_name: str) -> None:
    """Skip a test that has no meaning without a real database.

    A single Python process holding the fake's own lock is its own exclusion —
    there is no window between its check and its write for a second caller to
    land in — so racing the fake would prove nothing about the advisory lock
    this test exists to hold accountable.
    """
    if backend_name != POSTGRES:
        pytest.skip("The race this test proves only exists against a real database.")


@pytest.mark.usefixtures("postgres_only")
async def test_concurrent_first_administrators_leave_exactly_one_opening(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Several callers racing to open the local sign-in door produce one winner.

    Every replica of a rolling deployment, or every terminal an operator has
    open at once, can reach for this door at the same instant. Whichever
    caller wins varies with scheduling; the count of doors opened must not,
    and every loser reads back a sentence naming what happened rather than a
    constraint name, an index name, or the driver's own words.
    """
    # Warm the gateway's one-time graph readiness check before timing the
    # race: it runs on first use of a fresh gateway, is not itself guarded by
    # any lock, and racing it here would measure that unrelated startup path
    # instead of the advisory lock this test exists to hold accountable.
    async with gateway.begin(scope):
        pass

    markers = [f"race-attempt-{index}" for index in range(LOCAL_SIGN_IN_RACE_ATTEMPTS)]

    async def attempt(marker: str) -> tuple[str, str]:
        try:
            async with gateway.begin(scope) as uow:
                opened = await uow.identity.open_local_sign_in(opened_at=at(), opened_via=marker)
        except Exception as error:  # noqa: BLE001 - classified and asserted on below
            return (type(error).__name__, str(error))
        return ("opened", opened.opened_via)

    results = await asyncio.gather(*(attempt(marker) for marker in markers))

    winners = [result for result in results if result[0] == "opened"]
    losers = [result for result in results if result[0] != "opened"]

    assert len(winners) == 1, f"expected exactly one opening, found {len(winners)}: {results}"
    assert len(losers) == LOCAL_SIGN_IN_RACE_ATTEMPTS - 1

    for kind, message in losers:
        assert kind == "DuplicateRecord", (
            f"a refusal must be the domain error, not {kind}: {message}"
        )
        lowered = message.lower()
        assert "asyncpg" not in lowered
        assert "sqlstate" not in lowered
        assert "constraint" not in lowered
        assert "duplicate key value" not in lowered
        assert "ix_" not in lowered
        assert "pk_" not in lowered

    [(_, winning_marker)] = winners
    async with gateway.begin(scope) as uow:
        stored = await uow.identity.local_sign_in_opening()

    assert stored is not None
    # The row a fresh read finds is the one the winner wrote, not a phantom
    # the race window left behind.
    assert stored.opened_via == winning_marker
