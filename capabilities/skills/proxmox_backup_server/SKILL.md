---
name: cloud_control_plane-proxmox_backup_server
display_name: Proxmox Backup Server investigation
description: A snapshot nobody verified is a file. Check verification and garbage collection, not just usage.
domain: cloud_control_plane
applies_when:
  alert_sources: [proxmox, proxmox_backup_server, alertmanager]
  tags: [backup, restore, snapshot, verification, retention, proxmox]
directs_tools:
  - proxmox_backup_server_datastore_health
requires:
  integrations: [proxmox_backup_server]
---

# Proxmox Backup Server investigation

"There is a backup" is four claims and three of them are usually unchecked. This
skill exists because the one everybody checks — is the datastore full — is the
one least likely to be the reason a restore fails.

## Order of operations

1. **Call `proxmox_backup_server_datastore_health` for the datastore in
   question.** One call answers all four claims.
2. **Read `snapshot_count` first.** Zero means nothing on this store would
   restore, whatever its usage says. This is not rare: a store configured and
   never written to looks healthy by every other measure.
3. **Then `unverified_snapshots`.** Backup Server can re-read a snapshot's chunks
   and confirm they are intact. A snapshot with no verification record has not
   failed — nobody has checked it. A store whose verification job has never run
   is indistinguishable from one whose verification passes, and only one of them
   restores.
4. **Then `garbage_collection_status`.** A store that has not collected reports
   usage about chunks nothing references any more. Its "used" figure is not
   wrong, it is about something else, and capacity planning from it is planning
   from a number that will drop by half the next time collection runs.
5. **Then usage and `estimated_full_date`.** Last, because a store that is 60%
   full of unverified snapshots is in worse shape than one at 90% that verifies.

## Reading the result

- **Unverified is not failed.** Say which. "Twelve snapshots, none verified"
  is a gap in the process; "twelve snapshots, three failed verification" is
  corruption, and they need different responses.
- **Recency matters more than count.** Two hundred snapshots whose newest is
  three weeks old is worse than four whose newest is from last night.
- **A store the token cannot see reports nothing rather than reporting empty.**
  `Datastore.Audit` is granted per datastore path here, so a permission error on
  one store says nothing about the others.

## What this is not for

- **Restoring, pruning or collecting garbage.** All three are operations with
  their own cost and consequences, and none of them is a read.
- **Whether the hypervisor's backup job ran.** That is a Proxmox VE question and
  `proxmox_protection_gaps` answers it. A job that never ran leaves no snapshot
  here, and the absence looks the same as a store nobody configured.
- **What is inside a snapshot.** Listing its contents is a restore, and it costs
  what a restore costs.
