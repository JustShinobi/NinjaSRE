"""What a Proxmox answer means, once, rather than at every call site.

The client could return the vendor's dictionaries and leave every caller to
reach into them. Three of these readings are the reason it does not.

**A quorum margin is arithmetic nobody should repeat.** Total votes minus the
quorum required is the number that decides whether losing a node makes
``/etc/pve`` read-only, and a two-node cluster's answer is zero. Computing it in
a detector, a tool, and a console is three chances to compute it differently.

**A thin pool has two percentages and they fail differently.** Data exhaustion
fills a volume; metadata exhaustion stops the pool accepting writes at all while
the data figure still looks comfortable. A reading that carried one number would
report the reference cluster's `data` pool as fine.

**A reading that is not there is not a reading of zero.** ``Reading`` is the type
that keeps "we looked and there is no ZFS", "we looked and the node did not
answer", and "nothing publishes this, so nobody is looking" apart. Collapsing
them into ``None`` is how an estate reports a fire as fine.

Everything here is derived from what the vendor sent and keeps the raw value
beside the verdict, for the reason the health mapping does: a wrong
interpretation is only diagnosable while the original is still there.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

#: Above this, a thin pool's metadata is close enough to exhaustion that the
#: pool will stop accepting writes before anybody notices the data percentage.
#: Named because Article II says a bound is a constant, and because the number
#: is a judgement rather than a fact.
METADATA_CRITICAL_PERCENT: Final = 90.0

#: Above this, a thin volume is close enough to its own ceiling that the guest
#: inside it is about to see write failures — regardless of what its datastore
#: reports.
VOLUME_CRITICAL_PERCENT: Final = 90.0


class ReadingUnavailable(LookupError):
    """A reading was required and the thing that publishes it did not answer."""


@dataclass(frozen=True, slots=True)
class Reading[T]:
    """A value that may honestly be absent, and says why when it is.

    Not ``T | None``. The three ways a Proxmox reading can be missing need
    different sentences in a report — the node did not answer, the technology is
    not present, nothing is publishing it — and a ``None`` erases the
    difference between all three and "the value is empty".
    """

    value: T | None = None
    available: bool = False
    unavailable_reason: str = ""
    #: What *would* publish this reading, when nothing currently does. FR-013e:
    #: naming the missing publisher is the difference between "nothing is
    #: failing" and "nothing is looking".
    published_by: str = ""

    @classmethod
    def of(cls, value: T) -> Reading[T]:
        """Return a reading that is present."""
        return cls(value=value, available=True)

    @classmethod
    def missing(cls, reason: str, *, published_by: str = "") -> Reading[T]:
        """Return a reading that is absent, carrying why and what would supply it."""
        return cls(available=False, unavailable_reason=reason, published_by=published_by)

    def require(self) -> T:
        """Return the value, or raise saying why there is not one.

        Raises:
            ReadingUnavailable: the reading is absent.
        """
        if not self.available or self.value is None:
            raise ReadingUnavailable(self.unavailable_reason or "the reading is not available")
        return self.value

    def or_else(self, fallback: T) -> T:
        """Return the value, or ``fallback`` when it is absent."""
        return self.value if self.available and self.value is not None else fallback

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a tool or a console renders."""
        return {
            "available": self.available,
            "value": self.value,
            "unavailable_reason": self.unavailable_reason,
            "published_by": self.published_by,
        }


# --- The cluster --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NodeMembership:
    """One node as the cluster's membership view sees it."""

    name: str
    online: bool
    node_id: int = 0
    address: str = ""
    local: bool = False


@dataclass(frozen=True, slots=True)
class ClusterStatus:
    """Quorum, votes, and who is in the cluster.

    ``is_clustered`` is false for a single-node installation, which answers
    ``/cluster/status`` with one node and no cluster record. That deployment has
    not lost quorum; it never had one, and reporting it as unquorate would be a
    critical finding about an installation that is working exactly as intended.
    """

    name: str
    members: tuple[NodeMembership, ...]
    quorate: bool = True
    expected_votes: int = 0
    total_votes: int = 0
    quorum_required: int = 0
    is_clustered: bool = True
    #: The quorum device as the membership view reports it — present here even
    #: when it contributes nothing, which is exactly the reference cluster's
    #: state and exactly what a device count would miss.
    quorum_device: str = ""
    version: str = ""

    @property
    def quorum_margin(self) -> int:
        """Return how many votes could be lost before quorum is.

        Zero on a two-node cluster with no quorum device: losing either node
        makes ``/etc/pve`` read-only and no guest can be started, stopped, or
        migrated on the survivor. Negative when quorum is already lost.
        """
        return self.total_votes - self.quorum_required

    @property
    def online_nodes(self) -> tuple[str, ...]:
        """Return the names of the nodes currently answering."""
        return tuple(member.name for member in self.members if member.online)

    @property
    def offline_nodes(self) -> tuple[str, ...]:
        """Return the names of the nodes that are not."""
        return tuple(member.name for member in self.members if not member.online)

    @property
    def has_non_contributing_quorum_device(self) -> bool:
        """Return whether a quorum device is configured and contributes no vote.

        The reference cluster's exact condition: a device appears in the
        membership view, its daemon has failed, and it carries zero votes. To
        anything counting configured devices this reads as protected.
        """
        return bool(self.quorum_device) and self.total_votes <= len(self.online_nodes)


@dataclass(frozen=True, slots=True)
class ClusterConfiguration:
    """The corosync configuration, and the two settings whose absence matters."""

    cluster_name: str = ""
    config_version: str = ""
    transport: str = ""
    secure_authentication: bool = False
    nodes: tuple[Mapping[str, Any], ...] = ()
    two_node: bool = False
    wait_for_all: bool = False
    has_quorum_device: bool = False


@dataclass(frozen=True, slots=True)
class HighAvailabilityState:
    """Managed resources, groups, who the manager is, and the fencing mode."""

    resources: tuple[Mapping[str, Any], ...] = ()
    groups: tuple[Mapping[str, Any], ...] = ()
    manager_node: str = ""
    manager_status: str = ""
    fencing_mode: str = ""
    lrm_states: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BackupJob:
    """One vzdump job definition, and what it does and does not cover."""

    job_id: str
    enabled: bool
    schedule: str = ""
    comment: str = ""
    storage: str = ""
    node: str = ""
    covers_everything: bool = False
    vmids: tuple[int, ...] = ()
    retention: str = ""

    @property
    def covers(self) -> str:
        """Return a one-line description of the job's coverage."""
        if self.covers_everything:
            return "every guest"
        return f"{len(self.vmids)} guest(s)" if self.vmids else "nothing named"


# --- Nodes --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NodeStatus:
    """One node's own view of itself."""

    node: str
    uptime_seconds: int = 0
    load_average: float = 0.0
    cpu_ratio: float = 0.0
    cpu_count: int = 0
    memory_total_bytes: int = 0
    memory_used_bytes: int = 0
    swap_total_bytes: int = 0
    swap_used_bytes: int = 0
    root_total_bytes: int = 0
    root_used_bytes: int = 0
    kernel_version: str = ""
    proxmox_version: str = ""

    @property
    def memory_ratio(self) -> float:
        """Return memory in use as a proportion of what there is."""
        return _ratio(self.memory_used_bytes, self.memory_total_bytes)

    @property
    def root_filesystem_ratio(self) -> float:
        """Return how full the root filesystem is."""
        return _ratio(self.root_used_bytes, self.root_total_bytes)

    @property
    def swap_ratio(self) -> float:
        """Return how much swap is in use."""
        return _ratio(self.swap_used_bytes, self.swap_total_bytes)


@dataclass(frozen=True, slots=True)
class Datastore:
    """One datastore as a node sees it.

    ``status`` is kept raw. Proxmox reports ``unknown`` for a share whose mount
    is down, and "unknown" is emphatically not "available" — the two datastores
    in that state on the reference cluster are NFS mounts that failed.
    """

    name: str
    node: str
    storage_type: str = ""
    status: str = "available"
    shared: bool = False
    total_bytes: int = 0
    used_bytes: int = 0
    content: tuple[str, ...] = ()

    @property
    def used_ratio(self) -> float:
        """Return how full this datastore is."""
        return _ratio(self.used_bytes, self.total_bytes)

    @property
    def is_available(self) -> bool:
        """Return whether the node can currently reach it."""
        return self.status == "available"


@dataclass(frozen=True, slots=True)
class PhysicalDisk:
    """One disk, with the verdict its own firmware gives."""

    device: str
    size_bytes: int = 0
    model: str = ""
    serial: str = ""
    disk_type: str = ""
    smart_health: str = ""
    wearout: str = ""

    @property
    def smart_passed(self) -> bool:
        """Return whether SMART reports the disk healthy.

        An unknown verdict is not a pass. A disk whose SMART could not be read
        is a disk nobody is watching, and reporting it as healthy is the failure
        this whole wave exists to avoid.
        """
        return self.smart_health.upper() in {"PASSED", "OK"}


@dataclass(frozen=True, slots=True)
class ThinPool:
    """An LVM-thin pool, with its two independent ways of filling up."""

    name: str
    volume_group: str
    size_bytes: int = 0
    data_percent: float = 0.0
    metadata_percent: float = 0.0
    state: str = ""

    @property
    def metadata_critical(self) -> bool:
        """Return whether metadata exhaustion is close enough to stop writes."""
        return self.metadata_percent >= METADATA_CRITICAL_PERCENT

    @property
    def data_critical(self) -> bool:
        """Return whether the pool's data extent is close to full."""
        return self.data_percent >= VOLUME_CRITICAL_PERCENT


@dataclass(frozen=True, slots=True)
class ThinVolume:
    """One guest's own volume inside a thin pool.

    The reading a datastore-level threshold cannot make: ``local-lvm`` at 84%
    while the volume inside it is at 99.6%.
    """

    name: str
    volume_group: str
    size_bytes: int = 0
    data_percent: float = 0.0
    vmid: int = 0

    @property
    def near_full(self) -> bool:
        """Return whether this volume is close to its own ceiling."""
        return self.data_percent >= VOLUME_CRITICAL_PERCENT


@dataclass(frozen=True, slots=True)
class PendingUpdate:
    """One package Proxmox is offering, and whether it matters more than most."""

    package: str
    version: str = ""
    priority: str = ""

    @property
    def is_security(self) -> bool:
        """Return whether the vendor marked this a security update."""
        return self.priority.lower() == "security"

    @property
    def is_kernel(self) -> bool:
        """Return whether this update replaces the running kernel.

        A kernel installed and never booted is the precondition of the reference
        cluster's only total outage: the usual reboot-required signal does not
        fire, and the new kernel's first boot is an unplanned one.
        """
        return "kernel" in self.package


@dataclass(frozen=True, slots=True)
class NetworkInterface:
    """One interface as ``/etc/network/interfaces`` and the kernel agree on it."""

    name: str
    interface_type: str = ""
    active: bool = False
    autostart: bool = False
    address: str = ""
    ports: tuple[str, ...] = ()

    @property
    def is_bridge(self) -> bool:
        """Return whether this is a bridge — the thing everything else depends on."""
        return self.interface_type == "bridge"


@dataclass(frozen=True, slots=True)
class ReplicationJob:
    """One storage replication job and how its last run went."""

    job_id: str
    source: str = ""
    target: str = ""
    guest: int = 0
    enabled: bool = True
    last_sync: int = 0
    duration_seconds: float = 0.0
    fail_count: int = 0
    error: str = ""

    @property
    def failing(self) -> bool:
        """Return whether the job's last run did not succeed."""
        return self.fail_count > 0 or bool(self.error)


# --- Guests -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GuestStatus:
    """One guest, of either kind, in the terms both kinds share.

    ``kind`` stays on the record rather than being flattened away. A container
    and a virtual machine differ in what can be done to them, what their
    configuration means, and how they fail, and an estate that could not express
    "restart every container on this node" would have lost something real.
    """

    vmid: int
    kind: str
    node: str
    status: str
    name: str = ""
    cpus: int = 0
    memory_bytes: int = 0
    memory_used_bytes: int = 0
    disk_bytes: int = 0
    disk_used_bytes: int = 0
    uptime_seconds: int = 0
    lock: str = ""
    ha_managed: bool = False
    template: bool = False
    agent_declared: bool = False

    @property
    def display_name(self) -> str:
        """Return what to call this guest, without inventing a name it does not have."""
        return self.name or f"{self.kind}/{self.vmid}"

    @property
    def is_container(self) -> bool:
        """Return whether this guest shares the host kernel."""
        return self.kind == "lxc"


# --- Tasks and backups --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """One asynchronous operation, identified the way Proxmox identifies it."""

    upid: str
    task_type: str = ""
    status: str = ""
    exit_status: str = ""
    node: str = ""
    user: str = ""
    vmid: int = 0
    started_at: int = 0
    ended_at: int = 0
    #: How many times this record was polled for. Zero for a task read once.
    polls: int = 0

    @property
    def finished(self) -> bool:
        """Return whether the task has stopped running."""
        return self.status.lower() in {"stopped", "ok"} or bool(self.exit_status)

    @property
    def succeeded(self) -> bool:
        """Return whether it finished without error.

        Proxmox says ``OK`` and says everything else in prose, so anything that
        is not ``OK`` is a failure — including the empty string, which is what a
        task that is still running has.
        """
        return self.exit_status.upper() == "OK" or (
            self.status.upper() == "OK" and not self.exit_status
        )

    @property
    def duration_seconds(self) -> int:
        """Return how long it took, or zero while it is still going."""
        return max(self.ended_at - self.started_at, 0) if self.ended_at else 0

    @property
    def summary(self) -> str:
        """Return the one line a report shows."""
        if not self.finished:
            return f"{self.task_type or 'task'} {self.upid} is still running after {self.polls} poll(s)"
        verdict = "succeeded" if self.succeeded else f"failed: {self.exit_status or self.status}"
        return f"{self.task_type or 'task'} {self.upid} {verdict}"


def parse_upid(upid: str) -> dict[str, str]:
    """Return the fields Proxmox packs into a task identifier.

    ``UPID:node:pid:pstart:starttime:type:id:user:`` — eight colon-separated
    fields. Parsed rather than pattern-matched because the ``id`` field is what
    says which guest a backup task was for, and a backup history that could not
    say which guest is a list of times.

    The three numeric fields are **hexadecimal** in the identifier and decimal
    everywhere else Proxmox reports them. Converting here is what stops a caller
    reading ``68943A10`` as a timestamp, which is the kind of mistake that
    produces a backup history dated in the year 3000.
    """
    parts = upid.split(":")
    if len(parts) < 8 or parts[0] != "UPID":
        return {}
    return {
        "node": parts[1],
        "pid": _from_hex(parts[2]),
        "pstart": _from_hex(parts[3]),
        "starttime": _from_hex(parts[4]),
        "type": parts[5],
        "id": parts[6],
        "user": parts[7],
    }


def _from_hex(raw: str) -> str:
    """Return a hexadecimal UPID field as a decimal string, or empty if it is not one."""
    try:
        return str(int(raw, 16))
    except ValueError:
        return ""


def _ratio(used: int, total: int) -> float:
    """Return ``used`` over ``total``, or zero when nothing was reported."""
    return used / total if total else 0.0


__all__ = [
    "METADATA_CRITICAL_PERCENT",
    "VOLUME_CRITICAL_PERCENT",
    "BackupJob",
    "ClusterConfiguration",
    "ClusterStatus",
    "Datastore",
    "GuestStatus",
    "HighAvailabilityState",
    "NetworkInterface",
    "NodeMembership",
    "NodeStatus",
    "PendingUpdate",
    "PhysicalDisk",
    "Reading",
    "ReadingUnavailable",
    "ReplicationJob",
    "TaskRecord",
    "ThinPool",
    "ThinVolume",
    "parse_upid",
]
