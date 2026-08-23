# Tasks — 045 Proxmox Remediation Capabilities

## Phase 1 — Risk table and declaration

- **T-001** Write the risk table: every planned action, its class, and the
  reversibility, data-loss, availability and blast-radius reasoning.
- **T-002** Declaration contract requiring risk class, preconditions, rollback
  plan or explicit absence, verification signals, settle period and required
  privileges.
- **T-003** Failing test: an action missing any of those fails registration, not
  runtime.
- **T-004** Failing test: the risk table and the registered capabilities agree
  exactly; a divergence fails the suite.
- **T-005** Failing test: an action that can lose data is the highest class
  regardless of size.

## Phase 2 — Preconditions and prohibitions

- **T-006** Precondition evaluation against fresh readings immediately before
  execution.
- **T-007** Failing test: a target that changed after proposal — a migrated
  guest, a newly taken lock — causes a refusal.
- **T-008** Failing test: without quorum, any configuration-writing action
  refuses with that reason.
- **T-009** Failing test: with a node unreachable in a two-node cluster, any
  action assuming it is dead refuses with the ambiguity named.
- **T-010** Registry-wide assertion: no registered action can fence a node, force
  quorum, alter corosync, or restart `pveproxy`, `pvedaemon`, `pve-cluster` or
  `corosync`.
- **T-011** Registry-wide assertion: no action affecting cluster membership,
  quorum configuration or fencing is autonomously available at any level.

## Phase 3 — Guest lifecycle

- **T-012** Start, graceful shutdown, reboot, hard stop, suspend, resume — for
  virtual machines and containers.
- **T-013** Failing test: a restart attempts graceful shutdown first, escalates
  to hard stop only after the declared timeout, records the escalation, and
  classifies the hard stop separately.
- **T-014** Start verification: running state reached, and the guest agent
  responds where present.
- **T-015** Unlock action with the dead-task precondition.
- **T-016** Failing test: unlock refuses when the holding task is alive, at every
  autonomy level.
- **T-017** A guest that shuts down cleanly but slowly is not hard-stopped early.
- **T-018** A start that succeeds and immediately crashes verifies as
  ineffective, not effective.

## Phase 4 — Movement

- **T-019** Migration with feasibility check and online preference.
- **T-020** Failing test: migration refuses rather than silently performing an
  offline migration.
- **T-021** Failing test: migration into a node that cannot see the guest's
  storage is refused as a precondition.
- **T-022** HA relocate as a distinct, highest-class action.
- **T-023** A migration that succeeds on the API and leaves the guest stopped
  verifies as ineffective.

## Phase 5 — Storage

- **T-024** Reclamation taking an explicit item list; failing test that a policy
  such as "oldest first" cannot be passed.
- **T-025** Failing test: any recovery point — snapshot, backup, last replication
  base — is the highest class regardless of size.
- **T-026** Orphaned-volume removal verifying ownership at execution time.
- **T-027** Failing test: no action can extend a thin pool or a ZFS pool; the
  system proposes it instead.
- **T-028** Reclaiming space a running backup is about to need — assert the
  precondition catches it.

## Phase 6 — Backups and replication

- **T-029** Backup retry; failing test that it refuses to collide with a
  scheduled run.
- **T-030** Replication resync with rate limiting and a stated expected link
  impact.
- **T-031** Failing test: no action deletes a backup in order to make room for a
  backup.

## Phase 7 — Execution evidence

- **T-032** Task identifier retention; log and outcome attached to the incident.
- **T-033** Failing test: a task that fails is reported as a failure with the
  provider's error, even though the API call returned success.
- **T-034** Per-resource serialisation through feature 041's lock; two incidents
  proposing against one guest do not act concurrently.
- **T-035** Structural test: no action holds a credential.
- **T-036** Every action exercised against recorded task outcomes including
  failures, with no live cluster.

## Definition of done

- SC-001 through SC-012 each proven by a named test.
- The risk table reviewed and asserted against the registry.
- Every action exercised once against a real cluster in feature 049's harness.
- `make verify` green.
