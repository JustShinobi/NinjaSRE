---
name: cloud_control_plane-proxmox
display_name: Proxmox cluster investigation
description: Quorum before nodes, nodes before guests. A cluster that cannot decide has already answered.
domain: cloud_control_plane
applies_when:
  alert_sources: [proxmox, alertmanager, prometheus]
  tags: [proxmox, hypervisor, cluster, quorum, guest, container, lxc, storage, backup]
directs_tools:
  - proxmox_cluster_health
  - proxmox_storage_pressure
  - proxmox_protection_gaps
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

1. **Ask whether the cluster can decide.** Call `proxmox_cluster_health` first,
   always. It returns the quorum margin — how many votes can be lost before the
   cluster stops deciding — and on a two-node cluster with no quorum device that
   number is zero *while everything is green*. If quorum is already lost,
   `/etc/pve` is read-only, nothing can be started or migrated, and every guest
   symptom below is downstream of that.
2. **Read the margin even when it is quorate.** A margin of zero is not an
   incident and it is the most important standing fact about the cluster: it
   means the next node failure is a cluster-wide outage rather than a
   single-node one. Say so, once, and move on.
3. **Check whether a quorum device is contributing.** A dead `corosync-qdevice`
   still appears in the membership view with zero votes. Anything counting
   configured devices reads that as protection. `quorum_device_contributing` is
   the field that does not.
4. **Then storage, at the right level.** Call `proxmox_storage_pressure` for the
   node in question. Three levels fail independently and only one of them is the
   one people watch — see below.
5. **Then protection, if anything is about recovery.** `proxmox_protection_gaps`
   answers "would this survive losing the node it is on", which is two questions:
   is it in an *enabled* backup job, and does anything replicate.
6. **Only then the guest.** By this point you know whether the cluster could have
   acted, whether the storage under the guest had room, and whether losing it
   would matter. A guest read before those is a guess with a number attached.

## The three storage levels, and why the obvious one is the least useful

- A **datastore** at 84% looks fine.
- The **thin pool** underneath it can be at 96% *metadata*, which stops the pool
  accepting writes entirely while its data percentage is comfortable. These are
  separate numbers with separate failure modes and a threshold on one says
  nothing about the other.
- The guest's **own thin volume** can be at 99.6% while both of the above look
  healthy. That guest is about to see write failures and no datastore-level
  alert will fire.

When a guest reports write errors and its datastore looks fine, you have not
ruled storage out. You have ruled out one of three.

## Reading the result

**A backup job that exists and is disabled is worse than no job.** Every
inventory of "is there a job covering this guest" answers yes. `disabled_jobs`
and `guests_without_an_enabled_job` are the fields that give the real answer.

**No replication with node-local storage means a node loss is unrecoverable
inside the cluster.** Combined with a disabled backup job it means unrecoverable
outright. Neither half reads as urgent alone.

**A datastore reporting `unknown` is not a fill level.** It is Proxmox saying it
cannot reach the share at all — usually a failed NFS or CIFS mount. Treat it as
an unreachable dependency, not as a full disk.

**A guest agent that does not answer is not an unhealthy guest.** Those are
different sentences. Say which one the evidence supports.

## What this is not for

- **Changing anything.** Starting, stopping, migrating, backing up and
  reconfiguring guests are remediations with approval gates and rollback plans.
  Nothing in this skill's tools writes.
- **Anything a declarative control plane owns.** Where the operator manages
  network configuration, bridges or guest definitions from a repository, that
  repository is the writer. Proposing an edit to `/etc/network/interfaces` is
  proposing a second writer, which is how drift becomes an outage.
- **Three readings this integration cannot make.** Failed `systemd` units, bridge
  state and thin-pool metadata as the node sees it are not in the Proxmox API,
  and this integration is deliberately forbidden a shell. If they are reported as
  **unavailable**, that means nothing is watching them — not that nothing is
  wrong. Say the difference out loud; it is the single most common wrong
  conclusion about this platform.

## Proxmox specifics

- Containers (`lxc`) and virtual machines (`qemu`) are distinct kinds with
  different endpoints, different configuration and different failure modes. A
  finding about "guests" that is only true of containers is a finding that will
  be wrong about the two virtual machines.
- A guest may have no name; Proxmox omits the field rather than sending an empty
  one. Refer to it as `lxc/137` rather than inventing a name.
- A VMID is reused freely after a guest is destroyed. Identity here includes the
  guest's creation time, so history that appears to stop is often a guest that
  was replaced rather than one that was healed.
- A kernel installed and never booted does not set `/var/run/reboot-required`.
  Pending updates listing a `proxmox-kernel` package is a planned reboot that has
  not happened, and its first real boot will be an unplanned one.
