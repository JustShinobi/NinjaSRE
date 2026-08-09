"""What a Proxmox token has to be allowed to do, for reading and for writing.

Proxmox's permission model is a path tree: a role is granted on ``/``, ``/vms``,
``/storage`` or ``/nodes``, and a token's effective privileges are the union of
what its user holds and — for a *privilege-separated* token — the intersection
with what the token itself was granted. An operator can therefore paste a
perfectly valid token that can read the cluster and not the guests, and every
symptom of that appears during an incident.

**Read and write sufficiency are reported separately, and that is the whole
point.** A read-only token is a legitimate and, for many operators, preferable
configuration: this feature reads and nothing else, and feature 046's writes
land behind an approval gate that the operator may never want to open.
Verification that failed because write privileges were absent would push every
operator towards a token that can destroy guests, in order to make a setup screen
go green. So the report says "sufficient for reading; not sufficient for the
write operations feature 046 would need", and both halves are true and useful.

**A missing privilege is named with the path it was needed for.** ``Sys.Audit``
granted on ``/nodes`` and not on ``/`` is a real and common configuration, and an
operator told only "insufficient privileges" will re-grant the role they already
have on the path they already have it on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

#: Where an operator changes what a token may do. Written once because it belongs
#: in every message about a missing privilege.
GRANTED_AT: Final = (
    "Datacenter → Permissions → add a permission for this token's path and role, "
    "and check 'Privilege Separation' on the token itself"
)


@dataclass(frozen=True, slots=True)
class RequiredPrivilege:
    """One Proxmox privilege on one path, and what depends on it."""

    privilege: str
    path: str
    grants: str
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError(
                f"{self.privilege}: a Proxmox privilege is granted on a path, and {self.path!r} "
                f"is not one. The path is half the grant."
            )

    def describe(self) -> str:
        """Return the privilege as an operator would search for it."""
        return f"{self.privilege} on {self.path}"


#: What this feature needs. Every one of them is an ``Audit`` privilege, which is
#: Proxmox's read-only role family — a token holding exactly these can enumerate
#: the estate and change nothing, which is the configuration this integration is
#: designed to be run with.
READ_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="Sys.Audit",
        path="/",
        grants="read cluster status, quorum, corosync configuration and the cluster log",
        capabilities=("proxmox_cluster_health",),
    ),
    RequiredPrivilege(
        privilege="VM.Audit",
        path="/vms",
        grants="read every guest's status, configuration, snapshots and task history",
        capabilities=("proxmox_protection_gaps",),
    ),
    RequiredPrivilege(
        privilege="Datastore.Audit",
        path="/storage",
        grants="read datastore status, contents and the thin pools underneath them",
        capabilities=("proxmox_storage_pressure",),
    ),
)

#: What feature 046 will need, declared here so verification can report on it
#: without this feature depending on it. Nothing in this integration uses these;
#: they exist so that an operator can be told, once, whether the token they
#: pasted would also support remediation — and choose deliberately.
WRITE_PRIVILEGES: Final[tuple[RequiredPrivilege, ...]] = (
    RequiredPrivilege(
        privilege="VM.PowerMgmt",
        path="/vms",
        grants="start, stop and reboot guests",
    ),
    RequiredPrivilege(
        privilege="VM.Migrate",
        path="/vms",
        grants="move a guest to another node",
    ),
    RequiredPrivilege(
        privilege="VM.Backup",
        path="/vms",
        grants="take a backup of a guest outside its schedule",
    ),
)


@dataclass(frozen=True, slots=True)
class PrivilegeGap:
    """One privilege a token does not hold, and where it was needed."""

    privilege: str
    path: str
    grants: str

    def describe(self) -> str:
        """Return the sentence an operator can act on."""
        return f"{self.privilege} on {self.path} — without it, nothing can {self.grants}"


@dataclass(frozen=True, slots=True)
class PrivilegeReport:
    """Whether a token can read, whether it can write, and what is missing from each."""

    held: Mapping[str, tuple[str, ...]]
    missing_read: tuple[PrivilegeGap, ...] = ()
    missing_write: tuple[PrivilegeGap, ...] = ()

    @property
    def read_sufficient(self) -> bool:
        """Return whether the token can do everything this feature reads."""
        return not self.missing_read

    @property
    def write_sufficient(self) -> bool:
        """Return whether it would also support the write operations of feature 046."""
        return not self.missing_write

    def explain(self) -> str:
        """Return every gap, named with its path, in one message.

        All of them at once. An operator fixing privileges wants to make one
        pass through the permissions screen, not to discover the second missing
        grant after re-running verification for the first.
        """
        lines: list[str] = []
        if self.missing_read:
            lines.append("Missing for reading:")
            lines.extend(f"  {gap.describe()}" for gap in self.missing_read)
        if self.missing_write:
            lines.append("Missing for the write operations a later feature would need:")
            lines.extend(f"  {gap.describe()}" for gap in self.missing_write)
        if lines:
            lines.append(f"Granted at: {GRANTED_AT}")
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a console or the CLI renders."""
        return {
            "read_sufficient": self.read_sufficient,
            "write_sufficient": self.write_sufficient,
            "missing_read": [gap.describe() for gap in self.missing_read],
            "missing_write": [gap.describe() for gap in self.missing_write],
            "granted_at": GRANTED_AT,
        }


def privilege_report(permissions: Mapping[str, Any]) -> PrivilegeReport:
    """Return what a token can and cannot do, from what ``/access/permissions`` said.

    Proxmox answers that endpoint with the token's **effective** privileges,
    which already accounts for privilege separation — so a separated token and a
    full one are read the same way here and neither needs a special case.

    A privilege granted on a parent path covers the paths beneath it, which is
    how Proxmox itself resolves them: ``Sys.Audit`` on ``/`` is ``Sys.Audit``
    everywhere, and a check that only looked for an exact path match would report
    a correctly-configured administrator's token as insufficient.
    """
    held = {
        str(path): tuple(sorted(str(name) for name, granted in _granted(value).items() if granted))
        for path, value in permissions.items()
    }
    return PrivilegeReport(
        held=held,
        missing_read=tuple(
            _gap(privilege) for privilege in READ_PRIVILEGES if not _holds(held, privilege)
        ),
        missing_write=tuple(
            _gap(privilege) for privilege in WRITE_PRIVILEGES if not _holds(held, privilege)
        ),
    )


def _granted(value: Any) -> Mapping[str, Any]:
    """Return the privilege map at one path, whatever shape Proxmox sent it in."""
    return value if isinstance(value, dict) else {}


def _holds(held: Mapping[str, tuple[str, ...]], required: RequiredPrivilege) -> bool:
    """Return whether ``held`` grants ``required``, inheriting from parent paths."""
    return any(
        required.privilege in privileges and _covers(path, required.path)
        for path, privileges in held.items()
    )


def _covers(granted_at: str, needed_at: str) -> bool:
    """Return whether a grant on ``granted_at`` reaches ``needed_at``.

    ``/`` covers everything; ``/vms`` covers ``/vms/100``; ``/vms`` does not
    cover ``/storage``. Proxmox resolves it this way and a check that did not
    would report a working token as broken.
    """
    if granted_at == "/":
        return True
    return needed_at == granted_at or needed_at.startswith(f"{granted_at}/")


def _gap(required: RequiredPrivilege) -> PrivilegeGap:
    """Return the gap record for a privilege a token does not hold."""
    return PrivilegeGap(privilege=required.privilege, path=required.path, grants=required.grants)


__all__ = [
    "GRANTED_AT",
    "READ_PRIVILEGES",
    "WRITE_PRIVILEGES",
    "PrivilegeGap",
    "PrivilegeReport",
    "RequiredPrivilege",
    "privilege_report",
]
