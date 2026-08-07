"""SC-007's storage half: re-encryption through the ports, with nothing offline.

This is in the persistence contract suite rather than beside the rotation policy
because re-encrypting a credential means reading its plaintext, and
``CredentialStore.reveal`` is the single method in NinjaSRE that returns one.
``make check-credentials`` allows that call in the storage layer, in the proxy,
and in this suite, and nowhere else — so the test that proves the rewrite
preserves the value has to live where the boundary already is.

Being here also means it runs against PostgreSQL under ``make test-postgres``,
which is where "the row is re-encrypted" is a fact about ciphertext rather than
about a dictionary. Against the fakes it still holds the half that constrains
every caller: every handle is readable at every point of the walk, and what
comes back is what went in.
"""

from __future__ import annotations

import pytest

from platform.credentials.handles import CredentialHandle
from platform.persistence.ports import PersistenceGateway, TenantScope
from platform.persistence.ports.credential_store import CredentialMetadata, SecretValue
from platform.persistence.rotation import VaultReEncryptor
from platform.startup.rotation import CredentialReEncryptor, rotate_encryption_key

pytestmark = pytest.mark.contract


def handles(count: int) -> tuple[str, ...]:
    """Return ``count`` credential handles, in the vault's own shape."""
    return tuple(
        CredentialHandle(integration=f"vendor-{index}", team_id="payments").qualified
        for index in range(count)
    )


async def store_credentials(
    gateway: PersistenceGateway,
    scope: TenantScope,
    stored: tuple[str, ...],
) -> None:
    """Put one credential under each handle."""
    async with gateway.begin(scope) as uow:
        for handle in stored:
            await uow.credentials.store(
                CredentialMetadata(handle=handle, integration=handle.split("::")[0]),
                SecretValue(f"secret-for-{handle}"),
            )


async def test_the_re_encryptor_is_the_port(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    assert isinstance(VaultReEncryptor(gateway=gateway, scope=scope), CredentialReEncryptor)


async def test_every_credential_is_rewritten_through_the_ports(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    stored = handles(4)
    await store_credentials(gateway, scope, stored)

    report = await rotate_encryption_key(
        VaultReEncryptor(gateway=gateway, scope=scope), batch_size=2
    )

    assert report.complete
    assert set(report.rewritten) == set(stored)


async def test_every_credential_stays_readable_at_every_point_of_the_rotation(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """SC-007's no-downtime half, checked between batches rather than argued."""
    stored = handles(6)
    await store_credentials(gateway, scope, stored)
    readable_after_each_batch: list[int] = []

    async def readable_now() -> int:
        async with gateway.begin(scope) as uow:
            found = 0
            for handle in stored:
                secret = await uow.credentials.reveal(handle)
                if secret.reveal() == f"secret-for-{handle}":
                    found += 1
            return found

    reencryptor = VaultReEncryptor(gateway=gateway, scope=scope)
    every = await reencryptor.handles()
    for start in range(0, len(every), 2):
        await reencryptor.reencrypt(every[start : start + 2])
        readable_after_each_batch.append(await readable_now())

    assert readable_after_each_batch == [6, 6, 6], (
        "a reader arriving mid-rotation must find every credential readable"
    )


async def test_the_plaintext_survives_the_rewrite_unchanged(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A rotation that changed a value would be a rotation that broke an integration."""
    stored = handles(2)
    await store_credentials(gateway, scope, stored)

    await rotate_encryption_key(VaultReEncryptor(gateway=gateway, scope=scope))

    async with gateway.begin(scope) as uow:
        for handle in stored:
            secret = await uow.credentials.reveal(handle)
            assert secret.reveal() == f"secret-for-{handle}"


async def test_rotation_bumps_the_key_version_it_records(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The stored version is how an operator tells a rewritten row from an untouched one."""
    stored = handles(2)
    await store_credentials(gateway, scope, stored)

    await rotate_encryption_key(VaultReEncryptor(gateway=gateway, scope=scope))

    async with gateway.begin(scope) as uow:
        for handle in stored:
            metadata = await uow.credentials.get_metadata(handle)
            assert metadata is not None
            assert metadata.key_version == 2
            assert metadata.rotated_at is not None


async def test_a_rotation_touches_no_other_tenant(
    gateway: PersistenceGateway, scope: TenantScope, other_scope: TenantScope
) -> None:
    """The scope is the boundary here as everywhere: one tenant's keys, one tenant's rows."""
    await store_credentials(gateway, scope, handles(2))
    await store_credentials(gateway, other_scope, handles(3))

    report = await rotate_encryption_key(VaultReEncryptor(gateway=gateway, scope=scope))

    assert report.total == 2


async def test_a_handle_that_vanished_mid_rotation_is_skipped_rather_than_raised(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """Deleting an integration while a rotation runs must not fail the rotation."""
    reencryptor = VaultReEncryptor(gateway=gateway, scope=scope)

    assert await reencryptor.reencrypt(["vendor-x::payments"]) == ()


async def test_a_deployment_with_nothing_stored_reports_a_complete_rotation(
    gateway: PersistenceGateway, scope: TenantScope
) -> None:
    report = await rotate_encryption_key(VaultReEncryptor(gateway=gateway, scope=scope))

    assert report.total == 0
    assert report.complete
