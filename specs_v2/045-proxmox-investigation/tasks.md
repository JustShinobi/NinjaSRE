# Tasks — 044 Proxmox Investigation Capabilities

## Phase 1 — Cluster, quorum, corosync

- **T-001** Failing test: the quorum tool against a two-node fixture with one
  node down reports expected and current votes, visible nodes, quorum-device
  presence, two-node and wait-for-all settings, and the read-only consequence.
- **T-002** `proxmox_quorum_status` synthesising from cluster status and
  configuration; states survival margin — how many losses the cluster tolerates.
- **T-003** Failing test: against a healthy cluster the same tool reports the
  margin rather than a bare "quorate".
- **T-004** `proxmox_corosync_links`: per-link status, retransmits, latency;
  failing test distinguishing a flapping link from a lost one.
- **T-005** `proxmox_ha_state`: managed resources, current and requested state,
  manager status, fencing imminent or occurred.
- **T-006** `proxmox_clock_skew` across the cluster, with the corosync tolerance
  stated.
- **T-007** Single-node fixture: quorum tools report the question as inapplicable
  rather than answering it wrongly.

## Phase 2 — Storage and ZFS

- **T-008** `proxmox_storage_pressure`: per-datastore usage with largest
  consumers.
- **T-009** Failing test: thin-pool metadata exhaustion reported as distinct from
  data exhaustion, on a fixture with ample data space.
- **T-010** `proxmox_zfs_health`: pool health, per-device state, errors, scrub
  status and age, fragmentation, capacity against the degradation threshold.
- **T-011** Failing test: a healthy pool above the capacity threshold is flagged.
- **T-012** `proxmox_disk_health`: SMART attributes that predict failure, with
  the pool or datastore each disk backs.
- **T-013** `proxmox_reclaimable_space`: amount and what each item protects.
- **T-014** Failing test: no entry may be returned without its protection
  statement — asserted structurally, not by inspection.
- **T-015** `proxmox_orphaned_volumes`: disks belonging to no guest.
- **T-016** `proxmox_datastore_availability`: which datastores each node can see.

## Phase 3 — Guests

- **T-017** `proxmox_guest_start_diagnosis` considering lock, task errors,
  storage availability, node resources, configuration validity, and passthrough
  devices absent on this node.
- **T-018** Failing test: a lock held by a live task and one orphaned by a dead
  task are correctly separated, on fixtures of each, with the task named and
  aged.
- **T-019** `proxmox_guest_pressure` distinguishing host memory pressure, guest
  memory pressure, ballooning, swap and CPU steal.
- **T-020** Failing test: on a fixture where the host storage is full and the
  guest filesystem is not, the tool attributes it to the host.
- **T-021** `proxmox_guest_tasks`: recent history with errors.
- **T-022** `proxmox_migration_feasibility`: can it move, and what prevents it —
  local disks, passthrough, target resources, datastore availability, quorum.

## Phase 4 — Backups

- **T-023** `proxmox_backup_coverage`: per-guest last successful backup with age
  and size; guests covered by no job.
- **T-024** `proxmox_backup_failures` with the provider's own error text.
- **T-025** Failing test: an unverified Proxmox Backup Server backup is reported
  as unproven, not as a backup.
- **T-026** `proxmox_pbs_state`: datastore usage, verification, garbage
  collection, prune results.
- **T-027** `proxmox_replication_lag` reporting recovery-point exposure in time.
- **T-028** Failing test: replication reporting success but not having run for a
  week is reported by exposure, not by last outcome.

## Phase 5 — Skills

- **T-029** Cluster and quorum skill: order of investigation, distinctions,
  supported conclusions.
- **T-030** Two-node cluster skill: survival, the read-only state, replication
  currency, what is safe without quorum.
- **T-031** Storage and ZFS skill.
- **T-032** Guest skill.
- **T-033** Backup and recovery skill.
- **T-034** Anti-patterns in each skill; at minimum the four named in the spec.
- **T-035** Routing to the estate and episodic memory for prior occurrences
  before a cause is proposed.

## Phase 6 — Proofs

- **T-036** Anti-pattern scenarios: one per anti-pattern, in which following the
  plausible first move would have been wrong, asserted.
- **T-037** Failing test: every tool against an unreachable cluster reports what
  it could not determine.
- **T-038** Structural test: every tool declares a read side-effect level.
- **T-039** Bounded-result test: a fixture with a thousand snapshots produces a
  bounded, ranked result that states it was bounded and by what.
- **T-040** Independence test: every tool works without any other having been
  called first.

## Definition of done

- SC-001 through SC-012 each proven by a named test.
- Every tool exercised against healthy, degraded and unreachable fixtures.
- `make verify` green.
