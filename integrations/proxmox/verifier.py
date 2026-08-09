"""Proves a Proxmox credential works, and says separately what it may do.

Three questions, where most integrations have two, and the third is the one that
changes an operator's behaviour.

**Does the credential authenticate?** One cheap call — the version endpoint,
which every Proxmox node answers and which still requires the token.

**Which privileges does it hold?** Proxmox *can* be asked, which is unusual and
worth using: ``/access/permissions`` returns the token's effective privileges,
already accounting for privilege separation. So the report is not inferred from a
sequence of probes that happened to succeed; it is the vendor's own answer, and a
missing privilege is named with the path it was needed for.

**Would it also support writing?** Reported separately and never as a failure.
This module reads and nothing else. A verification that went red because the
token could not stop a guest would push every operator towards a token that can
destroy one, in order to make a setup screen turn green — so a read-only token
verifies as *sufficient*, clearly labelled, and the write answer is offered as
information for whoever decides later whether to open the remediation path.

The permission probes below are the framework's contract, one call each, and they
exist alongside the privilege report rather than instead of it: the probe proves
the call is permitted *in this deployment through this proxy*, which is a stronger
statement than a privilege listing, and the listing explains a refusal that a
probe can only report.
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
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.privileges import (
    GRANTED_AT,
    READ_PRIVILEGES,
    PrivilegeReport,
    privilege_report,
)
from integrations.proxmox.schema import INTEGRATION, tested_versions_note
from platform.credentials.verification import VerificationResult

#: What each failure means for Proxmox specifically, in the operator's terms.
#: "401" and "403" are different problems with different fixes, and an operator
#: told only that verification failed will check the wrong one first.
_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "Proxmox rejected the token. Re-issue it at Datacenter → Permissions → API Tokens "
        "and paste it as one line: user@realm!tokenid=secret. Pasting the secret alone is "
        "the commonest cause of this."
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The token is valid and its privileges are not. Check what it holds at Datacenter → "
        "Permissions, and remember that a privilege-separated token holds only what was "
        "granted to the token itself."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Proxmox credential is configured for this team."
    ),
    IntegrationErrorReason.REFUSED: (
        "The proxy refused the call before it left: this node's address is not in the "
        "integration's declared allow-list. Every node's address belongs there, not only "
        "the one in the configuration."
    ),
    IntegrationErrorReason.PROXY_UNAVAILABLE: (
        "Neither the credential proxy nor any configured Proxmox node answered. "
        "Authenticated calls have no path around the proxy."
    ),
}

_GRANTED_AT: Final = GRANTED_AT

#: FR-011's condition, written down. Proxmox *does* expose a privilege listing,
#: so the probes below are not standing in for one — they check that the call is
#: permitted through this deployment's proxy, which the listing cannot say.
_PROBES_ARE_NOT_A_SUBSTITUTE: Final = (
    "Proxmox answers /access/permissions with the token's effective privileges, so this "
    "probe is not standing in for an introspection endpoint — it checks that the call is "
    "permitted end to end through this deployment's credential proxy"
)

CLUSTER_READ: Final = RequiredPermission(
    name="Sys.Audit on /",
    grants="read cluster status, quorum, corosync configuration and the cluster log",
    capabilities=("proxmox_cluster_health",),
    where=_GRANTED_AT,
)

GUEST_READ: Final = RequiredPermission(
    name="VM.Audit on /vms",
    grants="read every guest's status, configuration, snapshots and task history",
    capabilities=("proxmox_protection_gaps",),
    where=_GRANTED_AT,
)

STORAGE_READ: Final = RequiredPermission(
    name="Datastore.Audit on /storage",
    grants="read datastore status, contents and the thin pools underneath them",
    capabilities=("proxmox_storage_pressure",),
    where=_GRANTED_AT,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (CLUSTER_READ, GUEST_READ, STORAGE_READ)


@dataclass(frozen=True, slots=True)
class ClusterReport:
    """What verification found: which cluster, how big, how old, and what it may do."""

    cluster: str
    node_count: int
    version: str
    quorate: bool
    privileges: PrivilegeReport
    endpoints: tuple[str, ...] = ()
    certificate: str = ""

    def summary(self) -> str:
        """Return the sentence an operator reads after pressing verify.

        Says which cluster was reached and, separately, what the token can do —
        with "read-only" as a stated, supported outcome rather than a warning.
        """
        reach = (
            f"Reached {self.cluster}: {self.node_count} node(s), Proxmox {self.version}, "
            f"{'quorate' if self.quorate else 'NOT quorate'}."
        )
        if not self.privileges.read_sufficient:
            return f"{reach} The token cannot read everything this integration needs."
        capability = (
            "sufficient for reading and for the writes the remediation capabilities make"
            if self.privileges.write_sufficient
            else "sufficient for reading; read-only, which is a supported choice"
        )
        return f"{reach} The token is {capability}."

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form the console and the CLI render."""
        return {
            "cluster": self.cluster,
            "node_count": self.node_count,
            "version": self.version,
            "quorate": self.quorate,
            "endpoints": list(self.endpoints),
            "certificate": self.certificate,
            "tested_versions": tested_versions_note(),
            "privileges": self.privileges.to_record(),
            "summary": self.summary(),
        }


@dataclass(frozen=True, slots=True)
class ProxmoxVerifier:
    """Checks a stored Proxmox credential end to end, and what it may do."""

    integration: str = INTEGRATION

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "reads /version — the cheapest call every Proxmox node answers that still "
            "requires the token, so it proves authentication without touching a guest"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per privilege this integration's capabilities need."""
        return (
            client_probe(
                CLUSTER_READ,
                build=self._client,
                call=lambda client: client.read_response("/cluster/status"),
                fallback_note=_PROBES_ARE_NOT_A_SUBSTITUTE,
            ),
            client_probe(
                GUEST_READ,
                build=self._client,
                call=lambda client: client.read_response(
                    "/cluster/resources", params={"type": "vm"}
                ),
                fallback_note=_PROBES_ARE_NOT_A_SUBSTITUTE,
            ),
            client_probe(
                STORAGE_READ,
                build=self._client,
                call=lambda client: client.read_response(
                    "/cluster/resources", params={"type": "storage"}
                ),
                fallback_note=_PROBES_ARE_NOT_A_SUBSTITUTE,
            ),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether Proxmox accepted this team's credential."""
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
            detail="Proxmox accepted the token.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what Proxmox said when this team's credential was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    async def describe(self, client: ProxmoxClient) -> ClusterReport:
        """Return which cluster was reached and what the token may do there.

        The answer the console shows after an operator presses verify: the
        cluster's name, how many nodes are in it, which Proxmox version it runs,
        whether it currently has quorum, and read and write sufficiency reported
        separately.
        """
        version = await client.version()
        status = await client.cluster_status()
        permissions = await client.access_permissions()
        return ClusterReport(
            cluster=status.name or "standalone",
            node_count=len(status.members),
            version=str(version.get("version", "")),
            quorate=status.quorate,
            privileges=privilege_report(permissions),
            endpoints=client.endpoints.hosts,
            certificate=client.trust.describe(),
        )

    def _client(self, transport: object, context: object) -> ProxmoxClient:
        """Return a client for one probe. It holds no token; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a Proxmox probe needs a proxy transport and a request context")
        return ProxmoxClient(transport=transport, context=context)


#: The privileges the report above is built from, re-exported so a document
#: generator does not have to reach into two modules to describe one credential.
REQUIRED_PRIVILEGES: Final = READ_PRIVILEGES


__all__ = [
    "CLUSTER_READ",
    "GUEST_READ",
    "PERMISSIONS",
    "REQUIRED_PRIVILEGES",
    "STORAGE_READ",
    "ClusterReport",
    "ProxmoxVerifier",
]
