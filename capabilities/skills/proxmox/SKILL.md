---
name: cloud_control_plane-proxmox
display_name: Proxmox cluster investigation
description: Quorum before nodes, nodes before guests. A cluster that cannot decide has already answered.
domain: cloud_control_plane
applies_when:
  alert_sources: [proxmox, alertmanager, prometheus]
  tags: [proxmox, hypervisor, cluster, quorum, corosync, fencing, node]
directs_tools:
  - proxmox_cluster_health
  - proxmox_quorum_status
  - proxmox_corosync_links
  - proxmox_ha_state
  - proxmox_clock_skew
requires:
  integrations: [proxmox]
---

# Proxmox cluster investigation

A hypervisor fails from the top down and is investigated the same way. A cluster
without quorum cannot start, stop, migrate or reconfigure anything on any node,
so "the guest will not start" has already been answered before anybody opens the
guest. Reading the guest first is how an investigation spends twenty minutes
describing a symptom.

## Order of operations

1. **Ask the estate and episodic memory first.** `query_service_topology` for
   what depends on this cluster, and `recall_similar_incidents` for whether this
   has happened before. On a small cluster the same three faults recur, and the
   prior occurrence usually names the cause faster than any reading will.
2. **Ask whether the cluster can decide.** `proxmox_quorum_status` returns the
   vote arithmetic, the corosync settings behind it, and the consequences that
   follow. If quorum is lost, `/etc/pve` is read-only, nothing starts or
   migrates, running guests carry on — and every guest symptom is downstream.
3. **Read the margin even when it is quorate.** A margin of zero is not an
   incident and is the most important standing fact about the cluster: the next
   node failure is a cluster-wide outage rather than a single-node one.
4. **Check what the quorum device contributes, not that it exists.** A dead
   `corosync-qdevice` still appears in the membership view with zero votes.
   `quorum_device.contributing` is the field that is not fooled.
5. **Then the links.** `proxmox_corosync_links` counts state changes rather than
   reporting the last one. A link that went down and came back four times is up
   right now, which is why nothing is alerting, and the fault is still there.
6. **Then time.** `proxmox_clock_skew` measures against what corosync tolerates,
   which is about a second. Two nodes a minute apart present as random link
   failures and unmigratable guests, and none of those symptoms mentions time.
7. **Then high availability.** `proxmox_ha_state` says whether a node is being
   fenced or is about to be. A cluster that is unquorate with managed resources
   has watchdogs counting down whatever anybody decides.

## Anti-patterns

**Forcing quorum on a cluster whose other node may still be running.** Lowering
expected votes on a partition that can still write its own storage is how both
halves proceed independently and the shared state is destroyed. Establish that
the other node is *down* — not merely unreachable from here — before anybody
considers it. On a two-node cluster this is the single most expensive plausible
first move, and the two-node skill covers what is safe instead.

**Concluding a cluster is healthy from a monitoring stack hosted inside it.** If
the dashboards live on the guests, a green dashboard means the guests answering
it are up. It says nothing about the node that is not, and it is silent in
exactly the failure it was installed for.

**Reading a link as recovered because it is up.** The state is the last event;
the fault is the transition count.

**Treating "the cluster is quorate" as "the cluster is fine".** Quorate with a
margin of zero, a failed quorum device, and a corosync ring only one node
declares is a cluster that is one event from stopping, and every field that
would say so is separate from the one that says quorate.

## What this is not for

- **Changing anything.** Nothing in this skill's tools writes.
- **Storage, guests or backups.** Those have their own skills, and reaching them
  before this one is the mistake this skill exists to prevent.
- **Readings this integration cannot make.** Failed `systemd` units and bridge
  state are not in the Proxmox API and this integration is deliberately
  forbidden a shell. Reported as **unavailable** they mean nothing is watching —
  not that nothing is wrong.

## Proxmox specifics

- Containers (`lxc`) and virtual machines (`qemu`) are distinct kinds with
  different endpoints and different failure modes. A finding about "guests" that
  is only true of containers will be wrong about the virtual machines.
- A guest may have no name; Proxmox omits the field. Refer to it as `lxc/137`
  rather than inventing one.
- A VMID is reused freely after a guest is destroyed, so history that appears to
  stop is often a guest that was replaced rather than one that was healed.
