"""The detectors that ship, each with its threshold, its reasoning and its remedy.

This is the file the whole feature is for. Everything before it is general
machinery — a detector engine, a signal store, an incident lifecycle — and this
is the set of things somebody who has run a two-node hypervisor cluster would
actually watch for, with numbers chosen for a house rather than for a data
centre.

Three properties hold across every entry, and each is enforced by a test that
runs over the whole set rather than by review.

**Every threshold states why it is that number.** Eighty per cent for a ZFS pool
is not arbitrary: it is where copy-on-write allocation starts having to search
for contiguous space. An operator who knows that can decide whether it applies
to them, and one who does not will either ignore the detector or obey it without
understanding — both worse than not shipping it.

**Every detector states what to do about it.** A finding an operator cannot act
on is an interruption rather than information. The remedy is on the detector,
not in a runbook somewhere, because the moment somebody needs it is the moment
they are looking at the incident.

**Every detector declares what topology it needs.** Two-node behaviour is
detected, never presumed. A three-node cluster shown two-node warnings learns
that warnings do not apply to it; a single-node installation shown cluster
detectors gets an incident about quorum it cannot lose.

**The set is not generic.** Every entry here corresponds either to a condition
that was true in a real two-node cluster at the time this was written, or to a
documented incident in that cluster's own postmortems. That is why it contains
things a generic set would not: a quorum device that is configured and
contributes no votes, a backup job that exists and is disabled, a kernel that is
installed and has never been booted, and failed ``systemd`` units — which were
invisible to every cluster-level and guest-level reading during that cluster's
only total outage, and plain at the unit level the entire time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from config.constants.guardian import (
    BACKUP_DATASTORE_USAGE_PERCENT,
    BACKUP_MAINTENANCE_OVERDUE_DAYS,
    BACKUP_MISSED_SECONDS,
    BACKUP_RETENTION_FLOOR,
    BLIND_SPOT_DETECTOR_ID,
    BRIDGE_DOWN_FIRE_ABOVE,
    CERTIFICATE_EXPIRY_DAYS,
    CLOCK_SKEW_TOLERANCE_SECONDS,
    COROSYNC_LINK_QUALITY_PERCENT,
    DATASTORE_UNKNOWN_SECONDS,
    DATASTORE_USAGE_CRITICAL_PERCENT,
    DATASTORE_USAGE_HIGH_PERCENT,
    FAILED_UNIT_PERSISTENT_SECONDS,
    FAILED_UNITS_FIRE_ABOVE,
    GUARDIAN_SIGNAL_PREFIX,
    GUEST_BACKUP_STALE_DAYS,
    GUEST_CPU_SATURATION_PERCENT,
    GUEST_FILESYSTEM_FULL_PERCENT,
    GUEST_LOCKED_SECONDS,
    GUEST_MEMORY_SATURATION_PERCENT,
    GUEST_RESTART_LOOP_FIRE_ABOVE,
    GUEST_RESTART_LOOP_WINDOW_SECONDS,
    GUEST_SATURATION_SECONDS,
    GUEST_STOPPED_SECONDS,
    GUEST_VOLUME_USAGE_PERCENT,
    KERNEL_UNBOOTED_DAYS,
    NODE_UNREACHABLE_SECONDS,
    PENDING_UPDATES_FIRE_ABOVE,
    PENDING_UPDATES_HOLD_SECONDS,
    QUORUM_MARGIN_FLOOR,
    REBOOT_REQUIRED_DAYS,
    REPLICATION_RPO_MINUTES,
    SECURITY_UPDATES_FIRE_ABOVE,
    SECURITY_UPDATES_HOLD_SECONDS,
    SHIPPED_DETECTOR_FOR_SECONDS,
    SHIPPED_DETECTOR_RECOVERY_SECONDS,
    SIGNAL_ORIGIN_HYPERVISOR,
    SIGNAL_ORIGIN_PUBLISHED,
    STORAGE_FULL_HORIZON_DAYS,
    STORAGE_GROWTH_PERCENT_PER_MINUTE,
    THIN_POOL_METADATA_PERCENT,
    ZFS_CAPACITY_PERCENT,
    ZFS_SCRUB_OVERDUE_DAYS,
)
from config.constants.hypervisor import (
    KIND_PHYSICAL_DISK,
    KIND_REPLICATION_JOB,
    KIND_STORAGE_POOL,
)
from platform.estate.kinds import (
    KIND_BACKUP_JOB,
    KIND_CLUSTER,
    KIND_CONTAINER,
    KIND_DATASTORE,
    KIND_NODE,
    KIND_VIRTUAL_MACHINE,
)
from platform.guardian.topology import ClusterShape, TopologyRequirement
from platform.notifications.models import Severity
from platform.observation.detectors.model import (
    Comparison,
    Condition,
    ConditionKind,
    DetectorDeclaration,
    GroupingKey,
)

#: The two guest kinds, together, because almost every guest detector applies to
#: both and a container is a guest in every sense this file cares about.
GUESTS: tuple[str, ...] = (KIND_CONTAINER, KIND_VIRTUAL_MACHINE)


class SignalOrigin(StrEnum):
    """Where a reading comes from, and therefore what it costs.

    The distinction is load-bearing for NFR-002. A reading this deployment polls
    from the hypervisor API adds a call to a cluster that is already running
    everything else; a reading queried from a metrics system the operator
    already runs adds nothing to the cluster at all.
    """

    #: Polled from the hypervisor API by this deployment.
    HYPERVISOR = SIGNAL_ORIGIN_HYPERVISOR
    #: Queried from a metrics system the operator already runs, through the
    #: observability bridge. Costs the cluster nothing.
    PUBLISHED = SIGNAL_ORIGIN_PUBLISHED


@dataclass(frozen=True, slots=True)
class Reading:
    """One value of the signal a detector reads, as a fixture states it.

    Numeric for almost everything and a state word for the one detector that
    watches a transition. Both are on the same type rather than in two, because
    a fixture table with two shapes is one somebody fills in wrongly.
    """

    value: float = 0.0
    state: str = ""

    def describe(self) -> str:
        """Return how this reading is written in a report."""
        return self.state or f"{self.value:g}"


@dataclass(frozen=True, slots=True)
class ShippedDetector:
    """One detector this deployment ships, and everything an operator needs to judge it.

    The four prose fields are not documentation. ``watches``, ``threshold``,
    ``rationale`` and ``remedy`` are assembled into the declaration's
    description, which is what the console renders beside the detector — so the
    reasoning is in front of somebody at the moment they are deciding whether
    the number is wrong for their cluster, rather than in a file they would have
    to go and find.
    """

    detector_id: str
    name: str
    #: What is being watched, in the operator's terms rather than the signal's.
    watches: str
    #: The threshold, as a sentence with the number in it.
    threshold: str
    #: Why that number and not another one.
    rationale: str
    #: What to do about it when it fires.
    remedy: str
    signal: str
    resource_kinds: tuple[str, ...]
    #: A reading that represents the condition, and one that represents health.
    #: Required rather than defaulted, so a detector cannot be added without
    #: both: SC-002 asks for a firing fixture *and* a healthy fixture per
    #: detector, and the only way to keep that true as detectors are added is to
    #: make the type refuse one without them. Most of these values are taken
    #: from a real cluster's survey rather than invented, which is what makes
    #: them fixtures representing the condition rather than fixtures
    #: representing the threshold.
    firing: Reading
    healthy: Reading
    fire_value: float = 0.0
    clear_value: float = 0.0
    condition_kind: ConditionKind = ConditionKind.THRESHOLD
    comparison: Comparison = Comparison.ABOVE
    to_state: str = ""
    from_state: str = ""
    silent_after_seconds: int = 0
    for_seconds: int = SHIPPED_DETECTOR_FOR_SECONDS
    recovery_seconds: int = SHIPPED_DETECTOR_RECOVERY_SECONDS
    severity: Severity = Severity.HIGH
    grouping_key: GroupingKey = GroupingKey.DETECTOR
    topology: TopologyRequirement = TopologyRequirement.ANY
    origin: SignalOrigin = SignalOrigin.HYPERVISOR
    #: The selector a metrics system is queried with. Required for a published
    #: reading and empty for a polled one, so "who publishes this" is answerable
    #: from the declaration rather than from a wiring diagram.
    matcher: str = ""
    #: True for a structural finding that acknowledgement closes rather than
    #: recovery. Exactly one detector is like this and it says why.
    acknowledged_to_clear: bool = False
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for label, value in (
            ("watches", self.watches),
            ("threshold", self.threshold),
            ("rationale", self.rationale),
            ("remedy", self.remedy),
        ):
            if not value.strip():
                raise ValueError(
                    f"{self.detector_id}: a shipped detector must state its {label}. A "
                    f"threshold with no reason beside it is a number an operator will "
                    f"either ignore or obey without understanding."
                )
        if self.origin is SignalOrigin.PUBLISHED and not self.matcher.strip():
            raise ValueError(
                f"{self.detector_id}: a published reading has to name the selector that "
                f"fetches it, or nothing can say what would publish it"
            )
        if self.origin is SignalOrigin.HYPERVISOR and self.matcher:
            raise ValueError(
                f"{self.detector_id}: a polled reading carries no metrics selector; the "
                f"matcher belongs to readings the operator's own monitoring publishes"
            )

    @property
    def description(self) -> str:
        """Return the paragraph the console shows beside this detector.

        Four sentences in a fixed order — what, when, why, what to do — because
        an operator reading thirty of these needs them to be the same shape.
        """
        return (
            f"Watches {self.watches}. Fires {self.threshold}. "
            f"Why that number: {self.rationale} "
            f"What to do: {self.remedy}"
        )

    def declaration(self, *, enabled: bool = True) -> DetectorDeclaration:
        """Return this detector as the evaluation engine's own declaration.

        Built through the same type an operator's own detector is built through,
        and validated by the same ``__post_init__``: a shipped detector that
        could skip validation would be the one whose clear value sat on the
        wrong side of its firing value.
        """
        return DetectorDeclaration(
            detector_id=self.detector_id,
            name=self.name,
            description=self.description,
            resource_kinds=self.resource_kinds,
            signal=self.signal,
            condition=Condition(
                kind=self.condition_kind,
                comparison=self.comparison,
                fire_value=self.fire_value,
                clear_value=self.clear_value,
                silent_after_seconds=self.silent_after_seconds,
                to_state=self.to_state,
                from_state=self.from_state,
            ),
            for_seconds=self.for_seconds,
            recovery_seconds=self.recovery_seconds,
            severity=self.severity,
            grouping_key=self.grouping_key,
            enabled=enabled,
            capabilities=self.capabilities,
        )

    def activates_on(self, shape: ClusterShape) -> bool:
        """Return whether this detector is worth turning on against ``shape``."""
        return self.topology.activates_on(shape)

    def to_record(self) -> dict[str, object]:
        """Return the document a console page and a ``--json`` listing render."""
        return {
            "detector_id": self.detector_id,
            "name": self.name,
            "watches": self.watches,
            "threshold": self.threshold,
            "rationale": self.rationale,
            "remedy": self.remedy,
            "signal": self.signal,
            "origin": self.origin.value,
            "matcher": self.matcher,
            "resource_kinds": list(self.resource_kinds),
            "severity": self.severity.value,
            "topology": self.topology.value,
            "fire_value": self.fire_value,
            "clear_value": self.clear_value,
            "for_seconds": self.for_seconds,
            "acknowledged_to_clear": self.acknowledged_to_clear,
        }


def _signal(domain: str, reading: str) -> str:
    """Return the namespaced name of one reading the shipped set consumes."""
    return f"{GUARDIAN_SIGNAL_PREFIX}.{domain}.{reading}"


# -- Cluster ------------------------------------------------------------------------
#
# Every one of these needs more than one node to mean anything, and two of them
# need exactly two. Nothing here activates on a single-node installation.

CLUSTER_DETECTORS: tuple[ShippedDetector, ...] = (
    ShippedDetector(
        detector_id="cluster-quorum-lost",
        name="Quorum lost",
        watches="whether the cluster still has enough votes to write its own configuration",
        threshold="as soon as the cluster reports itself not quorate",
        rationale=(
            "there is no partial state and nothing transient about it: without quorum the "
            "cluster filesystem goes read-only, so no guest can be started, stopped, "
            "migrated or reconfigured anywhere. Waiting does not improve the reading."
        ),
        remedy=(
            "restore the missing node or its corosync link. If neither is coming back "
            "soon, an expected-votes change on the survivor makes it writable again — and "
            "is a decision to make deliberately, because it removes the protection quorum "
            "was providing."
        ),
        signal=_signal("cluster", "quorate"),
        resource_kinds=(KIND_CLUSTER,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        condition_kind=ConditionKind.THRESHOLD,
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=60,
        recovery_seconds=300,
        severity=Severity.CRITICAL,
        topology=TopologyRequirement.CLUSTERED,
    ),
    ShippedDetector(
        detector_id="cluster-quorum-margin-zero",
        name="Quorum margin is zero",
        watches="how many votes could be lost before the cluster stops being quorate",
        threshold="when the margin reaches zero — one node loss from unquorate",
        rationale=(
            "a quorate two-node cluster reads as healthy right up to the moment either "
            "node goes away, and then both halves are useless: the survivor cannot write "
            "/etc/pve and the loss was never a surprise. The margin is the reading that "
            "says so while there is still time to fix it."
        ),
        remedy=(
            "add a third vote. A quorum device on any always-on machine in the house is "
            "the usual answer; two_node with wait_for_all is the alternative and has "
            "different failure behaviour. Both are corosync.conf changes with a "
            "config_version bump."
        ),
        signal=_signal("cluster", "quorum_margin"),
        resource_kinds=(KIND_CLUSTER,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=QUORUM_MARGIN_FLOOR,
        clear_value=QUORUM_MARGIN_FLOOR,
        for_seconds=60,
        recovery_seconds=300,
        severity=Severity.CRITICAL,
        topology=TopologyRequirement.TWO_NODE,
    ),
    ShippedDetector(
        detector_id="cluster-quorum-device-not-contributing",
        name="Quorum device configured but not voting",
        watches=("a quorum device that appears in the membership view and contributes no votes"),
        threshold="whenever a device is present and its vote count is zero",
        rationale=(
            "this is the worst shape a quorum device can be in, because everything that "
            "counts devices reports it as configured. A failed qdevice daemon leaves the "
            "entry in the membership list, so the cluster looks like it has three votes "
            "and has two."
        ),
        remedy=(
            "check corosync-qdevice on each node and the qnetd host it talks to. If the "
            "device was never finished, corosync.conf has no device block and the entry "
            "is a leftover — removing it makes the arithmetic honest."
        ),
        signal=_signal("cluster", "quorum_device_votes"),
        resource_kinds=(KIND_CLUSTER,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=300,
        severity=Severity.HIGH,
        topology=TopologyRequirement.CLUSTERED,
    ),
    ShippedDetector(
        detector_id="cluster-corosync-link-degraded",
        name="Corosync link degraded",
        watches="the quality knet reports for each corosync link",
        threshold=f"below {COROSYNC_LINK_QUALITY_PERCENT:g}% link quality",
        rationale=(
            "knet retransmits below this, and retransmission is how token loss starts. A "
            "link at ninety per cent under no load is a link that drops the token the "
            "first time a backup saturates the interface."
        ),
        remedy=(
            "look for the shared interface: on most homelabs corosync rides the same NIC "
            "as guest traffic and backups. A second link on a separate interface is the "
            "fix, and corosync supports it without downtime."
        ),
        signal=_signal("cluster", "link_quality"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=62.0),
        healthy=Reading(value=100.0),
        comparison=Comparison.BELOW,
        fire_value=COROSYNC_LINK_QUALITY_PERCENT,
        clear_value=COROSYNC_LINK_QUALITY_PERCENT,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
        topology=TopologyRequirement.CLUSTERED,
    ),
    ShippedDetector(
        detector_id="cluster-corosync-link-lost",
        name="Corosync link lost",
        watches="whether each configured corosync link is connected at all",
        threshold="as soon as a link reports itself down",
        rationale=(
            "a cluster with one link and that link down is a cluster about to lose "
            "membership; a cluster with two links and one down has lost its redundancy "
            "and nothing else will say so."
        ),
        remedy=(
            "check the interface and the switch port before anything else. If this is the "
            "only link, treat it as an outage in progress rather than a warning."
        ),
        signal=_signal("cluster", "link_connected"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=60,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
        topology=TopologyRequirement.CLUSTERED,
    ),
    ShippedDetector(
        detector_id="cluster-node-unreachable",
        name="Node unreachable",
        watches="whether each cluster node is answering",
        threshold=f"after {NODE_UNREACHABLE_SECONDS}s of no answer",
        rationale=(
            "two minutes is longer than any single corosync membership change and shorter "
            "than a reboot, so it separates a node that is restarting from a node that "
            "has gone."
        ),
        remedy=(
            "if the node is up and only unreachable, the cause is almost always the "
            "network rather than the hypervisor — check the bridge and the interfaces "
            "before the Proxmox services."
        ),
        signal=_signal("cluster", "node_online"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=NODE_UNREACHABLE_SECONDS,
        severity=Severity.CRITICAL,
        grouping_key=GroupingKey.RESOURCE,
        topology=TopologyRequirement.CLUSTERED,
    ),
    ShippedDetector(
        detector_id="cluster-node-clock-skew",
        name="Node clock skew",
        watches="how far each node's clock is from the rest of the cluster",
        threshold=f"beyond {CLOCK_SKEW_TOLERANCE_SECONDS:g}s of skew",
        rationale=(
            "corosync's token timeout is a few seconds and its membership protocol "
            "compares timestamps across nodes, so a second of skew is a meaningful "
            "fraction of the budget rather than a cosmetic difference. Backup schedules "
            "and certificate validity drift with it too."
        ),
        remedy=(
            "check that chrony or systemd-timesyncd is running and reaching a time "
            "source. A node that cannot reach the internet needs one of its neighbours "
            "configured as the source."
        ),
        signal=_signal("cluster", "clock_skew_seconds"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=3.4),
        healthy=Reading(value=0.02),
        fire_value=CLOCK_SKEW_TOLERANCE_SECONDS,
        clear_value=CLOCK_SKEW_TOLERANCE_SECONDS / 2,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
        topology=TopologyRequirement.CLUSTERED,
    ),
    ShippedDetector(
        detector_id="cluster-fencing-occurred",
        name="High-availability fencing occurred",
        watches="whether the cluster fenced a node",
        threshold="on any fencing event",
        rationale=(
            "fencing is the cluster deciding a node was unsafe and cutting it off, which "
            "means guests were killed and restarted elsewhere. It is never routine and it "
            "is never something the operator should learn about from a guest's uptime."
        ),
        remedy=(
            "find out why the node stopped updating its watchdog before restoring HA. A "
            "fence that repeats is worse than the fault it is protecting against."
        ),
        signal=_signal("cluster", "fencing_events"),
        resource_kinds=(KIND_CLUSTER,),
        firing=Reading(value=1.0),
        healthy=Reading(value=0.0),
        fire_value=0.0,
        clear_value=0.0,
        for_seconds=60,
        severity=Severity.CRITICAL,
        topology=TopologyRequirement.CLUSTERED,
    ),
    ShippedDetector(
        detector_id="cluster-version-divergence",
        name="Node running a divergent version",
        watches="whether every node runs the same Proxmox version",
        threshold="whenever more than one version is present in the cluster",
        rationale=(
            "a mixed-version cluster is supported only during an upgrade. Left mixed, "
            "live migration between the two starts failing in ways whose error messages "
            "do not mention the version at all."
        ),
        remedy=(
            "finish the upgrade. If it was stopped deliberately, note that migration "
            "between the divergent nodes should be treated as unavailable until it is "
            "finished."
        ),
        signal=_signal("cluster", "distinct_versions"),
        resource_kinds=(KIND_CLUSTER,),
        firing=Reading(value=2.0),
        healthy=Reading(value=1.0),
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.MEDIUM,
        topology=TopologyRequirement.CLUSTERED,
    ),
    ShippedDetector(
        detector_id="cluster-two-node-quorum-survival",
        name="Two-node cluster would not survive a single node loss",
        watches=("whether a two-node cluster is configured to stay usable when one node goes"),
        threshold="whenever no mitigation is configured — no voting quorum device, no two_node",
        rationale=(
            "with two votes and a quorum of two, losing either node leaves the survivor "
            "unquorate. That is the default and it is almost never what the operator "
            "intended; the reason it goes unnoticed is that the cluster reads as perfectly "
            "healthy while both nodes are up."
        ),
        remedy=(
            "a quorum device on a third always-on machine is the answer that keeps the "
            "protection. two_node with wait_for_all is simpler and trades it for a "
            "different risk, which is worth understanding before choosing it."
        ),
        signal=_signal("cluster", "quorum_survival_configured"),
        resource_kinds=(KIND_CLUSTER,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.HIGH,
        topology=TopologyRequirement.TWO_NODE,
    ),
)


# -- Storage ------------------------------------------------------------------------
#
# LVM-thin first and ZFS second, which is the opposite order to most hypervisor
# documentation and the right one for this hardware: the surveyed cluster has no
# ZFS at all, two thin pools, and three guest volumes near their own ceilings.

STORAGE_DETECTORS: tuple[ShippedDetector, ...] = (
    ShippedDetector(
        detector_id="storage-datastore-usage-high",
        name="Datastore filling",
        watches="how full each datastore is",
        threshold=f"above {DATASTORE_USAGE_HIGH_PERCENT:g}%",
        rationale=(
            "eighty-five leaves room for one large guest's disk to grow without anything "
            "failing, which is the point at which an operator still has choices about "
            "what to delete rather than being forced into the quickest one."
        ),
        remedy=(
            "look for old backups, orphaned volumes and snapshots nobody kept "
            "deliberately before deleting anything a guest is using."
        ),
        signal=_signal("storage", "datastore_used_percent"),
        resource_kinds=(KIND_DATASTORE,),
        firing=Reading(value=96.0),
        healthy=Reading(value=56.0),
        fire_value=DATASTORE_USAGE_HIGH_PERCENT,
        clear_value=DATASTORE_USAGE_HIGH_PERCENT - 5.0,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="storage-datastore-usage-critical",
        name="Datastore nearly full",
        watches="how full each datastore is",
        threshold=f"above {DATASTORE_USAGE_CRITICAL_PERCENT:g}%",
        rationale=(
            "ninety-five is where the next backup or snapshot fails rather than where "
            "space becomes tight. On a thin-provisioned datastore it is also where a "
            "guest write can fail, which the guest experiences as a disk error."
        ),
        remedy=(
            "free space now, and expect the fastest safe win to be pruning backups rather "
            "than moving a guest. Moving a guest needs space at both ends."
        ),
        signal=_signal("storage", "datastore_used_percent"),
        resource_kinds=(KIND_DATASTORE,),
        firing=Reading(value=96.0),
        healthy=Reading(value=84.0),
        fire_value=DATASTORE_USAGE_CRITICAL_PERCENT,
        clear_value=DATASTORE_USAGE_CRITICAL_PERCENT - 5.0,
        for_seconds=300,
        severity=Severity.CRITICAL,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="storage-thin-pool-metadata",
        name="Thin pool metadata filling",
        watches="an LVM thin pool's metadata usage, which is separate from its data usage",
        threshold=f"above {THIN_POOL_METADATA_PERCENT:g}% metadata",
        rationale=(
            "metadata exhaustion is a different and much worse failure than running out "
            "of data space: the pool stops accepting writes while its data percentage "
            "still looks comfortable, and recovering it needs the pool offline. Metadata "
            "does not shrink, so there is no waiting it out."
        ),
        remedy=(
            "extend the metadata volume with lvextend --poolmetadatasize. Doing it while "
            "the pool is still writable is a live operation; doing it afterwards is not."
        ),
        signal=_signal("storage", "thin_pool_metadata_percent"),
        resource_kinds=(KIND_STORAGE_POOL,),
        firing=Reading(value=91.4),
        healthy=Reading(value=31.98),
        fire_value=THIN_POOL_METADATA_PERCENT,
        clear_value=THIN_POOL_METADATA_PERCENT - 5.0,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_lvm_thin_pool_metadata_used_percent",
    ),
    ShippedDetector(
        detector_id="storage-guest-volume-near-full",
        name="Guest volume near its own ceiling",
        watches="how full one guest's thin volume is, as a share of that volume",
        threshold=f"above {GUEST_VOLUME_USAGE_PERCENT:g}% of the volume",
        rationale=(
            "a datastore-level threshold cannot see this. One surveyed cluster had a "
            "datastore reporting 84% while a guest sat at 99.6% of its own volume — the "
            "datastore was fine and the guest was about to stop writing."
        ),
        remedy=(
            "grow the guest's disk, or free space inside the guest and run fstrim so the "
            "thin volume actually shrinks. Deleting inside the guest without discard "
            "changes nothing at this level."
        ),
        signal=_signal("storage", "guest_volume_used_percent"),
        resource_kinds=GUESTS,
        firing=Reading(value=99.6),
        healthy=Reading(value=76.88),
        fire_value=GUEST_VOLUME_USAGE_PERCENT,
        clear_value=GUEST_VOLUME_USAGE_PERCENT - 5.0,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_lvm_thin_volume_used_percent",
    ),
    ShippedDetector(
        detector_id="storage-datastore-status-unknown",
        name="Datastore status unknown",
        watches="a datastore that reports neither available nor full, but unknown",
        threshold=f"after {DATASTORE_UNKNOWN_SECONDS}s reporting unknown",
        rationale=(
            "an unknown datastore is almost always a network share whose mount has gone, "
            "and it is a completely different problem from a full one. Both leave guests "
            "unable to write, and only one of them is fixed by deleting something."
        ),
        remedy=(
            "check the mount on the node rather than the storage. An NFS or SMB share "
            "whose server went away leaves a mount unit failed and the datastore unknown."
        ),
        signal=_signal("storage", "datastore_status_known"),
        resource_kinds=(KIND_DATASTORE,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=DATASTORE_UNKNOWN_SECONDS,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="storage-growth-to-full",
        name="Datastore trending to full",
        watches="how fast a datastore is filling, projected forwards",
        threshold=(f"when the trend reaches full within {STORAGE_FULL_HORIZON_DAYS:g} days"),
        rationale=(
            "fourteen days is roughly how long it takes to free space that is not "
            "obviously free: decide what to delete, find somewhere to put it, and do it "
            "without a maintenance window. A shorter horizon turns this into the "
            "threshold detector it is meant to precede."
        ),
        remedy=(
            "find what is growing before deciding what to delete. Steady growth is "
            "usually one guest's logs or one backup job's retention; a step change is "
            "usually a new guest."
        ),
        signal=_signal("storage", "datastore_used_percent"),
        resource_kinds=(KIND_DATASTORE,),
        firing=Reading(value=0.004),
        healthy=Reading(value=0.0001),
        condition_kind=ConditionKind.RATE_OF_CHANGE,
        fire_value=STORAGE_GROWTH_PERCENT_PER_MINUTE,
        clear_value=STORAGE_GROWTH_PERCENT_PER_MINUTE,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="storage-smart-failure-predicted",
        name="Disk predicting its own failure",
        watches="each physical disk's SMART self-assessment",
        threshold="as soon as a disk reports a failing assessment",
        rationale=(
            "SMART's overall assessment is deliberately conservative — a disk that says "
            "it is failing usually is. The value of the reading is entirely in acting on "
            "it before the disk stops, because afterwards it is a restore rather than a "
            "replacement."
        ),
        remedy=(
            "check what is on it and whether that has a current backup, then replace it. "
            "A disk under a thin pool with no replication takes its guests with it."
        ),
        signal=_signal("storage", "smart_healthy"),
        resource_kinds=(KIND_PHYSICAL_DISK,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=300,
        severity=Severity.CRITICAL,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="storage-zfs-pool-degraded",
        name="ZFS pool degraded or faulted",
        watches="the health each ZFS pool reports, where ZFS is in use",
        threshold="whenever a pool is anything other than online",
        rationale=(
            "degraded means redundancy is already spent, so the next fault is data loss "
            "rather than another warning. Faulted means it is already too late for that "
            "pool and the question is which backup to restore from."
        ),
        remedy=(
            "identify the failed device with zpool status before replacing anything. "
            "Resilvering onto a second failing disk is how a degraded pool becomes a "
            "faulted one."
        ),
        signal=_signal("storage", "zfs_pool_online"),
        resource_kinds=(KIND_STORAGE_POOL,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=300,
        severity=Severity.CRITICAL,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_zfs_zpool_state",
    ),
    ShippedDetector(
        detector_id="storage-zfs-capacity-high",
        name="ZFS pool past its performance threshold",
        watches="how full each ZFS pool is",
        threshold=f"above {ZFS_CAPACITY_PERCENT:g}% capacity",
        rationale=(
            "this is not about running out of space. Eighty per cent is where copy-on-"
            "write allocation starts having to search for contiguous free space, and the "
            "slowdown arrives long before the pool is full — which is why the symptom is "
            "usually reported as 'everything got slow' rather than as a storage problem."
        ),
        remedy=(
            "free space or add a vdev. Deleting snapshots is usually the fastest win, and "
            "on a pool this full it is also the one that frees the most."
        ),
        signal=_signal("storage", "zfs_capacity_percent"),
        resource_kinds=(KIND_STORAGE_POOL,),
        firing=Reading(value=88.0),
        healthy=Reading(value=41.0),
        fire_value=ZFS_CAPACITY_PERCENT,
        clear_value=ZFS_CAPACITY_PERCENT - 5.0,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_zfs_zpool_capacity_percent",
    ),
    ShippedDetector(
        detector_id="storage-zfs-scrub-overdue",
        name="ZFS scrub overdue",
        watches="how long it has been since each ZFS pool was scrubbed",
        threshold=f"more than {ZFS_SCRUB_OVERDUE_DAYS:g} days",
        rationale=(
            "the common schedule is monthly, and five days of slack keeps a scrub that "
            "started late from raising an incident about itself. A pool that is never "
            "scrubbed finds its silent corruption during a resilver, which is the worst "
            "possible moment."
        ),
        remedy=(
            "run zpool scrub. If it is overdue because the timer is not enabled, enabling "
            "it is the actual fix."
        ),
        signal=_signal("storage", "zfs_days_since_scrub"),
        resource_kinds=(KIND_STORAGE_POOL,),
        firing=Reading(value=61.0),
        healthy=Reading(value=12.0),
        fire_value=ZFS_SCRUB_OVERDUE_DAYS,
        clear_value=ZFS_SCRUB_OVERDUE_DAYS,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.LOW,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_zfs_zpool_days_since_scrub",
    ),
)


# -- Guests -------------------------------------------------------------------------

GUEST_DETECTORS: tuple[ShippedDetector, ...] = (
    ShippedDetector(
        detector_id="guest-stopped-unexpectedly",
        name="Guest stopped that should be running",
        watches="a guest the inventory declares should be running and that is not",
        threshold=f"after {GUEST_STOPPED_SECONDS}s stopped",
        rationale=(
            "ten minutes covers a deliberate restart and a migration. Past it the usual "
            "causes are somebody stopping it and not saying so, or something stopping it "
            "and nobody noticing — and the second is the reason this exists."
        ),
        remedy=(
            "read the guest's recent tasks before starting it. A guest that stopped by "
            "itself usually stopped for a reason that will repeat."
        ),
        signal=_signal("guest", "running"),
        resource_kinds=GUESTS,
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=GUEST_STOPPED_SECONDS,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.PARENT,
    ),
    ShippedDetector(
        detector_id="guest-locked-too-long",
        name="Guest locked beyond a threshold",
        watches="how long a guest has been holding a lock",
        threshold=f"after {GUEST_LOCKED_SECONDS // 60} minutes locked",
        rationale=(
            "thirty minutes is longer than a backup of a normal guest and long enough "
            "that a large one is not interrupted. Beyond it the usual cause is a "
            "cancelled task that left the lock behind, and no amount of waiting clears "
            "that."
        ),
        remedy=(
            "confirm no task is genuinely running before unlocking. Clearing a lock while "
            "a backup is still writing produces a corrupt backup and a guest nobody can "
            "trust."
        ),
        signal=_signal("guest", "locked"),
        resource_kinds=GUESTS,
        firing=Reading(value=1.0),
        healthy=Reading(value=0.0),
        fire_value=0.0,
        clear_value=0.0,
        for_seconds=GUEST_LOCKED_SECONDS,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="guest-restart-loop",
        name="Guest restart loop",
        watches="how often a guest has restarted recently",
        threshold=(
            f"more than {GUEST_RESTART_LOOP_FIRE_ABOVE:g} restarts in "
            f"{GUEST_RESTART_LOOP_WINDOW_SECONDS // 3600} hour"
        ),
        rationale=(
            "one restart is an event and two is a coincidence. Three in an hour is a "
            "guest that cannot stay up, and each further restart makes the logs harder to "
            "read rather than the problem clearer."
        ),
        remedy=(
            "stop it rather than letting it keep cycling, then read the last boot's logs. "
            "A loop that is being restarted by HA needs HA turned off for that guest "
            "first."
        ),
        signal=_signal("guest", "restarts"),
        resource_kinds=GUESTS,
        firing=Reading(value=5.0),
        healthy=Reading(value=1.0),
        fire_value=GUEST_RESTART_LOOP_FIRE_ABOVE,
        clear_value=GUEST_RESTART_LOOP_FIRE_ABOVE,
        for_seconds=GUEST_RESTART_LOOP_WINDOW_SECONDS,
        recovery_seconds=GUEST_RESTART_LOOP_WINDOW_SECONDS,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="guest-memory-saturated",
        name="Guest memory saturated",
        watches="a guest's memory usage against what it was given",
        threshold=(
            f"above {GUEST_MEMORY_SATURATION_PERCENT:g}% for "
            f"{GUEST_SATURATION_SECONDS // 60} minutes"
        ),
        rationale=(
            "a guest at ninety per cent for a minute is doing work; one at ninety per "
            "cent for a quarter of an hour needs more memory or has a leak. The duration "
            "is what separates the two, and without it this detector is a nuisance."
        ),
        remedy=(
            "for a container, raising the limit is live. For a VM, check whether the "
            "ballooning minimum is doing the opposite of what was intended before "
            "changing the maximum."
        ),
        signal=_signal("guest", "memory_used_percent"),
        resource_kinds=GUESTS,
        firing=Reading(value=97.0),
        healthy=Reading(value=51.0),
        fire_value=GUEST_MEMORY_SATURATION_PERCENT,
        clear_value=GUEST_MEMORY_SATURATION_PERCENT - 10.0,
        for_seconds=GUEST_SATURATION_SECONDS,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="guest-cpu-saturated",
        name="Guest CPU saturated",
        watches="a guest's CPU usage against the cores it was given",
        threshold=(
            f"above {GUEST_CPU_SATURATION_PERCENT:g}% for {GUEST_SATURATION_SECONDS // 60} minutes"
        ),
        rationale=(
            "the same fifteen-minute duration as memory, for the same reason: a busy "
            "guest and a stuck guest look identical for the first minute and completely "
            "different for the fifteenth."
        ),
        remedy=(
            "check whether the node itself is oversubscribed before giving the guest more "
            "cores. On a homelab it usually is, and adding cores to one guest takes them "
            "from another."
        ),
        signal=_signal("guest", "cpu_used_percent"),
        resource_kinds=GUESTS,
        firing=Reading(value=99.0),
        healthy=Reading(value=63.0),
        fire_value=GUEST_CPU_SATURATION_PERCENT,
        clear_value=GUEST_CPU_SATURATION_PERCENT - 10.0,
        for_seconds=GUEST_SATURATION_SECONDS,
        severity=Severity.LOW,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="guest-filesystem-full",
        name="Guest filesystem full",
        watches="a guest's own filesystem usage, as its agent reports it",
        threshold=f"above {GUEST_FILESYSTEM_FULL_PERCENT:g}%",
        rationale=(
            "higher than the datastore threshold because this is the guest's own view, "
            "and what it precedes is a failure inside the guest rather than across the "
            "datastore. A guest at ninety-five per cent is one log rotation from a "
            "service that will not start."
        ),
        remedy=(
            "free space inside the guest first, then run fstrim if the volume is thin-"
            "provisioned — otherwise the hypervisor's view does not change."
        ),
        signal=_signal("guest", "filesystem_used_percent"),
        resource_kinds=GUESTS,
        firing=Reading(value=98.0),
        healthy=Reading(value=61.0),
        fire_value=GUEST_FILESYSTEM_FULL_PERCENT,
        clear_value=GUEST_FILESYSTEM_FULL_PERCENT - 5.0,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_filesystem_used_percent",
    ),
    ShippedDetector(
        detector_id="guest-no-recent-backup",
        name="Guest with no recent successful backup",
        watches="how long since each guest was last backed up successfully",
        threshold=f"more than {GUEST_BACKUP_STALE_DAYS:g} days",
        rationale=(
            "eight days rather than seven, so a weekly job that ran an hour late is not "
            "an incident. What this catches is not a late job but a guest that has "
            "quietly fallen out of every job's scope."
        ),
        remedy=(
            "check whether the guest is in a job's list at all before investigating the "
            "job. Falling out of scope is far more common than a job failing silently."
        ),
        signal=_signal("guest", "days_since_backup"),
        resource_kinds=GUESTS,
        firing=Reading(value=11.0),
        healthy=Reading(value=1.0),
        fire_value=GUEST_BACKUP_STALE_DAYS,
        clear_value=GUEST_BACKUP_STALE_DAYS,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.DETECTOR,
    ),
)


# -- Backups ------------------------------------------------------------------------
#
# Four of these exist because a real cluster was in exactly this state: a backup
# job that existed and was disabled, fifty-five guests covered by no enabled job,
# retention of two everywhere, and no replication jobs at all under node-local
# storage. Every one of them reads as "backups are configured" to anything that
# counts jobs.

BACKUP_DETECTORS: tuple[ShippedDetector, ...] = (
    ShippedDetector(
        detector_id="backup-job-failed",
        name="Backup job failed",
        watches="the outcome of each backup job's last run",
        threshold="on any failed run",
        rationale=(
            "a failed backup is not noticed by anything else until it is needed, and by "
            "then the gap is however long it has been failing. The reference cluster had "
            "one failing for eleven days."
        ),
        remedy=(
            "read the job's log for the first guest that failed rather than the summary. "
            "One guest failing usually stops the rest of the job."
        ),
        signal=_signal("backup", "job_succeeded"),
        resource_kinds=(KIND_BACKUP_JOB,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=300,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="backup-job-missed",
        name="Backup job did not run when scheduled",
        watches="whether each scheduled backup job actually ran",
        threshold=f"more than {BACKUP_MISSED_SECONDS // 3600} hours past its window",
        rationale=(
            "six hours is long enough that a job queued behind another job is not a "
            "finding, and short enough that a missed nightly window is caught the same "
            "morning. A job that did not run leaves no failure to notice."
        ),
        remedy=(
            "check the schedule and whether the node was up. A job whose node was down at "
            "its window does not catch up by itself."
        ),
        signal=_signal("backup", "hours_past_schedule"),
        resource_kinds=(KIND_BACKUP_JOB,),
        firing=Reading(value=19.0),
        healthy=Reading(value=0.5),
        fire_value=BACKUP_MISSED_SECONDS / 3_600,
        clear_value=BACKUP_MISSED_SECONDS / 3_600,
        for_seconds=1_800,
        recovery_seconds=1_800,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="backup-guest-uncovered",
        name="Guest covered by no enabled backup job",
        watches="whether each guest appears in the scope of at least one enabled job",
        threshold="whenever a guest is in no enabled job's scope",
        rationale=(
            "coverage is the question a job listing cannot answer. A cluster with three "
            "backup jobs configured can still have most of its guests in none of them, "
            "and the surveyed one did: about fifty-five guests, including the entire "
            "observability stack, were covered by nothing enabled."
        ),
        remedy=(
            "add the guest to a job, or decide deliberately that it does not need one and "
            "record that. A guest excluded on purpose and a guest forgotten look "
            "identical from here."
        ),
        signal=_signal("backup", "guest_covered"),
        resource_kinds=GUESTS,
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.CRITICAL,
        grouping_key=GroupingKey.DETECTOR,
    ),
    ShippedDetector(
        detector_id="backup-job-disabled",
        name="Backup job exists but is disabled",
        watches="a configured backup job that is switched off",
        threshold="whenever a job is present and disabled",
        rationale=(
            "a disabled job is the most misleading state a backup can be in, because "
            "every listing shows it. It usually means somebody turned it off for one "
            "night — the surveyed cluster had its primary node's job disabled and its "
            "database job commented 'no automatic policy'."
        ),
        remedy=(
            "either enable it or delete it. A job kept disabled as documentation is a job "
            "that will be counted as coverage by the next person to look."
        ),
        signal=_signal("backup", "job_enabled"),
        resource_kinds=(KIND_BACKUP_JOB,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.DETECTOR,
    ),
    ShippedDetector(
        detector_id="backup-retention-below-floor",
        name="Backup retention below the floor",
        watches="how many copies each backup job keeps",
        threshold=f"fewer than {BACKUP_RETENTION_FLOOR:g} kept copies",
        rationale=(
            "with two copies, discovering that the most recent one is corrupt leaves "
            "exactly one — and that one is usually from the same broken state, because "
            "the two runs are a day apart. Three is the smallest number that survives one "
            "bad backup."
        ),
        remedy=(
            "raise keep-last, or move to a keep-daily and keep-weekly policy so the "
            "copies are not all from the same week."
        ),
        signal=_signal("backup", "retention_depth"),
        resource_kinds=(KIND_BACKUP_JOB,),
        firing=Reading(value=2.0),
        healthy=Reading(value=7.0),
        comparison=Comparison.BELOW,
        fire_value=BACKUP_RETENTION_FLOOR,
        clear_value=BACKUP_RETENTION_FLOOR,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.DETECTOR,
    ),
    ShippedDetector(
        detector_id="backup-verification-failed",
        name="Backup verification failed",
        watches="the result of each backup's verification",
        threshold="on any failed verification",
        rationale=(
            "an unverified backup is a hypothesis. A failed verification is the one "
            "reading that turns a backup somebody was relying on into a backup that does "
            "not exist, and it is far better to learn that now."
        ),
        remedy=(
            "take a fresh backup of that guest before investigating the old one. The "
            "diagnosis can wait; the missing copy cannot."
        ),
        signal=_signal("backup", "verification_passed"),
        resource_kinds=(KIND_BACKUP_JOB,),
        firing=Reading(value=0.0),
        healthy=Reading(value=1.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=300,
        severity=Severity.CRITICAL,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="backup-server-datastore-near-full",
        name="Backup server datastore near full",
        watches="how full the Proxmox Backup Server datastore is",
        threshold=f"above {BACKUP_DATASTORE_USAGE_PERCENT:g}%",
        rationale=(
            "lower than a general datastore threshold, because a backup store that fills "
            "stops taking backups — and what you find that out about is the backup you "
            "needed. There is also nothing running on it that would degrade first and "
            "give a warning."
        ),
        remedy=(
            "run a prune and then a garbage collection, in that order. Pruning alone "
            "removes the index entries and frees nothing until the collection runs."
        ),
        signal=_signal("backup", "datastore_used_percent"),
        resource_kinds=(KIND_DATASTORE,),
        firing=Reading(value=93.0),
        healthy=Reading(value=19.0),
        fire_value=BACKUP_DATASTORE_USAGE_PERCENT,
        clear_value=BACKUP_DATASTORE_USAGE_PERCENT - 5.0,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="backup-garbage-collection-overdue",
        name="Garbage collection or prune overdue",
        watches="how long since the backup store last pruned or collected garbage",
        threshold=f"more than {BACKUP_MAINTENANCE_OVERDUE_DAYS:g} days",
        rationale=(
            "ten days against a weekly schedule. What this catches is not a slow store "
            "but a maintenance job that was never scheduled at all, which is invisible "
            "until the datastore fills."
        ),
        remedy=(
            "schedule both. A prune with no garbage collection behind it frees no space, "
            "which is the usual reason a store fills despite retention looking correct."
        ),
        signal=_signal("backup", "days_since_maintenance"),
        resource_kinds=(KIND_DATASTORE,),
        firing=Reading(value=24.0),
        healthy=Reading(value=3.0),
        fire_value=BACKUP_MAINTENANCE_OVERDUE_DAYS,
        clear_value=BACKUP_MAINTENANCE_OVERDUE_DAYS,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.LOW,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="backup-replication-lag",
        name="Replication behind its recovery-point objective",
        watches="how far behind each replication job's last successful sync is",
        threshold=f"more than {REPLICATION_RPO_MINUTES:g} minutes",
        rationale=(
            "an hour is chosen against the common fifteen-minute schedule: a job that is "
            "four intervals behind has stopped keeping its promise rather than run late. "
            "The lag is also exactly how much data a node loss would cost."
        ),
        remedy=(
            "check the target's free space and the link between the nodes. A replication "
            "job that cannot finish inside its interval falls further behind every run."
        ),
        signal=_signal("backup", "replication_lag_minutes"),
        resource_kinds=(KIND_REPLICATION_JOB,),
        firing=Reading(value=240.0),
        healthy=Reading(value=12.0),
        fire_value=REPLICATION_RPO_MINUTES,
        clear_value=REPLICATION_RPO_MINUTES,
        for_seconds=1_800,
        recovery_seconds=1_800,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="backup-no-replication-jobs",
        name="No replication at all under node-local storage",
        watches=("whether any replication job exists while guests sit on node-local storage"),
        threshold="whenever guests are on node-local storage and no replication job exists",
        rationale=(
            "this is a structural gap rather than a fault, and nothing else reports it. "
            "With guests on node-local LVM-thin and no replication, losing a node means "
            "its guests are unavailable until restored from a backup — and if that node's "
            "backup job is the disabled one, there is nothing to restore from."
        ),
        remedy=(
            "either configure replication for the guests that matter, or move them to "
            "shared storage. Deciding that a node loss is acceptable is also a valid "
            "answer, and worth recording so this stops being raised."
        ),
        signal=_signal("backup", "replication_jobs"),
        resource_kinds=(KIND_CLUSTER,),
        firing=Reading(value=0.0),
        healthy=Reading(value=4.0),
        comparison=Comparison.BELOW,
        fire_value=1.0,
        clear_value=1.0,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.HIGH,
    ),
)


# -- Maintenance --------------------------------------------------------------------

MAINTENANCE_DETECTORS: tuple[ShippedDetector, ...] = (
    ShippedDetector(
        detector_id="maintenance-certificate-expiring",
        name="Certificate expiring",
        watches="how long each certificate has left",
        threshold=f"fewer than {CERTIFICATE_EXPIRY_DAYS:g} days remaining",
        rationale=(
            "three weeks covers a renewal that needs a person, a DNS change and a "
            "weekend. Shorter horizons produce an alert during the week somebody is away, "
            "which is exactly when a certificate expires."
        ),
        remedy=(
            "renew it. If it is the cluster's own certificate, note that the web "
            "interface and the API both stop trusting it at the same instant."
        ),
        signal=_signal("maintenance", "certificate_days_left"),
        resource_kinds=(KIND_NODE, KIND_CLUSTER),
        firing=Reading(value=6.0),
        healthy=Reading(value=74.0),
        comparison=Comparison.BELOW,
        fire_value=CERTIFICATE_EXPIRY_DAYS,
        clear_value=CERTIFICATE_EXPIRY_DAYS,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="maintenance-updates-pending",
        name="Package updates pending",
        watches="how many package updates a node has waiting",
        threshold=(f"more than {PENDING_UPDATES_FIRE_ABOVE:g} pending, held for a day"),
        rationale=(
            "the count alone says little; twenty of them describe a node nobody has "
            "touched in about a month, which is the state in which the eventual upgrade "
            "is large, unfamiliar and done under pressure. The day-long hold is what "
            "keeps a node halfway through an upgrade from raising this about itself."
        ),
        remedy=(
            "update during a window you chose. On a two-node cluster, one node at a time "
            "and only if quorum survives losing one."
        ),
        signal=_signal("maintenance", "pending_updates"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=24.0),
        healthy=Reading(value=3.0),
        fire_value=PENDING_UPDATES_FIRE_ABOVE,
        clear_value=PENDING_UPDATES_FIRE_ABOVE,
        for_seconds=PENDING_UPDATES_HOLD_SECONDS,
        recovery_seconds=PENDING_UPDATES_HOLD_SECONDS,
        severity=Severity.LOW,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="maintenance-security-updates-pending",
        name="Security updates pending",
        watches="how many of a node's pending updates are security updates",
        threshold="one or more pending, held for half a day",
        rationale=(
            "a far lower bar than ordinary updates because the question is different. "
            "One security update outstanding is a decision somebody has made without "
            "noticing they made it, and the half-day hold is only there so that applying "
            "them promptly does not produce an incident on the way."
        ),
        remedy=(
            "apply them. Most security updates on a hypervisor node need no reboot; the "
            "ones that do are a kernel, which the reboot detectors then pick up."
        ),
        signal=_signal("maintenance", "pending_security_updates"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=6.0),
        healthy=Reading(value=0.0),
        fire_value=SECURITY_UPDATES_FIRE_ABOVE,
        clear_value=SECURITY_UPDATES_FIRE_ABOVE,
        for_seconds=SECURITY_UPDATES_HOLD_SECONDS,
        recovery_seconds=SECURITY_UPDATES_HOLD_SECONDS,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="maintenance-reboot-required",
        name="Node requiring a reboot",
        watches="how long a node has been signalling that it needs a reboot",
        threshold=f"more than {REBOOT_REQUIRED_DAYS:g} days signalling it",
        rationale=(
            "a week of evenings in which to schedule one. The signal itself is reliable "
            "when it is present, which is the whole difference between this and the "
            "detector below — where nothing signals anything at all."
        ),
        remedy=(
            "reboot during a window you chose. On two nodes, confirm quorum survives "
            "losing one first — otherwise the reboot takes the cluster with it."
        ),
        signal=_signal("maintenance", "reboot_required_days"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=19.0),
        healthy=Reading(value=0.0),
        fire_value=REBOOT_REQUIRED_DAYS,
        clear_value=REBOOT_REQUIRED_DAYS,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.LOW,
        grouping_key=GroupingKey.RESOURCE,
    ),
    ShippedDetector(
        detector_id="maintenance-kernel-never-booted",
        name="Kernel installed and never booted",
        watches="a kernel present on disk whose first real boot has not happened",
        threshold=f"more than {KERNEL_UNBOOTED_DAYS:g} days installed and unbooted",
        rationale=(
            "this is not a softer version of reboot-required, and the difference is the "
            "point. In the reference cluster's worst incident, /var/run/reboot-required "
            "was absent, the new kernel had been installed for weeks, and its first boot "
            "was an unplanned one during a power cut — at which point the interfaces were "
            "renamed, the bridge could not be built, and both nodes lost networking "
            "together. Installed is not tested, and nothing else signals the gap."
        ),
        remedy=(
            "boot it deliberately, one node at a time, with someone able to reach the "
            "console. That is the whole mitigation: the risk is not the new kernel, it is "
            "that its first boot is unattended."
        ),
        signal=_signal("maintenance", "kernel_unbooted_days"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=34.0),
        healthy=Reading(value=0.0),
        fire_value=KERNEL_UNBOOTED_DAYS,
        clear_value=KERNEL_UNBOOTED_DAYS,
        for_seconds=3_600,
        recovery_seconds=3_600,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_kernel_installed_unbooted_days",
    ),
)


# -- The host layer -----------------------------------------------------------------
#
# The readings that explained an outage nothing else could see. They do not come
# from the hypervisor API — it does not have them, and a hypervisor integration
# that could run shell commands on every node would be a larger authority than
# every remediation capability combined. They arrive as metrics the node
# publishes about itself.

HOST_DETECTORS: tuple[ShippedDetector, ...] = (
    ShippedDetector(
        detector_id="host-systemd-units-failed",
        name="Failed systemd units on a node",
        watches="how many systemd units are in a failed state on each node",
        threshold="one or more failed units",
        rationale=(
            "one is the right threshold because a unit is either supposed to be running "
            "or is not a unit. The reference cluster's only total outage was invisible to "
            "every cluster-level and guest-level reading and plain here the whole time — "
            "and that cluster currently carries nine failed units on one node, including "
            "the very script its own postmortem singled out for failing silently."
        ),
        remedy=(
            "systemctl --failed on the node, and read the oldest one first. Mount units "
            "and network hardening scripts are the two that matter most here, because "
            "both fail without anything else changing."
        ),
        signal=_signal("host", "failed_units"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=9.0),
        healthy=Reading(value=0.0),
        fire_value=FAILED_UNITS_FIRE_ABOVE,
        clear_value=FAILED_UNITS_FIRE_ABOVE,
        severity=Severity.MEDIUM,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_systemd_units_failed",
    ),
    ShippedDetector(
        detector_id="host-unit-failed-persistently",
        name="A unit failed continuously",
        watches="a systemd unit that has stayed failed rather than failed and restarted",
        threshold=f"failed for more than {FAILED_UNIT_PERSISTENT_SECONDS // 3600} hour",
        rationale=(
            "separates a unit that failed and was restarted from one nobody is going to "
            "restart. The second kind is what silent degradation looks like: the machine "
            "keeps working, one thing it was supposed to do is not happening, and no "
            "reading changes again."
        ),
        remedy=(
            "decide whether the unit is still wanted. Half of these on a long-lived "
            "homelab node are services somebody stopped needing and never disabled, and "
            "masking them is the fix."
        ),
        signal=_signal("host", "failed_units"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=9.0),
        healthy=Reading(value=0.0),
        fire_value=FAILED_UNITS_FIRE_ABOVE,
        clear_value=FAILED_UNITS_FIRE_ABOVE,
        for_seconds=FAILED_UNIT_PERSISTENT_SECONDS,
        recovery_seconds=1_800,
        severity=Severity.HIGH,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_systemd_units_failed",
    ),
    ShippedDetector(
        detector_id="host-bridge-down",
        name="Configured bridge absent or down",
        watches="whether each configured network bridge exists and is up",
        threshold="as soon as a configured bridge is absent or down",
        rationale=(
            "there is no degraded state between a bridge being up and nothing on the node "
            "reaching anything: every guest's network is on it, and so is corosync. In "
            "the incident this detector comes from, a kernel upgrade renamed the "
            "interfaces, the interfaces file still named the old ones, ifupdown2 could "
            "not build the bridge, and corosync, the cluster filesystem, keepalived and "
            "the entire monitoring stack failed one after another."
        ),
        remedy=(
            "compare the interface names in /etc/network/interfaces with what the kernel "
            "actually has. If they disagree, that is the whole fault and it needs console "
            "access rather than the network."
        ),
        signal=_signal("host", "bridges_down"),
        resource_kinds=(KIND_NODE,),
        firing=Reading(value=1.0),
        healthy=Reading(value=0.0),
        fire_value=BRIDGE_DOWN_FIRE_ABOVE,
        clear_value=BRIDGE_DOWN_FIRE_ABOVE,
        for_seconds=60,
        severity=Severity.CRITICAL,
        grouping_key=GroupingKey.RESOURCE,
        origin=SignalOrigin.PUBLISHED,
        matcher="node_network_bridge_down",
    ),
)


# -- The blind spot ------------------------------------------------------------------

BLIND_SPOT_DETECTOR: ShippedDetector = ShippedDetector(
    detector_id=BLIND_SPOT_DETECTOR_ID,
    name="Monitoring hosted inside the estate it monitors",
    watches=(
        "whether the observability stack this deployment reads runs inside the estate "
        "it is reading about"
    ),
    threshold="once, on discovering the arrangement",
    rationale=(
        "this is a structural fact rather than a condition that comes and goes, so it "
        "fires once and is cleared by somebody acknowledging it rather than by anything "
        "recovering. It matters because the failure it produces is total: during the "
        "reference cluster's only outage, Prometheus, Alertmanager, Grafana, the "
        "blackbox exporter and Loki were all containers on the node that went down, and "
        "not one alert fired. The outage was found by a person noticing that nothing "
        "responded, and diagnosed with a keyboard plugged into the machine."
    ),
    remedy=(
        "the fix is not to move the stack — a homelab has one set of hardware. It is a "
        "watcher outside the cluster: the external heartbeat this deployment pushes is "
        "exactly that, and configuring a destination for it closes the gap this finding "
        "describes."
    ),
    signal=_signal("estate", "monitoring_hosted_inside"),
    resource_kinds=(KIND_CLUSTER,),
    firing=Reading(state="self_hosted"),
    healthy=Reading(state="external"),
    condition_kind=ConditionKind.STATE_TRANSITION,
    to_state="self_hosted",
    for_seconds=300,
    recovery_seconds=300,
    severity=Severity.HIGH,
    acknowledged_to_clear=True,
)


#: Every detector this deployment ships, in the order an operator reads them:
#: the cluster, then what it stores on, then what runs on it, then whether any
#: of it is recoverable, then the maintenance nobody schedules, then the layer
#: underneath that nothing else looks at.
SHIPPED_DETECTORS: tuple[ShippedDetector, ...] = (
    *CLUSTER_DETECTORS,
    *STORAGE_DETECTORS,
    *GUEST_DETECTORS,
    *BACKUP_DETECTORS,
    *MAINTENANCE_DETECTORS,
    *HOST_DETECTORS,
    BLIND_SPOT_DETECTOR,
)

_BY_ID: dict[str, ShippedDetector] = {
    detector.detector_id: detector for detector in SHIPPED_DETECTORS
}


def detector_by_id(detector_id: str) -> ShippedDetector | None:
    """Return the shipped detector called ``detector_id``, or ``None``."""
    return _BY_ID.get(detector_id)


def detectors_for(shape: ClusterShape) -> tuple[ShippedDetector, ...]:
    """Return the shipped detectors worth activating against ``shape``.

    Gating happens here rather than at evaluation, so a single-node installation
    does not merely fail to fire its cluster detectors — it never declares them,
    and an operator listing what is watching them sees the truth.
    """
    return tuple(detector for detector in SHIPPED_DETECTORS if detector.activates_on(shape))


__all__ = [
    "BACKUP_DETECTORS",
    "BLIND_SPOT_DETECTOR",
    "CLUSTER_DETECTORS",
    "GUEST_DETECTORS",
    "GUESTS",
    "HOST_DETECTORS",
    "MAINTENANCE_DETECTORS",
    "SHIPPED_DETECTORS",
    "STORAGE_DETECTORS",
    "ShippedDetector",
    "SignalOrigin",
    "detector_by_id",
    "detectors_for",
]
