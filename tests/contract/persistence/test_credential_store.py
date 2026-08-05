"""Contract: credentials, and everything that must not return one.

FR-018's encryption at rest is a property of a backend with a disk, and is
tested against the Postgres implementation. What is testable against *any*
implementation — and is what constrains every caller in the platform — is the
access shape: exactly one method returns secret material, nothing else can be
coaxed into it, and no rendering of any value here contains a secret (FR-019).
"""

from __future__ import annotations

import pytest
from conftest import at

from platform.persistence.errors import RecordNotFound
from platform.persistence.ports import (
    REDACTED,
    CredentialMetadata,
    CredentialStore,
    PersistenceGateway,
    SecretValue,
    TenantScope,
)

pytestmark = pytest.mark.contract

TOKEN = "xoxb-not-a-real-slack-token-000"
HANDLE = "slack-bot-token"

METADATA = CredentialMetadata(
    handle=HANDLE,
    integration="slack",
    description="Bot token for the incident channel.",
)


def test_only_one_method_returns_secret_material() -> None:
    """The grep that is the audit: ``reveal`` is the trust boundary."""
    surface = {name for name in dir(CredentialStore) if not name.startswith("_")}

    assert surface == {
        "store",
        "get_metadata",
        "list_metadata",
        "reveal",
        "rotate",
        "delete",
        "verify_decryptable",
    }


def test_a_secret_will_not_print_itself() -> None:
    # An exception string reaches places logs do not: a traceback in a console,
    # an error field in an API response.
    secret = SecretValue(TOKEN)

    assert TOKEN not in repr(secret)
    assert TOKEN not in str(secret)
    assert TOKEN not in f"{secret}"
    assert str(secret) == REDACTED
    assert secret.reveal() == TOKEN


def test_secrets_compare_without_leaking_their_length() -> None:
    assert SecretValue(TOKEN) == SecretValue(TOKEN)
    assert SecretValue(TOKEN) != SecretValue("something-else")
    assert SecretValue(TOKEN) != TOKEN


async def test_a_credential_round_trips_through_reveal(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        stored = await uow.credentials.store(METADATA, SecretValue(TOKEN))
        revealed = await uow.credentials.reveal(HANDLE)

    assert stored.created_at is not None
    assert revealed.reveal() == TOKEN


async def test_metadata_reads_carry_nothing_that_could_be_a_secret(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.credentials.store(METADATA, SecretValue(TOKEN))
        found = await uow.credentials.get_metadata(HANDLE)
        listed = await uow.credentials.list_metadata(integration="slack")

    assert found is not None
    assert TOKEN not in repr(found)
    assert [item.handle for item in listed] == [HANDLE]
    assert TOKEN not in repr(listed)


async def test_rotation_is_a_different_operation_from_a_first_write(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # The audit trail has to tell onboarding an integration from responding to a
    # leak.
    async with gateway.begin(scope) as uow:
        await uow.credentials.store(METADATA, SecretValue(TOKEN))
        rotated = await uow.credentials.rotate(
            HANDLE, SecretValue("xoxb-the-new-one"), key_version=2, rotated_at=at(10)
        )
        revealed = await uow.credentials.reveal(HANDLE)

    assert rotated.rotated_at == at(10)
    assert rotated.key_version == 2
    assert revealed.reveal() == "xoxb-the-new-one"


async def test_an_unknown_handle_is_refused_by_both_paths(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        assert await uow.credentials.get_metadata("no-such-handle") is None

        with pytest.raises(RecordNotFound):
            await uow.credentials.reveal("no-such-handle")

        with pytest.raises(RecordNotFound):
            await uow.credentials.rotate(
                "no-such-handle", SecretValue("x"), key_version=2, rotated_at=at()
            )


async def test_deleting_reports_whether_it_was_there(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    async with gateway.begin(scope) as uow:
        await uow.credentials.store(METADATA, SecretValue(TOKEN))

        assert await uow.credentials.delete(HANDLE) is True
        assert await uow.credentials.delete(HANDLE) is False


async def test_the_health_check_can_ask_whether_the_key_still_works(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    # Empty means every stored credential is readable. A key that did not
    # survive a restore surfaces at start rather than during the first incident
    # that needs the one integration nobody tested.
    async with gateway.begin(scope) as uow:
        await uow.credentials.store(METADATA, SecretValue(TOKEN))

        assert await uow.credentials.verify_decryptable() == ()
