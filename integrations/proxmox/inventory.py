"""The operator's own declaration of what should be there, as a second source.

An API says what *is*. It cannot say what was meant. A guest that is stopped is
a fact; whether that is fine depends on whether anybody intended it to be
running, and Proxmox has no field for intent — there is no "expected state" on a
container and no "owner" on a node.

Operators who run their infrastructure properly already write this down. The
reference cluster keeps a schema-validated YAML inventory declaring each node's
role, each guest's expected state, and who owns each service. That file is
better evidence of intent than anything this system could infer, and it is
already maintained because something else depends on it.

So it is read as a **second source for the same resources**, reconciled under
feature 038's multi-source rule rather than stored beside the live view. Two
consequences, and the second is the point:

**The identities have to match.** A node is identified exactly as the live sweep
identifies it. A guest is identified by cluster, kind and VMID with no creation
discriminator — the inventory does not know when a guest was created — so the two
sources meet on the correlation key instead, which is what that field is for.

**Disagreement is retained, not resolved.** Where the inventory says a guest
should be running and the API says it is stopped, both values stay and the
divergence becomes a signal. Picking a winner would throw away the only
interesting thing about the pair: a detector reading "declared running, observed
stopped" has found drift, and a detector reading either value alone has found
nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from integrations._base.discovery import DiscoveredResource, DiscoveryPage, declare
from integrations.proxmox.identity import cluster_identity, guest_identity, node_identity
from platform.estate.discovery.port import DiscoveryMode, SweepBudget
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE, KIND_VIRTUAL_MACHINE

#: The source name this second view registers under. Distinct from ``proxmox``
#: on purpose: reconciliation is between *sources*, and an inventory that
#: registered under the same name would overwrite the live view rather than be
#: reconciled with it.
INVENTORY_SOURCE: Final = "proxmox_inventory"

#: How often a file on disk is re-read. Long, because it changes when a person
#: changes it, and the sweep that notices five minutes later is not late.
INVENTORY_INTERVAL_SECONDS: Final = 900


class InventoryInvalid(ValueError):
    """The declarative inventory is not one, with every problem named at once.

    Reported together rather than one at a time. An operator fixing an inventory
    wants one pass through the file, and a loader that reported the second
    mistake only after the first was corrected is a loader people stop running.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__(
            f"the declarative inventory has {len(self.problems)} problem(s): "
            + "; ".join(self.problems)
        )


@dataclass(frozen=True, slots=True)
class DeclaredNode:
    """What the operator says a node is for."""

    name: str
    role: str = ""
    expected_state: str = "online"
    owner: str = ""


@dataclass(frozen=True, slots=True)
class DeclaredGuest:
    """What the operator says a guest is for, and whether it should be running."""

    vmid: int
    kind: str
    name: str = ""
    expected_state: str = "running"
    owner: str = ""
    role: str = ""


@dataclass(frozen=True, slots=True)
class Inventory:
    """One cluster's declared shape, validated on the way in."""

    cluster: str
    nodes: tuple[DeclaredNode, ...] = ()
    guests: tuple[DeclaredGuest, ...] = ()

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any], *, cluster: str) -> Inventory:
        """Return the inventory ``document`` declares, or raise naming every problem.

        Deliberately strict about the two fields identity depends on — a node's
        name and a guest's VMID and kind. Everything else is optional, because an
        operator who declared only "these guests should be running" has still
        declared something this system could not otherwise know.
        """
        problems: list[str] = []
        nodes: list[DeclaredNode] = []
        for index, entry in enumerate(_entries(document, "nodes", problems)):
            name = str(entry.get("name", "")).strip()
            if not name:
                problems.append(f"nodes[{index}] has no name, so nothing can be matched to it")
                continue
            nodes.append(
                DeclaredNode(
                    name=name,
                    role=str(entry.get("role", "")),
                    expected_state=str(entry.get("expected_state", "online")),
                    owner=str(entry.get("owner", "")),
                )
            )

        guests: list[DeclaredGuest] = []
        for index, entry in enumerate(_entries(document, "guests", problems)):
            vmid = entry.get("vmid")
            kind = str(entry.get("kind", "")).strip()
            if not isinstance(vmid, int):
                problems.append(
                    f"guests[{index}] has no integer vmid, which is the only thing the API "
                    f"and this file can be matched on"
                )
                continue
            if kind not in {"lxc", "qemu"}:
                problems.append(
                    f"guests[{index}] declares kind {kind!r}; a Proxmox guest is 'lxc' or 'qemu'"
                )
                continue
            guests.append(
                DeclaredGuest(
                    vmid=vmid,
                    kind=kind,
                    name=str(entry.get("name", "")),
                    expected_state=str(entry.get("expected_state", "running")),
                    owner=str(entry.get("owner", "")),
                    role=str(entry.get("role", "")),
                )
            )

        if problems:
            raise InventoryInvalid(problems)
        return cls(cluster=cluster, nodes=tuple(nodes), guests=tuple(guests))

    def node(self, name: str) -> DeclaredNode:
        """Return the declaration for ``name``.

        Raises:
            KeyError: the inventory does not declare that node.
        """
        found = next((node for node in self.nodes if node.name == name), None)
        if found is None:
            raise KeyError(f"the inventory declares no node called {name!r}")
        return found

    def guest(self, vmid: int) -> DeclaredGuest:
        """Return the declaration for ``vmid``.

        Raises:
            KeyError: the inventory does not declare that guest.
        """
        found = next((guest for guest in self.guests if guest.vmid == vmid), None)
        if found is None:
            raise KeyError(f"the inventory declares no guest with vmid {vmid}")
        return found


@dataclass(frozen=True, slots=True)
class Divergence:
    """One place the declaration and the live reading disagree.

    Both values are kept. Which one is "right" is a judgement that depends on
    what changed and why, and it is exactly the judgement a detector exists to
    prompt rather than one a reconciliation should make silently.
    """

    native_id: str
    field: str
    expected: str
    observed: str
    subject: str = ""

    def as_signal(self) -> tuple[str, str]:
        """Return this divergence as an estate signal: a name and a value."""
        return (
            f"divergence.{self.field}",
            f"declared {self.expected or 'nothing'}, observed {self.observed or 'nothing'}",
        )

    def describe(self) -> str:
        """Return the sentence a finding shows."""
        return (
            f"{self.subject or self.native_id}: the inventory declares {self.field} "
            f"{self.expected or 'nothing'} and the cluster reports "
            f"{self.observed or 'nothing'}"
        )


@dataclass(frozen=True, slots=True)
class InventorySource:
    """The declarative inventory, behind the same discovery protocol as the API.

    A source rather than a lookup, so that reconciliation is the estate's own
    multi-source rule and not a second merge written here. It makes no provider
    calls at all, which is why its declaration says one: a source that declared
    zero would be a source the sweep could not budget for.
    """

    inventory: Inventory

    @property
    def declaration(self) -> Any:
        """Return what this source says about itself."""
        return declare(
            INVENTORY_SOURCE,
            kinds=(KIND_NODE, KIND_CONTAINER, KIND_VIRTUAL_MACHINE),
            interval_seconds=INVENTORY_INTERVAL_SECONDS,
            rate_limit_per_minute=60,
            max_provider_calls=1,
        )

    async def discover(
        self,
        *,
        mode: DiscoveryMode,
        cursor: str = "",
        budget: SweepBudget,
    ) -> DiscoveryPage:
        """Return the resources the inventory declares, in one page where they fit.

        ``complete`` is true only for a full sweep that emitted everything. A
        declaration has no notion of "changed since", so an incremental pass over
        one is the whole file again — and marking that complete would license the
        estate to conclude that anything it did not see had been deleted, from a
        page that never claimed to be exhaustive.

        The cursor exists because an inventory can be large: an operator with two
        hundred guests declared has a file this may not fit in one page of the
        estate's own budget, and suspending is the same answer the live source
        gives.
        """
        cluster = self.inventory.cluster
        resources = [
            DiscoveredResource(
                kind=KIND_NODE,
                native_id=node_identity(cluster, node.name),
                display_name=node.name,
                correlation_key=node.name,
                parent_native_id=cluster_identity(cluster),
                provider_status=node.expected_state,
                signals={
                    "declared_role": node.role,
                    "declared_state": node.expected_state,
                    "declared_owner": node.owner,
                },
            )
            for node in self.inventory.nodes
        ]
        resources.extend(
            DiscoveredResource(
                kind=KIND_CONTAINER if guest.kind == "lxc" else KIND_VIRTUAL_MACHINE,
                native_id=guest_identity(cluster, guest.kind, guest.vmid, created_at=""),
                display_name=guest.name or f"{guest.kind}/{guest.vmid}",
                correlation_key=f"{cluster}/{guest.kind}/{guest.vmid}",
                provider_status=guest.expected_state,
                signals={
                    "declared_state": guest.expected_state,
                    "declared_owner": guest.owner,
                    "declared_role": guest.role,
                },
            )
            for guest in self.inventory.guests
        )

        start = int(cursor) if cursor.isdigit() else 0
        window = resources[start : start + budget.max_resources]
        emitted = start + len(window)
        exhausted = emitted >= len(resources)
        return DiscoveryPage(
            resources=tuple(window),
            complete=exhausted and mode is DiscoveryMode.FULL,
            cursor="" if exhausted else str(emitted),
            provider_calls=0,
        )


def divergences(
    inventory: Inventory,
    observed: Iterable[DiscoveredResource],
) -> tuple[Divergence, ...]:
    """Return every place the inventory and the live sweep disagree.

    Matched on the correlation key for guests and on the node name for nodes,
    because those are the two things both sources can name identically. A guest
    the inventory declares and the sweep never saw is a divergence too — the
    strongest kind, and the one an "expected state" file exists to catch.
    """
    by_correlation = {found.correlation_key: found for found in observed if found.correlation_key}
    found: list[Divergence] = []

    for node in inventory.nodes:
        live = by_correlation.get(node.name)
        if live is None:
            found.append(
                Divergence(
                    native_id=node_identity(inventory.cluster, node.name),
                    field="presence",
                    expected="declared in the inventory",
                    observed="",
                    subject=node.name,
                )
            )
            continue
        if node.expected_state and live.provider_status != node.expected_state:
            found.append(
                Divergence(
                    native_id=live.native_id,
                    field="state",
                    expected=node.expected_state,
                    observed=live.provider_status,
                    subject=node.name,
                )
            )

    for guest in inventory.guests:
        key = f"{inventory.cluster}/{guest.kind}/{guest.vmid}"
        live = by_correlation.get(key)
        if live is None:
            found.append(
                Divergence(
                    native_id=guest_identity(
                        inventory.cluster, guest.kind, guest.vmid, created_at=""
                    ),
                    field="presence",
                    expected="declared in the inventory",
                    observed="",
                    subject=guest.name or str(guest.vmid),
                )
            )
            continue
        if guest.expected_state and live.provider_status != guest.expected_state:
            found.append(
                Divergence(
                    native_id=live.native_id,
                    field="state",
                    expected=guest.expected_state,
                    observed=live.provider_status,
                    subject=guest.name or str(guest.vmid),
                )
            )

    return tuple(found)


def _entries(
    document: Mapping[str, Any], key: str, problems: list[str]
) -> tuple[Mapping[str, Any], ...]:
    """Return the list under ``key``, recording a problem when it is not one."""
    value = document.get(key, ())
    if isinstance(value, Mapping) or not isinstance(value, Sequence):
        problems.append(f"{key!r} must be a list of entries")
        return ()
    return tuple(entry for entry in value if isinstance(entry, Mapping))


__all__ = [
    "INVENTORY_INTERVAL_SECONDS",
    "INVENTORY_SOURCE",
    "DeclaredGuest",
    "DeclaredNode",
    "Divergence",
    "Inventory",
    "InventoryInvalid",
    "InventorySource",
    "divergences",
]
