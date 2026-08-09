---
name: cloud_control_plane-proxmox-two-node
display_name: Proxmox two-node cluster
description: Two nodes have an even vote count and no majority when one is gone. What survives depends on configuration nobody remembers making.
domain: cloud_control_plane
applies_when:
  alert_sources: [proxmox, alertmanager]
  tags: [proxmox, two-node, quorum, corosync, split-brain, homelab]
directs_tools:
  - proxmox_quorum_status
  - proxmox_corosync_links
  - proxmox_replication_lag
  - proxmox_migration_feasibility
---

# The two-node Proxmox cluster

A two-node cluster is not a small three-node cluster. Two votes with a quorum of
two means losing either node leaves one vote against a requirement of two, and
the survivor is unquorate — so a node failure is a cluster-wide outage rather
than the single-node one everybody plans for. This is the default configuration
and it is the default failure.

Whether it survives depends entirely on settings the operator may not know they
made, which is why every statement below branches on a reading rather than an
assumption.

## What to establish, in order

1. **`proxmox_quorum_status`, before anything else.** It returns `two_node`,
   `wait_for_all`, `last_man_standing`, and what the quorum device contributes.
   Those four decide the answer:
   - **`two_node` set, no quorum device.** Corosync drops the requirement to one
     vote, so the survivor stays quorate — and *both* halves would if they
     stopped seeing each other while both were running. Fencing is the only
     thing preventing two writers, so a cluster with `two_node` set and no
     working fencing is a split brain waiting for a network event.
   - **Neither set, no quorum device.** The margin is zero. The survivor goes
     read-only and stays there until the other node returns or somebody
     intervenes. Nothing is corrupted; nothing can be started either.
   - **A quorum device that contributes.** Three votes, and a node loss leaves
     two. This is the configuration that actually works, and a device that is
     configured while contributing nothing looks identical to it in every
     inventory that counts devices.
2. **`proxmox_corosync_links`.** On two nodes there is one peer, so a single
   flapping link is the entire cluster's membership. A ring only one node
   declares can never come up, and nothing logs an error for it.
3. **`proxmox_replication_lag`.** This is where a two-node cluster is usually
   worst. Guests on node-local storage with no replication mean a node loss is
   unrecoverable inside the cluster — the survivor cannot start them, because it
   does not have their disks. Read the exposure in time, not the last outcome.
4. **`proxmox_migration_feasibility`** before proposing the obvious move. On a
   two-node cluster with node-local storage the answer is usually no, and the
   reason is the disk rather than anything about the guest.

## In the read-only state, what is safe

Everything that reads. The API answers, the guests keep running and keep
serving, and a report can be written. What is not safe is anything that writes
to `/etc/pve`, which includes starting a guest, stopping one, migrating one,
editing a configuration, and creating a backup job.

**Waiting is a legitimate action.** A survivor that is read-only with its guests
running is degraded and stable. Restoring the missing node — or its link — puts
the cluster back with nothing lost. Every faster route trades that for risk.

## Anti-patterns

**Forcing quorum while the other node may still be running.** `pvecm expected 1`
on a partition that can still write its own storage is how both halves proceed
and the shared state is destroyed. "I cannot reach it" is not "it is down": a
link failure produces exactly the same view from both sides, and both sides
would be equally entitled to conclude it. Establish the other node is off —
physically, or by something outside the cluster — first.

**Restarting corosync to "re-establish" membership.** On two nodes this removes
the only vote the survivor has and can turn a recoverable outage into a fenced
one.

**Reading the survivor's guests as healthy because they are running.** They are
running and unmanaged: nothing will restart them if they stop, and nothing can.

**Trusting a quorum device that is listed.** Check the contribution.

## Before proposing a cause

Ask `recall_similar_incidents`. A two-node homelab cluster fails the same three
ways, and the previous occurrence usually names both the cause and what actually
fixed it. `query_service_topology` says what else goes down with it, which is
the part that decides urgency.
