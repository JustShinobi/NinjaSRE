---
name: cloud_control_plane-proxmox-node-host
display_name: Proxmox node host layer
description: The layer beneath the API, where the outages that no cluster reading can see actually live.
domain: cloud_control_plane
applies_when:
  alert_sources: [proxmox, alertmanager]
  tags: [proxmox, node, host, network, bridge, boot, systemd, kernel]
directs_tools:
  - proxmox_cluster_health
  - proxmox_corosync_links
  - proxmox_clock_skew
---

# The Proxmox node host layer

Everything a cluster reading can see assumes the node is answering. The outage
class this skill is about is the one where it is not, and where every
cluster-level and guest-level reading was green until the moment it went silent.

The reference cluster's only total outage lived entirely here: a bridge that
failed to build at boot took corosync, the cluster filesystem and every guest's
network with it, and diagnosing it required physical access because the API it
would have been diagnosed through was on the other side of the bridge.

## What lives below the API

Four things, none of which the Proxmox API publishes and none of which this
integration can read — it is deliberately forbidden a shell:

- **Failed `systemd` units.** A unit that failed at boot and was never noticed.
  `corosync-qdevice` on the reference cluster is in exactly that state, and the
  cluster still lists a quorum device.
- **Bridge presence.** Everything on a Proxmox node depends on `vmbr0`. Nothing
  watches whether it built.
- **Interface naming.** Predictable names change when hardware or firmware
  changes, and an interface that was renamed leaves a bridge configured against a
  port that no longer exists. The configuration is unchanged and correct, and it
  no longer describes the machine.
- **Boot-time reconvergence.** A kernel installed and never booted does not set
  the usual reboot-required signal. Its first real boot will be an unplanned one,
  at the worst moment, with a configuration nobody has tested since.

## How to investigate it from outside

1. **Establish what the cluster can still see.** `proxmox_cluster_health` and
   `proxmox_corosync_links`: a node that is up while corosync is not looks
   different from a node that is off — the API answers for the cluster and
   returns 595 for that node's own reads.
2. **Rule out time.** `proxmox_clock_skew`. Skew presents as link failure, and
   link failure is what this layer's problems present as.
3. **Say what nothing is watching.** Where the readings above come back
   **unavailable**, that means no observation exists — not that the answer is
   negative. Write the difference down explicitly. It is the most common wrong
   conclusion about this platform.
4. **Ask what happened last time, and what goes with it.**
   `recall_similar_incidents` first: a host-layer fault that recurs recurs
   identically, and the previous occurrence names both the cause and the
   physical step that fixed it. Then `query_service_topology` for what the node
   carries, because a host-layer outage takes everything on it at once and the
   blast radius is what decides whether this is a drive to the rack tonight.

## Anti-patterns

**Treating silence as health.** A node that stopped answering stopped producing
readings, and an estate that keeps the last good ones shows a healthy node
indefinitely. Check when each reading was taken, not only what it says.

**Silent degradation as an afterthought.** Treat "a component logged a warning
and exited zero" as a first-class hypothesis, not a last resort. Three of the
reference cluster's incidents were a script or daemon that continued running in a
broken state and never failed: a replication helper that skipped a guest, a
maintenance job that found nothing to do because its path had moved, and a
qdevice daemon that stayed dead. None of them raised anything. The question that
finds them is "what last succeeded", never "what failed".

**Concluding a cluster is healthy from a monitoring stack hosted inside it.** The
dashboards are guests. If the node is gone, so are they, and their last state
before they went is what is on the screen.

**Proposing an edit to the node's network configuration.** Where an operator
manages bridges from a repository, that repository is the writer, and a second
writer is how drift becomes an outage. Where they do not, the change still needs
console access to be safe: a network change applied over the network is one typo
from being unreachable.

## What this is not for

- **Anything that writes.** This layer is where a wrong write is unrecoverable
  without physical access.
- **Guest-level symptoms.** They have their own skill, and reaching for this one
  first attributes an ordinary fault to the hardest layer to check.
