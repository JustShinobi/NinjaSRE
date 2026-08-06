"""Contract: users, token hashes, and role bindings."""

from __future__ import annotations

import pytest
from conftest import PRIMARY_ORG, at

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
