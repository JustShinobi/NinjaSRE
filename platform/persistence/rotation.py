"""Rewriting stored credentials under the process's current encryption key.

This lives in the persistence package for one reason, and it is the reason the
boundary exists: re-encrypting a credential means reading its plaintext, and
``CredentialStore.reveal`` is the single method in NinjaSRE that returns one.
``make check-credentials`` allows that call here and in the proxy's resolver,
and nowhere else — so the code that does the reading is the code that owns the
storage, and the rotation *policy* lives one package away in
``platform.startup.rotation`` where it can be reasoned about without a database.

The plaintext never leaves this module. It is read into a ``SecretValue`` and
handed straight back to ``rotate``; nothing is returned, logged, or held.

Backend-neutral on purpose. Everything here goes through the repository ports,
so the same rotation runs against PostgreSQL and against the fakes — which is
what lets the no-downtime property be a unit test rather than a claim.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from platform.persistence.errors import CredentialError, RecordNotFound
from platform.persistence.ports import PersistenceGateway, TenantScope


class VaultReEncryptor:
    """Rewrites one tenant's stored credentials under the current key.

    One transaction per call to ``reencrypt``, which is what makes the batch
    size in ``platform.startup.rotation`` mean something: a batch is a
    transaction, and a transaction is how long a reader could be made to wait.
    """

    __slots__ = ("_gateway", "_scope")

    def __init__(self, *, gateway: PersistenceGateway, scope: TenantScope) -> None:
        self._gateway = gateway
        self._scope = scope

    async def handles(self) -> tuple[str, ...]:
        """Return every stored credential handle in this tenant, in handle order."""
        async with self._gateway.begin(self._scope) as uow:
            stored = await uow.credentials.list_metadata()
        return tuple(metadata.handle for metadata in stored)

    async def reencrypt(self, handles: Sequence[str]) -> tuple[str, ...]:
        """Rewrite each of ``handles`` under the current key, in one transaction.

        Returns the handles that were rewritten. A credential whose ciphertext
        opens with no key this process holds is omitted rather than raised on:
        it was already unreadable before the rotation started, and failing the
        batch would strand every other credential between two keys.
        """
        rewritten: list[str] = []
        now = datetime.now(UTC)

        async with self._gateway.begin(self._scope) as uow:
            for handle in handles:
                metadata = await uow.credentials.get_metadata(handle)
                if metadata is None:
                    continue
                try:
                    secret = await uow.credentials.reveal(handle)
                except (CredentialError, RecordNotFound):
                    continue
                # Writing the same plaintext back is what re-encrypts it: the
                # column type seals on the way in, under whichever key the
                # process currently holds.
                await uow.credentials.rotate(
                    handle,
                    secret,
                    key_version=metadata.key_version + 1,
                    rotated_at=now,
                )
                rewritten.append(handle)

        return tuple(rewritten)


__all__ = ["VaultReEncryptor"]
