---
name: cloud_control_plane-proxmox-backup
display_name: Proxmox backup and recovery
description: A job that names a guest is not a backup, and a file with a size is not a restore.
domain: cloud_control_plane
applies_when:
  alert_sources: [proxmox, alertmanager]
  tags: [proxmox, backup, restore, replication, retention, recovery]
directs_tools:
  - proxmox_backup_coverage
  - proxmox_backup_failures
  - proxmox_protection_gaps
  - proxmox_replication_lag
---

# Proxmox backup and recovery

Recovery is a different question from health and it is answered by four separate
claims, three of which are usually unchecked. Ask them in this order, because
each one makes the next meaningful.

## Order of operations

1. **Is there an *enabled* job?** `proxmox_backup_coverage` counts against
   enabled jobs only. A job that exists and is switched off satisfies every
   inventory of "is there a backup job for this guest" and protects nothing —
   which is the difference between "fifty-five guests are protected" and the
   truth. `disabled_jobs` and `guests_without_an_enabled_job` are the fields.
2. **How deep does it keep?** Two retained copies and thirty read identically as
   "covered". Two means a corruption noticed on the third day is unrecoverable
   from a guest every dashboard calls protected. `retention_depth` says which.
   A job with no retention rule at all is depth *unknown*, not depth zero: it
   keeps everything until the datastore fills.
3. **Did it actually run?** `proxmox_backup_failures` carries Proxmox's own
   error text, and — separately — the guests whose *every* attempt has failed. A
   guest that failed last night and succeeded the night before has a backup; a
   guest with nothing but failures has never had one, and both are one row in a
   list of failures.
4. **Would it restore?** Where there is a Proxmox Backup Server, its own skill
   covers verification. An unverified snapshot is a file. A store whose
   verification job has never run is indistinguishable from one whose
   verification passes, and only one of them restores.
5. **What would a node loss cost?** `proxmox_replication_lag` reports the
   recovery-point exposure in time. **No replication jobs at all is a finding**,
   not an empty list: with guests on node-local storage a node loss makes them
   unrecoverable inside the cluster, and nothing that iterates over existing jobs
   can see it. Combined with a disabled backup job it means unrecoverable
   outright, and neither half reads as urgent alone.

## Anti-patterns

**Reading a guest as backed up because a job names it.** This is the failure this
whole skill exists for. Check `enabled`, then check that a backup actually
completed, then check its age, then — where there is a Backup Server — check that
it verified. Four claims, and the first one is the only one most reports make.

**Reading a replication job by its last outcome.** A job that reports success and
last ran a week ago reports success. The week is the finding.

**Treating an old backup as no backup, or a recent one as a good one.** Age and
provenness are separate readings. Two hundred snapshots whose newest is three
weeks old is worse than four whose newest is from last night; four unverified is
worse than four verified.

**Deleting a backup to free space without reading what keeps it.** The retention
rule is what decides whether it comes back. `proxmox_reclaimable_space` states
this per entry, and the storage skill covers it.

**Concluding a backup datastore is fine because it has room.** A share reporting
`unknown` reads as having room, and it is a mount that failed.

## Before proposing a cause

`recall_similar_incidents` — a backup job that has failed before usually fails
the same way, and the previous occurrence names the fix. `query_service_topology`
for what the unprotected guests carry, because "no backup" is a different
severity for a DNS resolver than for a media server.

## What this is not for

- **Running a backup, enabling a job, restoring, or pruning.** Nothing here
  writes; all four are remediations with approval gates.
- **Whether the storage is full.** That is the storage skill's question, and the
  backup datastore is one of the four levels it reads.
