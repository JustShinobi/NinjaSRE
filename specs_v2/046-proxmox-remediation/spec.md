# Feature 046 — Proxmox Remediation Capabilities

- **Wave:** 11 — Proxmox and the homelab
- **Branch:** `feat/046-proxmox-remediation`
- **Status:** Draft
- **Depends on:** 040, 041, 045

## Summary

The actions the system may take on a Proxmox cluster, each with a declared risk
class, a rollback plan where one exists, a verification signal, and a set of
preconditions that must hold before it runs.

The existing remediation set is seven Kubernetes-shaped actions. None of them
applies to a hypervisor. This feature adds the hypervisor set, and it does so
under the machinery the previous two features built: every action resolves an
autonomy level through feature 040 and closes its loop through feature 041. There
is no Proxmox-specific autonomy path.

The risk classification is the substance of this specification. Starting a
stopped container and hard-stopping a running virtual machine are both "one API
call" and are not remotely the same act. Getting that table right is what makes
autonomous operation on someone's homelab defensible.

## User scenarios

### Primary story

A backup dies and leaves a guest locked. The system sees the lock, confirms
through the investigation tool that the task holding it is dead, clears the lock,
waits, confirms the guest is manageable again, and closes the incident. The
operator reads about it later. This is low risk, reversible, and precisely the
class of tedium worth automating.

A datastore hits ninety-five per cent. The system identifies reclaimable space —
and stops. The largest reclaimable item is the only snapshot from before last
week's change, and deleting a recovery point is not something it does on its own.
It proposes, with what each option would return and what each protects, and
waits.

A node stops responding. The system does not fence it, does not force quorum, and
does not start its guests elsewhere. In a two-node cluster it cannot distinguish
a dead node from an unreachable one, and both wrong answers cost data. It reports
what it knows and escalates.

### Acceptance scenarios

1. **Given** any action, **when** it is proposed, **then** its risk class, its
   rollback plan and its verification signal are all declared, and an action
   missing any of them cannot be registered.
2. **Given** a guest locked by a dead task, **when** the unlock action runs,
   **then** the lock is cleared and the guest is confirmed manageable.
3. **Given** a guest locked by a live task, **when** unlock is proposed, **then**
   its precondition fails and it does not run, whatever the autonomy level.
4. **Given** a stopped guest that should be running, **when** the start action
   runs, **then** it starts and is verified running with its services reachable
   where that can be checked.
5. **Given** a guest needing restart, **when** the action runs, **then** graceful
   shutdown is attempted first, a hard stop only after a declared timeout, and
   the escalation from one to the other is recorded and separately classified.
6. **Given** a migration, **when** it is proposed, **then** feasibility is checked
   first, an online migration is preferred, and the action refuses rather than
   falling back to an offline migration without saying so.
7. **Given** reclaimable space, **when** deletion is proposed, **then** anything
   that is a recovery point is classified at the highest risk regardless of size.
8. **Given** a node that is unreachable in a two-node cluster, **when** any action
   that assumes it is dead is proposed, **then** it is refused with the ambiguity
   named.
9. **Given** any action, **when** it completes, **then** its Proxmox task
   identifier, its log and its outcome are attached to the incident.
10. **Given** an action whose task fails, **when** it fails, **then** the
    provider's own error is surfaced and the failure is not reported as a
    success because the API call returned 200.
11. **Given** the cluster without quorum, **when** any action requiring a
    configuration write is proposed, **then** it is refused with the reason,
    because the configuration filesystem is read-only.
12. **Given** an action with a rollback plan, **when** verification shows it made
    things worse, **then** feature 041 rolls it back automatically.

### Edge cases

- A guest that shuts down cleanly but takes twenty minutes.
- A migration that succeeds on the API and leaves the guest stopped.
- An unlock on a guest whose task died but whose disk operation did not.
- A start that succeeds and immediately crashes.
- A backup retry that collides with the next scheduled run.
- Reclaiming space that the running backup is about to need.
- A replication resync that saturates the link between nodes.
- An action proposed against a guest that migrated after the proposal was made.
- Two actions proposed against the same guest by two incidents.

## Requirements

### Functional

**Declaration**

- **FR-001** Every action MUST declare: a risk class, its preconditions, its
  rollback plan or an explicit statement that none exists, its verification
  signals, its settle period, and the Proxmox privileges it needs.
- **FR-002** An action missing any of those MUST fail registration, not runtime.
- **FR-003** Preconditions MUST be evaluated against fresh readings immediately
  before execution, not against the state the investigation observed.
- **FR-004** An action whose target changed between proposal and execution — a
  guest that migrated, a lock that was taken — MUST refuse rather than proceed.

**The risk table**

- **FR-005** Risk classification MUST account for reversibility, data-loss
  potential, availability impact and blast radius, and MUST be reviewable as a
  single table.
- **FR-006** At minimum, these classifications MUST hold: clearing an orphaned
  lock and starting a stopped guest are the lowest class; graceful guest shutdown
  and reboot, online migration, replication resync and backup retry are the
  middle class; hard guest stop, snapshot or backup deletion, offline migration,
  storage reclamation of a recovery point, HA state changes and anything touching
  a node's own services are the highest class.
- **FR-007** Any action affecting cluster membership, quorum configuration or
  fencing MUST be the highest class and MUST NOT be autonomously available at any
  level.
- **FR-008** Any action that can lose data MUST be the highest class regardless of
  how small the change is.

**Guest lifecycle**

- **FR-009** Actions MUST exist for: start, graceful shutdown, reboot, hard stop,
  suspend and resume — for both virtual machines and containers.
- **FR-010** A restart MUST attempt graceful shutdown first and escalate to a hard
  stop only after a declared timeout, recording the escalation and classifying
  the hard stop separately.
- **FR-011** A start MUST verify the guest reached running state and, where a
  guest agent is present, that the agent responds.
- **FR-012** An unlock action MUST require, as a precondition, that the holding
  task is confirmed dead.

**Movement**

- **FR-013** A migration action MUST check feasibility first and MUST prefer
  online migration.
- **FR-014** It MUST refuse rather than silently perform an offline migration when
  online is not possible.
- **FR-015** An HA relocate MUST be distinct from a manual migration and MUST be
  the highest risk class.
- **FR-016** No action may migrate a guest into a node that cannot see its
  storage, and this MUST be a precondition, not a hope.

**Storage**

- **FR-017** A reclamation action MUST take an explicit list of items, never a
  policy such as "oldest first".
- **FR-018** Any item that is a recovery point — a snapshot, a backup, the last
  replication base — MUST be the highest risk class regardless of size.
- **FR-019** An orphaned-volume removal MUST verify the volume belongs to no
  guest at execution time, not at proposal time.
- **FR-020** No action may extend a thin pool or a ZFS pool; the system MUST
  propose that to a human.

**Backups and replication**

- **FR-021** A backup-retry action MUST refuse to collide with a scheduled run.
- **FR-022** A replication resync MUST be rate-limitable and MUST state the link
  impact it expects.
- **FR-023** No action may delete a backup as part of making room for a backup.

**Cluster safety**

- **FR-024** No action may fence a node, force quorum, or alter corosync
  configuration.
- **FR-025** In a cluster without quorum, any action requiring a configuration
  write MUST refuse with that reason.
- **FR-026** In a two-node cluster with a node unreachable, any action that
  assumes the node is dead MUST refuse with the ambiguity named.
- **FR-027** No action may restart `pveproxy`, `pvedaemon`, `pve-cluster` or
  `corosync`; these MUST be proposals to a human.
- **FR-027a** No action may modify a node's network configuration —
  `/etc/network/interfaces`, bridges, bonds, VLANs, interface naming, or routing.
  In the reference cluster this state is owned by a declarative control plane with
  its own apply path, and it is the layer whose only total outage required
  physical access to recover. A second writer here turns drift into an outage.
- **FR-027b** No action may write to any path a declarative control plane owns.
  Where the operator runs one, this system proposes changes *to that repository's
  workflow* and never applies them directly.

**Execution and evidence**

- **FR-028** Every action MUST execute through the existing remediation executor
  and the credential proxy.
- **FR-029** Every action MUST retain its Proxmox task identifier and attach the
  task log and outcome to the incident.
- **FR-030** A task that fails MUST surface the provider's own error, and an API
  call returning success MUST NOT be reported as the action succeeding — the task
  outcome is what counts.
- **FR-031** Two actions against one guest MUST be serialised by feature 041's
  per-resource lock.

### Non-functional

- **NFR-001** No action may hold a credential.
- **NFR-002** Every action MUST be testable against recorded task outcomes,
  including failures, without a live cluster.
- **NFR-003** Every action MUST be exercised against a real cluster at least once,
  in the harness feature 049 provides.
- **NFR-004** The risk table MUST be documented in one place and asserted against
  the registered capabilities, so the table and the code cannot diverge.

## Success criteria

- **SC-001** An action missing a risk class, a rollback statement or a
  verification signal fails registration.
- **SC-002** The risk table matches the registered capabilities exactly, asserted.
- **SC-003** Unlock refuses when the holding task is alive, at every autonomy
  level.
- **SC-004** A restart escalating from graceful to hard records the escalation and
  is classified separately.
- **SC-005** Migration refuses rather than silently going offline.
- **SC-006** Migration into a node without the guest's storage is refused as a
  precondition.
- **SC-007** Deleting a recovery point is the highest class regardless of size.
- **SC-008** No registered action can fence, force quorum, alter corosync, or
  restart a node service — asserted over the whole registry.
- **SC-009** Without quorum, configuration-writing actions refuse with the reason.
- **SC-010** With a node unreachable in a two-node cluster, actions assuming it is
  dead refuse with the ambiguity named.
- **SC-011** A task that fails is reported as a failure with the provider's error,
  even though the API call succeeded.
- **SC-012** Preconditions are re-evaluated at execution; a target that changed
  after proposal causes a refusal.

## Out of scope

- The autonomy decision — feature 040.
- Verification and rollback machinery — feature 041.
- Anything requiring shell access to a node.
- Provisioning: creating, cloning or destroying guests.
