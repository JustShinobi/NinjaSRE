"""What kinds of thing the estate models, and how an integration adds one.

FR-002 asks for two things that pull against each other: kinds must be declared
rather than free text, *and* an integration must be able to add one without the
core model changing. A closed enumeration gives the first and refuses the
second; a string column gives the second and refuses the first.

So: a registry. Declaration is a value — a ``ResourceKind`` with a name, a
label, the parents it may hang from, the attributes it has and their types, and
how long an observation of it stands. Extension is a call, made while the
deployment is being composed. Closure is ``seal``, called once wiring is done,
after which the set is fixed for the life of the process.

**Rejection happens at registration.** A kind naming a parent nobody declared is
wrong the moment it is declared, and a registry that accepted it would surface
the mistake on the first sweep of a production integration instead. The same
holds for the discovery declarations in ``platform/estate/discovery``: the kinds
an integration says it will emit are checked when it registers, not when it
returns one.

The core kinds below are the ones the platform models itself: the shapes that
appear whatever a deployment has connected. Everything provider-specific — a
Proxmox backup job, a Kubernetes namespace — is registered by its integration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from config.constants.estate import DEFAULT_FRESHNESS_SECONDS, MIN_FRESHNESS_SECONDS
from platform.estate.attributes import AttributeType, TypedAttributes, typed
from platform.estate.errors import (
    KindAlreadyRegistered,
    RegistrySealed,
    UnknownResourceKind,
)

#: The kinds the platform models itself, named as constants so that a caller
#: comparing against one cannot misspell it and get a silent miss.
KIND_CLUSTER: Final = "cluster"
KIND_NODE: Final = "node"
KIND_VIRTUAL_MACHINE: Final = "virtual_machine"
KIND_CONTAINER: Final = "container"
KIND_DATASTORE: Final = "datastore"
KIND_SERVICE: Final = "service"
KIND_BACKUP_JOB: Final = "backup_job"


@dataclass(frozen=True, slots=True)
class ResourceKind:
    """One declared kind of thing the estate can hold.

    ``parent_kinds`` is what a resource of this kind may hang from, and it is a
    tuple rather than a single value because a guest may sit on a node in one
    deployment and directly on a cluster in another. An empty tuple means the
    kind is a root — a cluster hangs from nothing.

    ``freshness_seconds`` is how long an observation of this kind stands before
    it reports stale. It is per kind because a hypervisor node polled every
    minute and a backup job that runs nightly cannot share one number without
    one of them lying.
    """

    name: str
    label: str
    integration: str = ""
    parent_kinds: tuple[str, ...] = ()
    attributes: Mapping[str, AttributeType] = field(default_factory=dict)
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("A resource kind needs a name.")
        if self.freshness_seconds < MIN_FRESHNESS_SECONDS:
            raise ValueError(
                f"a freshness interval of {self.freshness_seconds}s for {self.name!r} is below "
                f"MIN_FRESHNESS_SECONDS ({MIN_FRESHNESS_SECONDS}s). A kind whose observations "
                f"expire faster than the sweep that produces them reports stale forever."
            )

    def typed(self, raw: Mapping[str, Any]) -> TypedAttributes:
        """Return ``raw`` reduced to the attributes this kind declares."""
        return typed(self.attributes, raw)


#: What the platform models whatever a deployment has connected. Provider
#: shapes are registered by their integration, which is the whole of FR-002's
#: extensibility half.
CORE_KINDS: Final[tuple[ResourceKind, ...]] = (
    ResourceKind(
        name=KIND_CLUSTER,
        label="Cluster",
        description="A set of nodes managed together.",
        attributes={
            "node_count": AttributeType.INTEGER,
            "quorate": AttributeType.BOOLEAN,
            "version": AttributeType.STRING,
        },
    ),
    ResourceKind(
        name=KIND_NODE,
        label="Node",
        description="A machine that runs workloads.",
        parent_kinds=(KIND_CLUSTER,),
        attributes={
            "cpu_count": AttributeType.INTEGER,
            "memory_bytes": AttributeType.INTEGER,
            "load_average": AttributeType.FLOAT,
            "uptime_seconds": AttributeType.INTEGER,
            "version": AttributeType.STRING,
            # Where on the network this sits. Declared on the three kinds that
            # have one, because it is what a zone is derived from — and a kind
            # that declares no address is one nothing expects a zone of, which
            # is what keeps a backup job out of the unplaced list.
            "address": AttributeType.STRING,
        },
    ),
    ResourceKind(
        name=KIND_VIRTUAL_MACHINE,
        label="Virtual machine",
        description="A full guest with its own kernel.",
        parent_kinds=(KIND_NODE,),
        attributes={
            "cores": AttributeType.INTEGER,
            "memory_bytes": AttributeType.INTEGER,
            "disk_bytes": AttributeType.INTEGER,
            "operating_system": AttributeType.STRING,
            "boot_order": AttributeType.STRING,
            "started_at": AttributeType.TIMESTAMP,
            "address": AttributeType.STRING,
            # The hypervisor's own numeric identifier for this guest. Declared
            # for the same reason `address` is: it is the label every host-side
            # series for the guest is keyed by, and a resource-usage query built
            # without it returns nothing — which reads as a guest under no
            # pressure rather than as a question nobody asked properly.
            "vmid": AttributeType.INTEGER,
        },
    ),
    ResourceKind(
        name=KIND_CONTAINER,
        label="Container",
        description="A guest sharing the host kernel.",
        parent_kinds=(KIND_NODE,),
        attributes={
            "cores": AttributeType.INTEGER,
            "memory_bytes": AttributeType.INTEGER,
            "image": AttributeType.STRING,
            "started_at": AttributeType.TIMESTAMP,
            "address": AttributeType.STRING,
            # As above, and here it is load-bearing rather than convenient: a
            # container shares the host's kernel, so the host's series keyed by
            # this identifier is the *only* correct source for its resource
            # usage.
            "vmid": AttributeType.INTEGER,
        },
    ),
    ResourceKind(
        name=KIND_DATASTORE,
        label="Datastore",
        description="Where guests and backups are kept.",
        parent_kinds=(KIND_NODE, KIND_CLUSTER),
        attributes={
            "total_bytes": AttributeType.INTEGER,
            "used_bytes": AttributeType.INTEGER,
            "storage_type": AttributeType.STRING,
            "shared": AttributeType.BOOLEAN,
        },
    ),
    ResourceKind(
        name=KIND_SERVICE,
        label="Service",
        description="Something that serves requests, wherever it runs.",
        parent_kinds=(KIND_NODE, KIND_VIRTUAL_MACHINE, KIND_CONTAINER, KIND_CLUSTER),
        attributes={
            "endpoint": AttributeType.STRING,
            "replicas": AttributeType.INTEGER,
            "version": AttributeType.STRING,
        },
    ),
    ResourceKind(
        name=KIND_BACKUP_JOB,
        label="Backup job",
        # A nightly job observed hourly is fresh; observed daily it is not. The
        # interval is a day plus an hour, so one missed run is not staleness.
        freshness_seconds=90_000,
        description="Recurring work that protects other resources.",
        parent_kinds=(KIND_CLUSTER, KIND_NODE),
        attributes={
            "schedule": AttributeType.STRING,
            "enabled": AttributeType.BOOLEAN,
            "last_run_at": AttributeType.TIMESTAMP,
            "covered_count": AttributeType.INTEGER,
        },
    ),
)


@dataclass(slots=True)
class KindRegistry:
    """Every kind this deployment models, open while composing and closed after.

    Not a module-level singleton. A test that registered a kind would otherwise
    change what every other test in the session sees, and the failure would land
    on whichever test ran next — which is the least diagnosable shape a test
    failure has. A deployment holds one; ``core_registry`` builds it.
    """

    _kinds: dict[str, ResourceKind] = field(default_factory=dict)
    _sealed: bool = False

    def register(self, kind: ResourceKind) -> ResourceKind:
        """Declare ``kind`` and return it.

        Raises ``RegistrySealed`` after the deployment has closed the set,
        ``KindAlreadyRegistered`` for a name somebody already owns, and
        ``UnknownResourceKind`` for a parent nobody declared — the last one
        being the check that makes "rejected at registration, not at write"
        true rather than aspirational.
        """
        if self._sealed:
            raise RegistrySealed(kind.name)
        if kind.name in self._kinds:
            raise KindAlreadyRegistered(kind.name)
        for parent in kind.parent_kinds:
            if parent not in self._kinds:
                raise UnknownResourceKind(parent, declared_by=kind.name)

        self._kinds[kind.name] = kind
        return kind

    def seal(self) -> None:
        """Close the set for the life of this registry. Idempotent."""
        self._sealed = True

    @property
    def is_sealed(self) -> bool:
        """Return whether further registration is refused."""
        return self._sealed

    def get(self, name: str) -> ResourceKind:
        """Return the kind called ``name``, or raise ``UnknownResourceKind``."""
        kind = self._kinds.get(name)
        if kind is None:
            raise UnknownResourceKind(name)
        return kind

    def knows(self, name: str) -> bool:
        """Return whether ``name`` has been declared."""
        return name in self._kinds

    def names(self) -> tuple[str, ...]:
        """Return every declared kind's name, in declaration order."""
        return tuple(self._kinds)

    def all(self) -> tuple[ResourceKind, ...]:
        """Return every declared kind, in declaration order."""
        return tuple(self._kinds.values())

    def freshness_for(self, name: str) -> int:
        """Return how long an observation of ``name`` stands.

        Falls back to the default for a kind nobody declared rather than
        raising, because this is called on the *read* path: a resource stored
        under a kind an integration has since stopped registering must still be
        readable, and the honest answer for it is the deployment's default
        rather than an exception on a listing.
        """
        kind = self._kinds.get(name)
        return kind.freshness_seconds if kind is not None else DEFAULT_FRESHNESS_SECONDS


def core_registry() -> KindRegistry:
    """Return a registry holding the core kinds, open for an integration's own.

    A new registry each call. Composition wires exactly one of these into a
    deployment and seals it; anything else holding one is a test, and a test
    that could pollute the next one is the bug this shape prevents.
    """
    registry = KindRegistry()
    for kind in CORE_KINDS:
        registry.register(kind)
    return registry


__all__ = [
    "CORE_KINDS",
    "KIND_BACKUP_JOB",
    "KIND_CLUSTER",
    "KIND_CONTAINER",
    "KIND_DATASTORE",
    "KIND_NODE",
    "KIND_SERVICE",
    "KIND_VIRTUAL_MACHINE",
    "KindRegistry",
    "ResourceKind",
    "core_registry",
]
