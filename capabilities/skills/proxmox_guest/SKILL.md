---
name: cloud_control_plane-proxmox-guest
display_name: Proxmox guest investigation
description: Every distinction that changes the remedy is a pair of readings that look alike.
domain: cloud_control_plane
applies_when:
  alert_sources: [proxmox, alertmanager]
  tags: [proxmox, guest, lxc, qemu, container, lock, memory, migration]
directs_tools:
  - proxmox_guest_start_diagnosis
  - proxmox_guest_pressure
  - proxmox_guest_tasks
  - proxmox_migration_feasibility
---

# Proxmox guest investigation

A guest is the last thing to read, not the first. By the time you open one you
should already know whether the cluster could have acted, and whether the storage
underneath it had room — because both of those produce guest symptoms and neither
is fixed inside the guest.

Everything below is a pair of readings that look alike and have different
remedies.

## A guest that will not start

Call `proxmox_guest_start_diagnosis`. It returns six causes and which one
invalidates the others, in this order:

1. **No quorum.** Nothing starts anywhere. Every finding below it is true and
   downstream.
2. **A lock.** The critical distinction: a lock held by a task that is *still
   running* and one left behind by a task that *died* are the same field with
   opposite correct actions. The tool names the task and its age.
3. **A datastore this node cannot reach.** The guest's disk may be on a share
   whose mount failed, and nothing about the guest says so.
4. **A passthrough device.** `hostpci` and `usb` entries are hardware in one
   machine. A guest that starts on one node and not the other is usually this.
5. **The node's free memory** against what the guest is configured for.
6. **The last failed task**, in Proxmox's own words. Read the words: they name
   the next thing to look at, and a paraphrase does not.

## A guest under pressure

Call `proxmox_guest_pressure`. Two attributions it makes explicitly:

- **Memory.** Host pressure and guest pressure both produce a stalling guest.
  Adding memory to a guest on a swapping host makes the host worse; adding
  memory to a host whose guest is at its own ceiling changes nothing.
- **Storage.** "The agent says the disk is full" and "the host's storage is
  full" are different sentences and only one is fixed inside the guest.

Two readings it names and cannot make: **ballooning** is reported as configured
rather than as currently reclaimed, and **CPU steal** is not in the Proxmox API
at all. An investigation with no steal reading attributes a stolen CPU to the
guest's own load every time, which is why the tool says so out loud.

## A guest that should move

Call `proxmox_migration_feasibility` *before* proposing it. On a small cluster
the answer is usually no, for a reason nobody checked: a node-local disk, a
datastore the target does not declare, a passthrough device, a target with less
free memory than the guest is configured for, or no quorum.

## Anti-patterns

**Clearing a lock whose task is alive.** It is the most tempting single action on
this page and it corrupts whatever the task was doing — usually a backup, which
is discovered months later when the restore is attempted. `lock.orphaned` is the
field. If it is false, wait.

**Restarting a guest whose problem is the host.** A guest killed by host memory
pressure comes back and is killed again, and the restart destroys the evidence of
why. Attribute first.

**Reading an absent guest agent as an unhealthy guest.** Those are different
sentences and only one is about the guest. A container has no agent at all.

**Treating a guest as gone because its node is down.** Proxmox keeps the row and
blanks what it cannot see: the reading is stale, not absent.

**Concluding from a name.** A guest may have no name — Proxmox omits the field
rather than sending an empty one — and a VMID is reused freely after a guest is
destroyed. History that appears to stop is often a guest that was replaced.

## Before proposing a cause

`recall_similar_incidents` for this guest and this failure shape;
`query_service_topology` for what depends on it. A guest that has stalled twice
before has a cause somebody already found, and the prior postmortem is faster
than any reading here.
