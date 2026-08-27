# Feature 045 — Proxmox Investigation Capabilities

- **Wave:** 11 — Proxmox and the homelab
- **Branch:** `feat/045-proxmox-investigation`
- **Status:** Draft
- **Depends on:** 003, 044

## Summary

The tools and the methodology: what to ask a Proxmox cluster, and in what order,
across the four domains that account for nearly everything that goes wrong in a
small cluster — quorum and corosync, storage and ZFS, guests, and backups.

A client that can read an endpoint is not an investigation. The read tools here
answer questions rather than wrapping paths — "is this cluster quorate and why
not" rather than "GET /cluster/status" — and the skills encode the order an
experienced operator would ask them in, including the several cases where the
obvious first question is the wrong one.

The two-node case gets particular attention because it is the user's case and
because it is genuinely different. A two-node cluster has an even vote count and
therefore no majority when one node is gone; whether it survives a node failure
depends entirely on configuration the operator may not know they made. That is
not an exotic edge case in a homelab. It is the default failure.

## User scenarios

### Primary story

A node stops answering. The investigation establishes, in order: that the cluster
has lost quorum and what its vote configuration is; that the surviving node's
`pmxcfs` is therefore read-only, which is why nothing can be started; which
guests were on the lost node and whether they are recoverable on the survivor;
whether replication was current enough that starting them elsewhere would lose
data; and whether high availability is about to fence something. The report
distinguishes what is broken from what is a consequence of what is broken.

A different morning, a container will not start. The investigation finds it is
not the container: the thin pool backing it has exhausted its metadata space,
three other guests are one write away from the same failure, and the reason is a
snapshot that was never pruned.

### Acceptance scenarios

1. **Given** a cluster that has lost quorum, **when** the quorum tool is called,
   **then** it reports the expected and current votes, which nodes are visible,
   whether a quorum device is configured, whether two-node mode or wait-for-all
   is set, and the consequence — that the configuration filesystem is read-only.
2. **Given** a healthy cluster, **when** the same tool is called, **then** it
   reports quorate with its margin, and says how many nodes may be lost before
   quorum is.
3. **Given** corosync link trouble, **when** the link tool is called, **then** it
   reports per-link status, retransmits and knet latency, and distinguishes a
   flapping link from a lost one.
4. **Given** a datastore under pressure, **when** the storage tool is called,
   **then** it reports usage, the largest consumers, and — for thin pools —
   metadata usage separately from data usage.
5. **Given** a ZFS pool, **when** the pool tool is called, **then** it reports
   health, per-device state, errors, scrub status and age, fragmentation, and
   whether capacity is above the level at which performance degrades.
6. **Given** snapshots accumulating, **when** the reclaim tool is called, **then**
   it reports what is reclaimable, how much each item would return, and what each
   is protecting — never a bare list of deletable things.
7. **Given** a guest that will not start, **when** the guest tool is called,
   **then** it reports its lock state, its last tasks with their errors, its
   configured versus available resources, its storage availability, and the most
   likely cause among them.
8. **Given** a guest that is locked, **when** it is examined, **then** the tool
   distinguishes a lock held by a running task from one orphaned by a task that
   died, because only the second is safe to clear.
9. **Given** a guest under memory pressure, **when** it is examined, **then** the
   tool distinguishes host pressure, guest pressure, ballooning and swap, and
   says which one it is.
10. **Given** backup jobs, **when** the backup tool is called, **then** it reports
    per-guest last successful backup, guests covered by no job, jobs that failed,
    and — where Proxmox Backup Server is present — verification and pruning
    state.
11. **Given** replication between nodes, **when** it is examined, **then** it
    reports per-job last success, lag, and the data that would be lost if the
    source were lost now.
12. **Given** any of these tools, **when** the cluster is unreachable or
    unquorate, **then** the tool reports what it could not determine and why,
    rather than an empty or misleading answer.

### Edge cases

- A single-node installation, where quorum questions are meaningless.
- A cluster where a node is up but corosync is not.
- A ZFS pool that is healthy but 96% full.
- A thin pool with plenty of data space and no metadata space.
- A guest locked by a backup that is genuinely still running.
- A guest whose disk is on a datastore that is not currently available.
- A guest with a passthrough device that only exists on one node.
- Backups that succeed but whose verification fails.
- Replication that reports success but has not run for a week.
- A node whose clock is far enough out to break corosync.

## Requirements

### Functional

**Cluster, quorum and corosync**

- **FR-001** A tool MUST report quorum state as an answer, not a dump: quorate or
  not, expected and current votes, visible nodes, and the margin.
- **FR-002** It MUST report the quorum configuration that determines survival —
  quorum device presence and health, two-node mode, wait-for-all, last-man-standing
  — and MUST state how many node losses the cluster survives.
- **FR-002a** A quorum device MUST be reported by its **contribution**, not by its
  presence. A device that appears in the membership view, contributes zero votes,
  and whose daemon has failed MUST be reported as *configured but not
  contributing* — never as "a quorum device is configured". This is the exact
  state of the reference cluster: `corosync-qdevice.service` is failed on one
  node, `corosync.conf` carries no `device {}` block, and the membership view
  still lists a `Qdevice` row.
- **FR-003** It MUST state the consequence of lost quorum explicitly: the
  configuration filesystem is read-only, guests cannot be started or migrated,
  and running guests continue.
- **FR-004** A tool MUST report corosync link health per link, including
  retransmits and latency, and MUST distinguish flapping from loss.
- **FR-005** A tool MUST report high-availability state: which resources are
  managed, their current and requested state, the manager's status, and whether
  fencing is imminent or has occurred.
- **FR-006** A tool MUST report node clock skew across the cluster, because
  corosync tolerates very little of it.

**Storage and ZFS**

- **FR-007** A tool MUST report per-datastore usage with the largest consumers,
  and MUST report thin-pool metadata usage separately from data usage.
- **FR-007a** A tool MUST report **per-guest thin volume fill** as a question
  distinct from datastore usage. In the reference cluster the datastore reads 84%
  while one guest's own volume is at 99.60% and two more are above 93% — a
  datastore threshold cannot see any of them, and the guests concerned are the
  two with prior stall postmortems.
- **FR-007b** A tool MUST report a datastore whose provider status is `unknown` —
  typically a network share that is down — as distinct from one that is full and
  from one that is healthy. Two such datastores exist in the reference cluster.
- **FR-008** Where ZFS is present, a tool MUST report pool health, per-device
  state, error counts, scrub status and age, fragmentation, and capacity against
  the threshold at which performance degrades. Where ZFS is absent — as it is on
  both reference nodes — the tool MUST report the question as inapplicable rather
  than as a failure or an empty result.
- **FR-009** A tool MUST report physical disk health including SMART attributes
  that predict failure, and MUST say which pool or datastore each disk backs.
- **FR-010** A tool MUST report reclaimable space with, for each item, the amount
  it would return and what it is protecting — a snapshot's age and its guest, a
  backup's retention rule, an orphaned disk's former owner.
- **FR-011** A tool MUST identify orphaned volumes: disks belonging to no guest.
- **FR-012** A tool MUST report which datastores are available from which nodes,
  because a guest cannot move to a node that cannot see its disk.

**Guests**

- **FR-013** A tool MUST diagnose a guest that will not start, considering: lock
  state, last task errors, storage availability, resource availability on the
  node, configuration validity, and passthrough devices absent on this node.
- **FR-014** A tool MUST distinguish a lock held by a live task from one orphaned
  by a dead task, and MUST name the task and its age.
- **FR-015** A tool MUST report guest resource pressure, distinguishing host
  memory pressure, guest memory pressure, ballooning, swap and CPU steal.
- **FR-016** Where a guest agent is present, a tool MUST report the guest's own
  filesystem usage, and MUST distinguish "the agent says the disk is full" from
  "the host's storage is full" — a distinction that changes the remedy entirely.
- **FR-017** A tool MUST report a guest's recent task history with errors.
- **FR-018** A tool MUST report whether a guest can be migrated and what would
  prevent it: local disks, passthrough devices, insufficient resources on the
  target, datastore availability, or lack of quorum.

**Backups**

- **FR-019** A tool MUST report per-guest backup coverage: last successful backup,
  its age, its size, and guests covered by no job at all.
- **FR-019a** Coverage MUST be computed against **enabled** jobs only. A disabled
  job that names a guest provides no coverage, and reporting it as coverage is
  the difference between "55 guests are protected" and the truth. The reference
  cluster's whole-node job is disabled and its guests read as covered to anything
  that counts job membership.
- **FR-019b** A tool MUST report retention depth per job alongside coverage. Two
  retained copies is a materially different position from thirty, and coverage
  without depth reads the same for both.
- **FR-020** A tool MUST report failed backup jobs with the provider's own error.
- **FR-021** Where Proxmox Backup Server is present, a tool MUST report datastore
  usage, verification outcomes, garbage-collection state and prune results, and
  MUST treat an unverified backup as unproven rather than as a backup.
- **FR-022** A tool MUST report replication job state per job: last success, lag,
  and the recovery-point exposure if the source were lost now.
- **FR-022a** **No replication jobs at all** MUST be reported as a finding in its
  own right when guests sit on node-local storage, not as an empty list. In that
  configuration a node loss makes its guests unrecoverable within the cluster,
  which is the single most consequential fact about the reference cluster's data
  posture and is invisible to anything that iterates over existing jobs.

**Skills**

- **FR-023** A skill MUST exist per domain, encoding the order of investigation,
  the distinctions that matter, and the conclusions each reading supports.
- **FR-024** A skill MUST exist for the two-node cluster specifically, covering
  quorum survival, the read-only consequence, replication currency, and what is
  safe to do without quorum.
- **FR-025** Skills MUST state their anti-patterns: the plausible first move that
  is wrong. At minimum — clearing a lock whose task is alive; forcing quorum on a
  cluster whose other node may still be running; freeing space by deleting the
  snapshot that is the only recent recovery point; restarting a guest whose
  problem is the host; **reading a guest as backed up because a job names it**;
  **concluding a cluster is healthy from a monitoring stack hosted inside it**;
  and **treating a datastore reporting `unknown` as empty rather than as
  unreachable**.
- **FR-025a** A skill MUST exist for the node host layer beneath the Proxmox API:
  failed `systemd` units, bridge presence, interface naming, and boot-time
  reconvergence. The reference cluster's only total outage lived entirely in that
  layer, was invisible to every cluster-level and guest-level reading, and
  required physical access to diagnose.
- **FR-025b** Skills MUST treat **silent degradation** as a first-class
  hypothesis: a component that logged a warning and exited zero. Three of the
  reference cluster's incidents involved a script or daemon that continued
  running in a broken state without ever failing.
- **FR-026** Skills MUST route to the estate and to episodic memory for prior
  occurrences before proposing a cause.

### Non-functional

- **NFR-001** Every tool MUST be read-only, declared and asserted.
- **NFR-002** Every tool MUST return a bounded result; a cluster with a thousand
  snapshots must not produce a thousand-entry payload.
- **NFR-003** Every tool MUST state what it could not determine, rather than
  omitting it.
- **NFR-004** Every tool MUST be exercised against recorded fixtures covering the
  healthy, the degraded and the unreachable case.
- **NFR-005** Tools MUST be usable individually; no tool may depend on another
  having been called first.

## Success criteria

- **SC-001** The quorum tool, against a two-node cluster with one node down,
  reports votes, configuration, survival margin and the read-only consequence.
- **SC-002** The same tool against a healthy cluster reports the margin and how
  many losses it survives.
- **SC-003** The storage tool reports thin-pool metadata exhaustion as distinct
  from data exhaustion, on a fixture where data space is ample.
- **SC-004** The ZFS tool flags a healthy pool above the capacity threshold.
- **SC-005** The reclaim tool never lists an item without saying what it protects.
- **SC-006** The lock tool correctly separates a live-task lock from an orphaned
  one, on fixtures of each.
- **SC-007** The guest tool, on a fixture where the host is full and the guest is
  not, attributes it to the host.
- **SC-008** The backup tool reports an unverified backup as unproven.
- **SC-009** The replication tool reports recovery-point exposure in time.
- **SC-010** Every tool, against an unreachable cluster, reports what it could not
  determine.
- **SC-011** Each skill's anti-patterns are asserted by a scenario in which
  following the plausible first move would have been wrong.
- **SC-012** Every tool is read-only, asserted structurally.

## Out of scope

- Any write — feature 046.
- Detectors that fire on these readings — feature 048.
- Ceph.
