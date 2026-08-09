"""The writes this deployment may make to a hypervisor, and the table behind them.

Thirteen actions, in four families, every one of them resolving its autonomy
through the policy engine and closing its loop through the verification
obligations — there is no hypervisor-specific autonomy path, and adding one would
be the thing this package exists not to do.

What is here that the cross-vendor remediation capabilities do not have:

``risk``
    The table. Every action, its class, and the reversibility, data-loss,
    availability and blast-radius reasoning behind it — plus the prohibitions,
    which are the deliberate hole: nothing may fence a node, force quorum, alter
    corosync, restart a node's own services, write a node's network
    configuration, or extend a pool.

``declaration``
    What a write has to say before it may be registered, checked as it is built.
    Incomplete is an import error rather than a surprise during an incident.

``preconditions``
    Pure evaluation against a reading taken immediately before the write. A guest
    that migrated since the proposal, a lock that has been taken by live work, a
    cluster that has lost quorum, a two-node cluster whose peer is silent — each
    is a refusal rather than a proceed.

``plane``
    Where a write actually happens, and where a Proxmox task's own outcome — not
    the HTTP status of the request that started it — decides whether it worked.
"""

from __future__ import annotations

from typing import Final

from capabilities.tools.remediation.proxmox import backups, guests, movement, storage
from capabilities.tools.remediation.proxmox.declaration import (
    ProxmoxRemediation,
    RegistrationRefused,
    RollbackDeclaration,
    WriteCategory,
    declarations_of,
)
from capabilities.tools.remediation.proxmox.plane import (
    HypervisorTaskFailed,
    ProxmoxControlPlane,
    TaskEvidence,
)
from capabilities.tools.remediation.proxmox.preconditions import (
    Facts,
    Precondition,
    PreconditionRefused,
)
from platform.remediation.components import RemediationComponents

#: Every hypervisor write, declared, keyed by the capability that performs it.
#: Explicit rather than discovered, because "which writes can this deployment
#: make to the hypervisor" is a question an operator should be able to answer by
#: reading one value.
DECLARATIONS: Final[dict[str, ProxmoxRemediation]] = declarations_of(
    (*guests.DECLARED, *movement.DECLARED, *storage.DECLARED, *backups.DECLARED)
)

#: The four components of each of them, in the same order.
COMPONENTS: Final[tuple[RemediationComponents, ...]] = (
    *guests.COMPONENTS,
    *movement.COMPONENTS,
    *storage.COMPONENTS,
    *backups.COMPONENTS,
)


def declaration_for(capability: str) -> ProxmoxRemediation:
    """Return what ``capability`` declared, or raise naming what is declared.

    Raises:
        KeyError: this package declares no such write.
    """
    found = DECLARATIONS.get(capability)
    if found is None:
        raise KeyError(
            f"{capability!r} is not a hypervisor write this deployment declares. It declares: "
            f"{', '.join(sorted(DECLARATIONS))}."
        )
    return found


__all__ = [
    "COMPONENTS",
    "DECLARATIONS",
    "Facts",
    "HypervisorTaskFailed",
    "Precondition",
    "PreconditionRefused",
    "ProxmoxControlPlane",
    "ProxmoxRemediation",
    "RegistrationRefused",
    "RollbackDeclaration",
    "TaskEvidence",
    "WriteCategory",
    "declaration_for",
]
