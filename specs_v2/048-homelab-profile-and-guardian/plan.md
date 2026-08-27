# Plan — 047 Homelab Profile and Cluster Guardian

## Technical context

| Concern | Choice |
|---|---|
| Profile | A deployment profile beside the existing ones, one compose file, one command |
| Detector set | Shipped configuration loaded through the config service, versioned, overridable without editing |
| Posture presets | Feature 040 policy documents, named, inspectable, previewable |
| Notification | The existing Telegram, Discord and email sinks |
| Heartbeat | An outbound push on an interval to a channel the operator chooses |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| II — Bounded autonomy | This feature ships the defaults that decide how autonomous a real deployment is. | FR-017 makes propose-only the default. The recommended preset is opt-in, inspectable, and previewed against history before it applies. |
| I — Evidence over assertion | A threshold with no rationale is a guess presented as a standard. | NFR-005 and SC-003: every shipped threshold states why, and a threshold without a rationale fails a test. |
| X — Operator owns their data | This is somebody's home infrastructure. | Nothing leaves the host except the notifications and heartbeat the operator configures. The profile works with no inbound connectivity. |
| XII — Test-first | Thirty detectors is thirty chances for a false positive. | SC-002 requires a firing fixture *and* a healthy fixture per detector, written before the detector. |

## Architecture decisions

**Propose-only is the default, and the recommended preset is one click away.** An
autonomous system that acts on somebody's home infrastructure on the day it is
installed will eventually do something they did not expect, and they will turn it
off. A week of watching it propose builds the confidence that makes the
permissive posture a decision rather than a surprise — and feature 040's preview
turns "what would this do" into a concrete list.

**Two-node behaviour is detected, never presumed.** The user's cluster has two
nodes; the profile must not therefore assume every one does. Topology detection
gates the two-node detectors, so a three-node cluster does not get warnings that
do not apply and a single-node install does not get cluster detectors at all.

**Every threshold carries its reasoning.** Eighty per cent for a ZFS pool is not
arbitrary — it is where copy-on-write allocation starts to fragment badly — and
an operator who knows that can decide whether it applies to them. A shipped
threshold with no stated reason is a number somebody will either ignore or obey
without understanding, and both are bad. The test that fails on a missing
rationale is what keeps this true as detectors are added.

**Notification is for a person, not a rota.** Escalation that repeats indefinitely
assumes somebody else eventually picks it up. Nobody does, in a homelab. So
escalation is bounded and ends, storms are digested into one message, and
resolutions are sent even when the original was never acknowledged — because the
operator was at work.

**The heartbeat is the answer to the hardest failure.** A guardian that has
stopped looks exactly like a cluster with no problems. An outbound heartbeat on
an interval means silence is detectable by the operator's own channel rather than
by the system that is not running.

**Self-awareness is required because the deployment is probably a guest.** Most
homelab operators will run this on the cluster it watches. That is a supported
configuration and a real hazard: the failure it most needs to report is the one
that takes it down. Detecting the situation, saying so, and heartbeating outward
is the honest handling.

## Phases

1. **The profile.** Compose definition, footprint declaration and measurement,
   component set, local model as first-class, backup and restore, upgrade
   preservation, restart resumption.
2. **Topology detection.** Single-node, two-node and multi-node recognition,
   gating the detectors each supports.
3. **Cluster detectors.** Quorum lost, quorum margin zero, corosync degraded and
   lost, node unreachable, clock skew, fencing occurred, version divergence.
4. **Storage detectors.** Datastore usage, thin-pool metadata, ZFS degraded and
   faulted, ZFS capacity threshold, scrub overdue, SMART prediction, growth
   trend to full.
5. **Guest detectors.** Unexpectedly stopped, locked beyond threshold, restart
   loop, sustained saturation, agent-reported filesystem full, no recent backup.
6. **Backup detectors.** Job failed, job missed, guest uncovered, verification
   failed, Proxmox Backup Server near full, garbage collection or prune overdue,
   replication lag beyond objective.
7. **Maintenance detectors.** Certificate expiry, pending updates including
   security, reboot required after kernel update.
8. **Posture and windows.** Propose-only default, the recommended preset,
   preview before apply, backup-window detection offered as freeze windows.
9. **Notification and heartbeat.** Personal channels, message content, resolution
   after the fact, storm digestion, bounded escalation, outbound heartbeat.
10. **Self-awareness.** Detecting that the deployment runs on the managed
    cluster; reporting a problem affecting itself.

## Risks

- **Thirty shipped detectors produce a noisy first week.** Mitigated by
  propose-only defaults, by SC-002's healthy fixture per detector, and by
  digestion — but the real mitigation is that a noisy first week under
  propose-only costs attention rather than action.
- **The declared footprint is optimistic.** Mitigated by NFR-001's soak rather
  than a point measurement, which is where memory growth shows up.
- **Thresholds tuned for the author's cluster.** Mitigated by FR-016's per-resource
  overrides and by stating each rationale, so an operator can see whether the
  reasoning applies to them.
