"""The rule that opens a deployment's local sign-in, and creates or rotates an administrator."""

from __future__ import annotations

import pytest

from platform.config_service.service import ConfigService
from platform.identity.audit.recorder import AuditContext, AuditRecorder
from platform.identity.enrolment import (
    EnrolledAdministrator,
    enrol_local_administrator,
    identity_provider_is_active,
    local_sign_in_is_open,
)
from platform.identity.errors import LocalAdministratorNameTaken, LocalEnrolmentBlockedBySso
from platform.identity.local_accounts import verify_secret
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.transaction import TenantScope

ORG_ID = "acme"
SCOPE = TenantScope(org_id=ORG_ID)


async def _seeded_store() -> FakePersistence:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")
    return store


def _tokens(store: FakePersistence) -> TokenService:
    return TokenService(gateway=store, recorder=AuditRecorder(gateway=store))


async def test_creating_the_first_administrator_opens_the_door() -> None:
    store = await _seeded_store()
    assert await local_sign_in_is_open(store, org_id=ORG_ID) is False

    result = await enrol_local_administrator(
        store,
        _tokens(store),
        org_id=ORG_ID,
        name="admin",
        password="a very long passphrase",
        opened_via="cli",
    )

    assert isinstance(result, EnrolledAdministrator)
    assert result.opened is True
    assert result.rotated is False
    assert await local_sign_in_is_open(store, org_id=ORG_ID) is True


async def test_the_created_administrator_holds_the_owner_role_and_a_stored_passphrase() -> None:
    store = await _seeded_store()
    result = await enrol_local_administrator(
        store,
        _tokens(store),
        org_id=ORG_ID,
        name="admin",
        password="a very long passphrase",
        opened_via="cli",
    )

    async with store.begin(SCOPE) as uow:
        user = await uow.identity.get_user(result.user_id)
        bindings = await uow.identity.role_bindings_for_user(result.user_id)

    assert user is not None
    assert user.local_password_hash is not None
    assert verify_secret("a very long passphrase", user.local_password_hash)
    assert [b.role for b in bindings] == [Role.OWNER.value]


async def test_the_audit_trail_never_carries_the_passphrase() -> None:
    store = await _seeded_store()
    await enrol_local_administrator(
        store,
        _tokens(store),
        org_id=ORG_ID,
        name="admin",
        password="a very long passphrase",
        opened_via="cli",
        recorder=AuditRecorder(gateway=store),
    )

    async with store.begin(SCOPE) as uow:
        events = await uow.audit.query()

    detail_text = " ".join(str(event.detail) for event in events)
    assert "a very long passphrase" not in detail_text


async def test_a_second_administrator_does_not_reopen_the_door() -> None:
    store = await _seeded_store()
    tokens = _tokens(store)
    first = await enrol_local_administrator(
        store,
        tokens,
        org_id=ORG_ID,
        name="admin",
        password="a very long passphrase",
        opened_via="cli",
    )
    second = await enrol_local_administrator(
        store,
        tokens,
        org_id=ORG_ID,
        name="ops",
        password="another long passphrase",
        opened_via="cli",
    )

    assert first.opened is True
    assert second.opened is False
    assert second.user_id != first.user_id


async def test_an_existing_name_without_rotation_is_refused() -> None:
    store = await _seeded_store()
    tokens = _tokens(store)
    await enrol_local_administrator(
        store,
        tokens,
        org_id=ORG_ID,
        name="admin",
        password="a very long passphrase",
        opened_via="cli",
    )

    with pytest.raises(LocalAdministratorNameTaken) as raised:
        await enrol_local_administrator(
            store,
            tokens,
            org_id=ORG_ID,
            name="admin",
            password="a different passphrase",
            opened_via="cli",
        )

    assert "admin" in str(raised.value)
    assert "rotat" in str(raised.value).lower()


async def test_rotation_replaces_the_passphrase_and_revokes_live_sessions() -> None:
    store = await _seeded_store()
    tokens = _tokens(store)
    created = await enrol_local_administrator(
        store,
        tokens,
        org_id=ORG_ID,
        name="admin",
        password="the old passphrase",
        opened_via="cli",
    )
    issued = await tokens.issue(
        SCOPE,
        AuditContext(actor_kind=ActorKind.USER, actor_id=created.user_id),
        user_id=created.user_id,
        name="a live session",
    )

    result = await enrol_local_administrator(
        store,
        tokens,
        org_id=ORG_ID,
        name="admin",
        password="the new passphrase",
        rotate=True,
        opened_via="cli",
    )

    assert result.rotated is True
    assert result.opened is False

    async with store.begin(SCOPE) as uow:
        user = await uow.identity.get_user(created.user_id)
        tokens_after = await uow.identity.tokens_for_user(created.user_id)

    assert user is not None
    assert verify_secret("the new passphrase", user.local_password_hash)
    assert not verify_secret("the old passphrase", user.local_password_hash)
    [live_token] = [t for t in tokens_after if t.token_id == issued.token.token_id]
    assert live_token.is_revoked is True


async def test_a_deployment_with_an_active_identity_provider_blocks_enrolment() -> None:
    store = await _seeded_store()
    service = ConfigService(gateway=store, scope=SCOPE)
    await service.set_settings(
        ORG_ID,
        {"policies": {"sso": {"is_active": True}}},
        actor_id="test",
        actor_kind=ActorKind.SYSTEM,
    )

    with pytest.raises(LocalEnrolmentBlockedBySso) as raised:
        await enrol_local_administrator(
            store,
            _tokens(store),
            org_id=ORG_ID,
            name="admin",
            password="a very long passphrase",
            opened_via="cli",
        )

    assert "break-glass" in str(raised.value).lower() or "break_glass" in str(raised.value).lower()
    assert "--force" not in str(raised.value)
    assert await identity_provider_is_active(store, org_id=ORG_ID) is True
