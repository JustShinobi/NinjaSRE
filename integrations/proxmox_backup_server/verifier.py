"""Proves a Proxmox Backup Server credential works, and what it may read.

One permission, and it is the one an operator most often gets wrong: Backup
Server's ``Datastore.Audit`` is granted per datastore path, so a token granted on
``/datastore/nightly`` reads that store and reports nothing at all about the one
next to it. A verification that only proved connectivity would report success for
a token that cannot see the datastore the deployment actually backs up to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import ProxyTransport, RequestContext
from integrations._verification.framework import Connectivity
from integrations._verification.permissions import (
    PermissionProbe,
    RequiredPermission,
    client_probe,
)
from integrations.proxmox_backup_server.client import ProxmoxBackupServerClient
from integrations.proxmox_backup_server.schema import INTEGRATION
from platform.credentials.verification import VerificationResult

_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "Backup Server rejected the token. Re-issue it under Access Control → API Tokens "
        "and paste it as one line: user@realm!tokenid:secret. The separator is a colon "
        "here, not an equals sign — that is a Proxmox VE token format."
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The token is valid and is not permitted on this datastore. Datastore.Audit is "
        "granted per datastore path, so a token that reads one store reports nothing at "
        "all about the next."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Proxmox Backup Server credential is configured for this team."
    ),
    IntegrationErrorReason.REFUSED: (
        "The proxy refused the call before it left: this server's address is not in the "
        "integration's declared allow-list."
    ),
    IntegrationErrorReason.PROXY_UNAVAILABLE: (
        "Neither the credential proxy nor the Backup Server answered."
    ),
}

_GRANTED_AT: Final = (
    "Access Control → Permissions, granting Datastore.Audit on /datastore or on each "
    "datastore path this deployment backs up to"
)

_NO_INTROSPECTION: Final = (
    "Backup Server has no endpoint that reports what a token may do, so the permission is "
    "probed by making the cheapest form of the read that needs it"
)

DATASTORE_READ: Final = RequiredPermission(
    name="Datastore.Audit on /datastore",
    grants="read datastore usage, snapshots, verification outcomes and garbage-collection state",
    capabilities=("proxmox_backup_server_datastore_health",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (DATASTORE_READ,)


@dataclass(frozen=True, slots=True)
class ProxmoxBackupServerVerifier:
    """Checks a stored Backup Server credential end to end, and what it may read."""

    integration: str = INTEGRATION
    host: str = ""

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "reads /version — the cheapest call a Backup Server answers that still requires "
            "the token, so it proves authentication without touching a datastore"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per permission this integration's capabilities need."""
        return (
            client_probe(
                DATASTORE_READ,
                build=self._client,
                call=lambda client: client.read_response("/status/datastore-usage"),
                fallback_note=_NO_INTROSPECTION,
            ),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether the Backup Server accepted this team's credential."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            return Connectivity(
                reachable=False,
                detail="the verifier needs a proxy transport and a request context",
            )
        try:
            response = await self._client(transport, context).ping()
        except IntegrationError as error:
            return Connectivity(
                reachable=False,
                detail=_ADVICE.get(error.reason, str(error)),
                status_code=error.status_code,
            )
        return Connectivity(
            reachable=True,
            detail="Proxmox Backup Server accepted the token.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what the Backup Server said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> ProxmoxBackupServerClient:
        """Return a client for one probe. It holds no token; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a Backup Server probe needs a proxy transport and a request context")
        if self.host:
            return ProxmoxBackupServerClient(transport=transport, context=context, host=self.host)
        return ProxmoxBackupServerClient(transport=transport, context=context)


__all__ = ["DATASTORE_READ", "PERMISSIONS", "ProxmoxBackupServerVerifier"]
