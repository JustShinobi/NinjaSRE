---
name: cloud_control_plane-proxmox-storage
display_name: Proxmox storage and ZFS
description: Four levels fail independently and the datastore percentage is the least useful of them.
domain: cloud_control_plane
applies_when:
  alert_sources: [proxmox, alertmanager, prometheus]
  tags: [proxmox, storage, zfs, lvm, thin, disk, smart, capacity]
directs_tools:
  - proxmox_storage_pressure
  - proxmox_zfs_health
  - proxmox_disk_health
  - proxmox_reclaimable_space
  - proxmox_orphaned_volumes
  - proxmox_datastore_availability
---

# Proxmox storage and ZFS

Storage fails at four levels that do not move together, and the one everybody
watches is the least informative of them.

## The four levels

- A **datastore** at 84% looks fine and is the number every dashboard shows.
- The **thin pool** under it has two percentages. Metadata exhaustion stops the
  pool accepting writes entirely while its data figure is comfortable, and a
  threshold on one says nothing about the other.
- Each guest's **own thin volume** can be at 99.6% while both of the above look
  healthy. That guest is about to see write failures and no datastore-level
  alert will fire.
- The **physical drives** underneath report `PASSED` until they do not.

When a guest reports write errors and its datastore looks fine, you have not
ruled storage out. You have ruled out one of four.

## Order of operations

1. **`proxmox_storage_pressure` for the node in question.** It reads all three
   upper levels together and names the largest consumers of each datastore, so a
   percentage comes with what is behind it.
2. **`proxmox_datastore_availability`** whenever a datastore reads oddly. A
   datastore reporting `unknown` is Proxmox saying it cannot reach the share at
   all — a failed NFS or CIFS mount. It is not a fill level and it is not an
   empty datastore, and its fill reads as a comfortable zero.
3. **`proxmox_zfs_health`** where there is ZFS. `ONLINE` answers one question:
   it does not answer capacity, per-device error counts, scrub age or
   fragmentation. A pool at 96% is ONLINE and its writes have already slowed by
   an order of magnitude. Where there is no ZFS the tool says the question is
   inapplicable, which is not a failure and not an empty result.
4. **`proxmox_disk_health`** for the drives. The SMART verdict is the firmware's
   opinion of itself and changes last; the reallocated and pending sector counts
   move months earlier.
5. **`proxmox_reclaimable_space` only once you know what is full**, and read the
   `protects` field of every entry before anything else.
6. **`proxmox_orphaned_volumes`** when a datastore is filling and no guest on it
   has grown. Proxmox keeps a volume when a guest is destroyed with its disks
   retained, and nothing afterwards ever mentions it again.

## Anti-patterns

**Freeing space by deleting the snapshot that is the only recent recovery
point.** The largest reclaimable item usually is. Every entry
`proxmox_reclaimable_space` returns carries what it protects, and the entry
marked as a guest's most recent snapshot is the one whose deletion removes the
only in-place way back. Delete an orphaned volume instead — it protects nothing
and says so.

**Treating a datastore reporting `unknown` as empty rather than as unreachable.**
Every capacity calculation that includes it is wrong in the safe-looking
direction, and every guest whose disk is on it is pinned in place.

**Reading a healthy pool as a pool with room.** Health and capacity are separate
readings and only one of them is in the state word.

**Growing a thin pool because a guest is out of space.** Check which of the four
levels is actually full first. Growing the pool under a guest whose own volume
is at 99.6% changes nothing the guest can see.

**Concluding "the host is fine" from a datastore the node does not declare.**
An incomplete host-side comparison is not a host that is comfortable.

## Before proposing a cause

`recall_similar_incidents` — a datastore that filled once fills the same way
again, and the previous occurrence names what was actually consuming it.
`query_service_topology` for what sits on the datastore, because the blast
radius decides whether this is tonight's work or this month's.

## What this is not for

- **Deleting, pruning, growing or replacing anything.** Nothing here writes, and
  `proxmox_reclaimable_space` is the tool whose output most resembles a delete
  list. It is not one.
- **Whether a backup would restore.** That is the backup skill's question, and a
  file with a size is not a proven restore.
