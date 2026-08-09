"""Every number the shipped detector set fires on, and what the guardian is bounded by.

This module is unusual for ``config/constants/`` in that most of what it holds
is not a bound on the deployment's own appetite — it is a claim about somebody
else's infrastructure. Eighty per cent of a ZFS pool is not a limit this system
imposes; it is where copy-on-write allocation starts to fragment badly, and an
operator who knows that can decide whether it applies to them.

So every threshold here carries the reason for its value, and the reason is
repeated in operator-facing prose on the detector itself, because the moment
somebody needs the reasoning is the moment they are looking at the detector and
deciding whether the number is wrong for their cluster. A shipped threshold with
no stated reason is a number people either ignore or obey without understanding,
and both are worse than no detector.

**Every one of these is overridable.** Per deployment and per resource, through
the configuration service, without editing the shipped set. What is here is the
default an operator starts from, chosen so that the first week is informative
rather than noisy.
"""

from __future__ import annotations

from typing import Final

# --- Cluster shape ---------------------------------------------------------------

CLUSTER_SHAPE_SINGLE_NODE: Final = "single_node"
CLUSTER_SHAPE_TWO_NODE: Final = "two_node"
CLUSTER_SHAPE_MULTI_NODE: Final = "multi_node"

#: The membership size whose quorum arithmetic is its own case. Named rather
#: than written as ``2`` at the comparison, because the whole point of the
#: two-node gate is that the number is a decision.
TWO_NODE_NODE_COUNT: Final[int] = 2

# --- Signal naming ---------------------------------------------------------------

#: Every signal the shipped set reads is named ``guardian.<domain>.<reading>``.
#: Namespaced on purpose: a detector reads *a reading*, not *a metric a
#: particular exporter happens to publish*, so the same detector works whether
#: the number arrived from this deployment's own polling or from a Prometheus
#: the operator already runs.
GUARDIAN_SIGNAL_PREFIX: Final = "guardian"

#: Where a reading comes from, which is what decides whether it costs a call to
#: the cluster. ``hypervisor`` readings are polled by this deployment through the
#: hypervisor API; ``published`` readings are queried from a metrics system the
#: operator already runs and cost the cluster nothing at all.
SIGNAL_ORIGIN_HYPERVISOR: Final = "hypervisor"
SIGNAL_ORIGIN_PUBLISHED: Final = "published"

# --- Cluster thresholds ------------------------------------------------------------

#: Quorum margin: how many votes could be lost before the cluster is unquorate.
#: Zero is one node loss away from a read-only ``/etc/pve``, and it fires
#: immediately because there is nothing transient about it.
QUORUM_MARGIN_FLOOR: Final[float] = 1.0

#: Corosync link quality below which a link is degraded rather than healthy.
#: knet reports a percentage; below eighty a link is retransmitting enough that
#: token loss under load is a matter of time.
COROSYNC_LINK_QUALITY_PERCENT: Final[float] = 80.0

#: How far a node's clock may drift before corosync's own token handling starts
#: to suffer. One second: corosync's default token timeout is a few seconds and
#: the membership protocol compares timestamps across nodes, so a second of skew
#: is a meaningful fraction of the budget rather than a cosmetic difference.
CLOCK_SKEW_TOLERANCE_SECONDS: Final[float] = 1.0

#: How long a node may be unreachable before it is an incident rather than a
#: scrape that missed. Two minutes is longer than any single corosync membership
#: change and shorter than a reboot.
NODE_UNREACHABLE_SECONDS: Final[int] = 120

# --- Storage thresholds ------------------------------------------------------------

#: Datastore usage that is worth saying something about, and the level at which
#: it stops being advice. Eighty-five leaves room for one large guest's disk to
#: grow; ninety-five is the point at which a backup or a snapshot will fail.
DATASTORE_USAGE_HIGH_PERCENT: Final[float] = 85.0
DATASTORE_USAGE_CRITICAL_PERCENT: Final[float] = 95.0

#: LVM thin pool *metadata* usage, which is a completely separate exhaustion
#: from data usage and a much worse one: a thin pool whose metadata is full
#: stops accepting writes while its data percentage still looks comfortable, and
#: recovering it needs the pool offline. Eighty per cent, because metadata does
#: not shrink and the repair is not something anybody does at short notice.
THIN_POOL_METADATA_PERCENT: Final[float] = 80.0

#: A single guest's own thin volume, as a share of that volume rather than of
#: the datastore. Ninety per cent: the guest's filesystem is the thing that
#: breaks, and a datastore-level threshold cannot see it — one cluster surveyed
#: for this wave had a datastore at 84% carrying a guest volume at 99.6%.
GUEST_VOLUME_USAGE_PERCENT: Final[float] = 90.0

#: How long a datastore may report an unknown status before it is a finding.
#: Five minutes distinguishes a share that is down from one that was busy during
#: a single poll.
DATASTORE_UNKNOWN_SECONDS: Final[int] = 300

#: The horizon a growth trend is projected over. Fourteen days is about how long
#: it takes to free space that is not obviously free — decide what to delete,
#: find somewhere to move it, and do it without a maintenance window.
STORAGE_FULL_HORIZON_DAYS: Final[float] = 14.0

#: The projected-full horizon expressed as the rate that reaches it, in percent
#: per minute, from the high threshold. Derived rather than configured so the
#: two cannot drift apart.
STORAGE_GROWTH_PERCENT_PER_MINUTE: Final[float] = (100.0 - DATASTORE_USAGE_HIGH_PERCENT) / (
    STORAGE_FULL_HORIZON_DAYS * 24.0 * 60.0
)

#: ZFS capacity above which allocation performance degrades rather than merely
#: space running out. Eighty per cent is where copy-on-write allocation starts
#: having to search for contiguous space, and the slowdown arrives long before
#: the pool is full.
ZFS_CAPACITY_PERCENT: Final[float] = 80.0

#: How long between scrubs before one is overdue. Thirty-five days: the common
#: schedule is monthly, and five days of slack keeps a scrub that started late
#: from raising an incident about itself.
ZFS_SCRUB_OVERDUE_DAYS: Final[float] = 35.0

# --- Guest thresholds ---------------------------------------------------------------

#: How long a guest may be stopped that the inventory says should be running.
#: Ten minutes covers a deliberate restart and a migration; beyond it somebody
#: stopped it and did not say so, or something stopped it and nobody noticed.
GUEST_STOPPED_SECONDS: Final[int] = 600

#: How long a guest may hold a lock. Thirty minutes is longer than any backup of
#: a normal guest and long enough that a large one is not interrupted; past it
#: the usual cause is a cancelled task that left the lock behind, which no
#: amount of waiting clears.
GUEST_LOCKED_SECONDS: Final[int] = 1_800

#: Restarts inside the window that make a guest a restart loop rather than a
#: guest somebody rebooted. Written as the value the count must *exceed*, so two
#: is "the third restart fires": one restart is an event and two is a
#: coincidence.
GUEST_RESTART_LOOP_FIRE_ABOVE: Final[float] = 2.0
GUEST_RESTART_LOOP_WINDOW_SECONDS: Final[int] = 3_600

#: Sustained memory and CPU saturation, and how long "sustained" is. Ninety per
#: cent for fifteen minutes: a guest at ninety for one minute is doing work, and
#: a guest at ninety for a quarter of an hour is a guest that needs more of
#: something.
GUEST_MEMORY_SATURATION_PERCENT: Final[float] = 90.0
GUEST_CPU_SATURATION_PERCENT: Final[float] = 90.0
GUEST_SATURATION_SECONDS: Final[int] = 900

#: A guest filesystem as its own agent reports it. Ninety-five, higher than the
#: datastore threshold, because this is the guest's own view and the failure it
#: precedes is inside the guest rather than across the datastore.
GUEST_FILESYSTEM_FULL_PERCENT: Final[float] = 95.0

#: How long a guest may go without a successful backup. Eight days rather than
#: seven, so a weekly job that ran an hour late is not an incident.
GUEST_BACKUP_STALE_DAYS: Final[float] = 8.0

# --- Backup thresholds ---------------------------------------------------------------

#: How late a scheduled backup may be before it counts as not having run. Six
#: hours: long enough that a job queued behind another job is not a finding,
#: short enough that a missed nightly window is caught the same morning.
BACKUP_MISSED_SECONDS: Final[int] = 21_600

#: The smallest retention depth worth calling a backup strategy. Three: with two
#: copies, discovering that the most recent one is corrupt leaves exactly one,
#: and that one is usually from the same broken state.
BACKUP_RETENTION_FLOOR: Final[float] = 3.0

#: Proxmox Backup Server datastore usage at which pruning stops being optional.
#: Eighty-five, lower than a general datastore, because a backup store that
#: fills stops taking backups — and the thing you find that out about is the
#: backup you needed.
BACKUP_DATASTORE_USAGE_PERCENT: Final[float] = 85.0

#: How long between garbage collections or prunes before one is overdue. Ten
#: days against the common weekly schedule.
BACKUP_MAINTENANCE_OVERDUE_DAYS: Final[float] = 10.0

#: The recovery-point objective replication is measured against, in minutes.
#: Sixty: a replication job configured to run every fifteen minutes and running
#: an hour behind has stopped keeping its promise.
REPLICATION_RPO_MINUTES: Final[float] = 60.0

# --- Maintenance thresholds -----------------------------------------------------------

#: How long before a certificate expires that somebody should be told. Twenty-one
#: days covers a renewal that needs a person, a DNS change, and a weekend.
CERTIFICATE_EXPIRY_DAYS: Final[float] = 21.0

#: Pending package updates a node may carry before it stops being routine,
#: written as the count to exceed. Twenty is not about risk on its own — it
#: describes a node nobody has touched in about a month, which is the state in
#: which the eventual upgrade is large, unfamiliar, and done under pressure.
PENDING_UPDATES_FIRE_ABOVE: Final[float] = 20.0

#: How long ordinary updates may sit before the count above is worth raising.
#: A whole day, so a node halfway through an upgrade is not a finding.
PENDING_UPDATES_HOLD_SECONDS: Final[int] = 86_400

#: Security updates get a far lower bar, because the question is different: one
#: outstanding is a decision somebody has made without noticing they made it.
SECURITY_UPDATES_FIRE_ABOVE: Final[float] = 0.0

#: And a shorter hold, for the same reason.
SECURITY_UPDATES_HOLD_SECONDS: Final[int] = 43_200

#: How long a node may sit needing a reboot after a kernel update. Seven days is
#: a week of evenings in which to schedule one.
REBOOT_REQUIRED_DAYS: Final[float] = 7.0

#: How long a kernel may be installed and never booted. This is not a softer
#: version of the reboot-required threshold — it is the case where nothing
#: signals anything at all: the package is on disk, ``/var/run/reboot-required``
#: is absent, and the first real boot of that kernel will be an unplanned one
#: during a power cut. Fourteen days, because the risk is not the delay itself
#: but that the delay is invisible.
KERNEL_UNBOOTED_DAYS: Final[float] = 14.0

# --- Host-layer thresholds -------------------------------------------------------------

#: Failed ``systemd`` units on a node that are worth an incident, as the count
#: to exceed — zero, so one failed unit is enough. A unit is either supposed to
#: be running or is not a unit. The only total outage the reference cluster ever
#: had was invisible to every cluster-level and guest-level reading and plain
#: here the whole time.
FAILED_UNITS_FIRE_ABOVE: Final[float] = 0.0

#: How long a unit may stay failed before it is a standing fault rather than a
#: unit that failed and will be restarted. One hour.
FAILED_UNIT_PERSISTENT_SECONDS: Final[int] = 3_600

#: A configured bridge that is absent or down, as the count to exceed. Zero,
#: immediately: every guest's network is on it, and there is no degraded state
#: between "the bridge is up" and "nothing on this node reaches anything".
BRIDGE_DOWN_FIRE_ABOVE: Final[float] = 0.0

# --- The monitoring blind spot -----------------------------------------------------------

#: The blind-spot detector fires once on discovery and is cleared by
#: acknowledgement rather than by recovery, because it is a structural finding
#: about where the monitoring lives rather than a condition that comes and goes.
BLIND_SPOT_DETECTOR_ID: Final = "estate-monitoring-blind-spot"

# --- Detector defaults --------------------------------------------------------------------

#: How long a shipped condition holds before it fires, unless the detector says
#: otherwise. Ten minutes rather than the platform's five: a homelab's polling is
#: sparser, and a first week of false positives is what makes somebody turn the
#: whole thing off.
SHIPPED_DETECTOR_FOR_SECONDS: Final[int] = 600

#: How long a condition must be clear before the incident closes. Longer than the
#: firing duration, so a datastore oscillating around its threshold produces one
#: incident rather than one per crossing.
SHIPPED_DETECTOR_RECOVERY_SECONDS: Final[int] = 1_800

#: The interval the shipped signal sources declare. Five minutes: a homelab is
#: not a trading floor, and the detectors' own durations are measured in tens of
#: minutes, so polling faster would add cluster load that changes no verdict.
SHIPPED_SIGNAL_INTERVAL_SECONDS: Final[int] = 300

# --- Load the guardian adds ------------------------------------------------------------------

#: Calls per minute the whole shipped set may make to the cluster, measured and
#: asserted rather than hoped. Twelve: a homelab cluster's API is a Perl daemon
#: on a machine that is also running everything else, and detection that was
#: itself a noticeable load would be a monitoring system with a self-inflicted
#: incident.
MAX_CLUSTER_CALLS_PER_MINUTE: Final[float] = 12.0

# --- Notification and heartbeat ----------------------------------------------------------------

#: How many findings inside the window become one digest instead of many
#: messages. Three: two notifications a few minutes apart are two things; three
#: is a storm starting, and the operator wants the shape of it rather than the
#: first three items of it.
DIGEST_THRESHOLD: Final[int] = 3

#: The window a digest gathers over. Five minutes is long enough for a node loss
#: to have taken its guests with it and short enough that the digest is still
#: about something happening now.
DIGEST_WINDOW_SECONDS: Final[float] = 300.0

#: Findings one digest names individually before it summarises the rest. Ten
#: fits a phone's notification without a scroll.
MAX_DIGEST_ITEMS: Final[int] = 10

#: How often the guardian pushes a heartbeat outward. Fifteen minutes: a
#: dead-man's switch that only notices after an hour is one that lets an
#: overnight failure run until morning, and one that pushes every minute is a
#: notification budget spent on saying nothing.
HEARTBEAT_INTERVAL_SECONDS: Final[float] = 900.0

#: How many intervals may pass with no heartbeat before the external watcher
#: should conclude the guardian has stopped. Two, so a single missed push during
#: a restart is not an alarm.
HEARTBEAT_MISSED_INTERVALS: Final[int] = 2

#: Escalation rounds before the guardian stops escalating. Two, and then it
#: stops: there is no rota to escalate to in a homelab, so an escalation that
#: repeats indefinitely is a notification the operator learns to filter.
GUARDIAN_ESCALATION_ROUNDS: Final[int] = 2

# --- Posture ------------------------------------------------------------------------------------

#: The named posture presets an operator can inspect and apply. ``propose_only``
#: is what a fresh deployment resolves to with no policy at all; ``recommended``
#: is the one thing this feature is willing to suggest, and it is applied only
#: after a preview against recorded history.
POSTURE_PRESET_PROPOSE_ONLY: Final = "propose_only"
POSTURE_PRESET_RECOMMENDED: Final = "recommended"

POSTURE_PRESETS: Final[tuple[str, ...]] = (
    POSTURE_PRESET_PROPOSE_ONLY,
    POSTURE_PRESET_RECOMMENDED,
)

#: How much recorded history a posture preview is shown against. Seven days is
#: the week the operator spent reading what it would have done.
POSTURE_PREVIEW_DAYS: Final[float] = 7.0

# --- Freeze windows detected from backup schedules -------------------------------------------------

#: How long before a scheduled backup a freeze window opens, and how long after
#: it closes. Thirty minutes each side: a job that starts on time still has a
#: queue in front of it, and an action taken while a backup is running is the
#: one that leaves a guest locked.
FREEZE_WINDOW_LEAD_MINUTES: Final[int] = 30
FREEZE_WINDOW_TRAIL_MINUTES: Final[int] = 30

#: The longest a detected backup window may run before it is offered as a window
#: rather than as a permanent freeze. Six hours: a freeze covering a quarter of
#: every day is a posture decision rather than a window, and offering it as one
#: would be how autonomy is switched off by accident.
MAX_DETECTED_FREEZE_HOURS: Final[float] = 6.0

# --- The declarative control plane -------------------------------------------------------------------

#: Where an operator's own infrastructure repository declares intent this system
#: can read but must never write. A remediation whose correct form is a change
#: to that repository is proposed as such rather than applied to the live host,
#: because a second writer is how drift becomes an outage.
DECLARED_INTENT_READ_ONLY_REASON: Final = (
    "this resource is owned by a declarative control plane; the correct remediation is a "
    "change to that repository, applied through its own path, not a write to the live host"
)

__all__ = [
    "BACKUP_DATASTORE_USAGE_PERCENT",
    "BACKUP_MAINTENANCE_OVERDUE_DAYS",
    "BACKUP_MISSED_SECONDS",
    "BACKUP_RETENTION_FLOOR",
    "BLIND_SPOT_DETECTOR_ID",
    "BRIDGE_DOWN_FIRE_ABOVE",
    "CERTIFICATE_EXPIRY_DAYS",
    "CLOCK_SKEW_TOLERANCE_SECONDS",
    "CLUSTER_SHAPE_MULTI_NODE",
    "CLUSTER_SHAPE_SINGLE_NODE",
    "CLUSTER_SHAPE_TWO_NODE",
    "COROSYNC_LINK_QUALITY_PERCENT",
    "DATASTORE_UNKNOWN_SECONDS",
    "DATASTORE_USAGE_CRITICAL_PERCENT",
    "DATASTORE_USAGE_HIGH_PERCENT",
    "DECLARED_INTENT_READ_ONLY_REASON",
    "DIGEST_THRESHOLD",
    "DIGEST_WINDOW_SECONDS",
    "FAILED_UNITS_FIRE_ABOVE",
    "FAILED_UNIT_PERSISTENT_SECONDS",
    "FREEZE_WINDOW_LEAD_MINUTES",
    "FREEZE_WINDOW_TRAIL_MINUTES",
    "GUARDIAN_ESCALATION_ROUNDS",
    "GUARDIAN_SIGNAL_PREFIX",
    "GUEST_BACKUP_STALE_DAYS",
    "GUEST_CPU_SATURATION_PERCENT",
    "GUEST_FILESYSTEM_FULL_PERCENT",
    "GUEST_LOCKED_SECONDS",
    "GUEST_MEMORY_SATURATION_PERCENT",
    "GUEST_RESTART_LOOP_FIRE_ABOVE",
    "GUEST_RESTART_LOOP_WINDOW_SECONDS",
    "GUEST_SATURATION_SECONDS",
    "GUEST_STOPPED_SECONDS",
    "GUEST_VOLUME_USAGE_PERCENT",
    "HEARTBEAT_INTERVAL_SECONDS",
    "HEARTBEAT_MISSED_INTERVALS",
    "KERNEL_UNBOOTED_DAYS",
    "MAX_CLUSTER_CALLS_PER_MINUTE",
    "MAX_DETECTED_FREEZE_HOURS",
    "MAX_DIGEST_ITEMS",
    "NODE_UNREACHABLE_SECONDS",
    "PENDING_UPDATES_FIRE_ABOVE",
    "PENDING_UPDATES_HOLD_SECONDS",
    "POSTURE_PRESETS",
    "POSTURE_PRESET_PROPOSE_ONLY",
    "POSTURE_PRESET_RECOMMENDED",
    "POSTURE_PREVIEW_DAYS",
    "QUORUM_MARGIN_FLOOR",
    "REBOOT_REQUIRED_DAYS",
    "REPLICATION_RPO_MINUTES",
    "SECURITY_UPDATES_FIRE_ABOVE",
    "SECURITY_UPDATES_HOLD_SECONDS",
    "SHIPPED_DETECTOR_FOR_SECONDS",
    "SHIPPED_DETECTOR_RECOVERY_SECONDS",
    "SHIPPED_SIGNAL_INTERVAL_SECONDS",
    "SIGNAL_ORIGIN_HYPERVISOR",
    "SIGNAL_ORIGIN_PUBLISHED",
    "STORAGE_FULL_HORIZON_DAYS",
    "STORAGE_GROWTH_PERCENT_PER_MINUTE",
    "THIN_POOL_METADATA_PERCENT",
    "TWO_NODE_NODE_COUNT",
    "ZFS_CAPACITY_PERCENT",
    "ZFS_SCRUB_OVERDUE_DAYS",
]
