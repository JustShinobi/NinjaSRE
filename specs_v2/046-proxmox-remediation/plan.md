# Plan — 045 Proxmox Remediation Capabilities

## Technical context

| Concern | Choice |
|---|---|
| Location | `capabilities/tools/remediation/proxmox_*/`, following the existing applier layout |
| Execution | The existing `RemediationExecutor`, unchanged |
| Gating | Feature 040's resolver — no Proxmox-specific autonomy path exists |
| Verification | Feature 041's obligations, with signals from feature 039's store |
| Async | Proxmox task identifiers polled through feature 044's bounded poller |
| Risk table | A declared table in one module, asserted against the registry |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| II — Bounded autonomy | These are the writes. | Every one resolves through feature 040. FR-007 and FR-024 put cluster-membership actions outside autonomous reach at every level — a bound configuration cannot lift. |
| III — Read-only by default | Writes need an approval and a rollback plan. | FR-001 requires both at declaration; FR-002 fails registration without them; feature 040 refuses any action lacking a rollback plan at every level. |
| IV — Secrets never reach the agent | Writes use a privileged token. | Execution goes through the credential proxy; NFR-001 asserted structurally. |
| I — Evidence over assertion | "The API returned 200" is not "it worked". | FR-030 makes the task outcome the verdict, and feature 041 re-reads the signal afterwards. |
| XII — Test-first | The risk table is the safety-critical artefact. | SC-002 asserts the table against the registry, and it is written before the actions. |

## Architecture decisions

**The risk table is a single reviewable artefact, asserted against the code.** A
risk class scattered across twenty capability modules is a risk classification
nobody has ever read as a whole. One table, one review, and a test that fails
when a capability's declared class differs from the table's — so the document an
operator reads is the one the system obeys.

**Data loss dominates size.** A hundred-megabyte snapshot that is the only recent
recovery point is a higher-risk deletion than a fifty-gigabyte orphaned disk.
Classifying by what an item protects rather than by what it costs is the rule
that keeps the storage actions from being quietly the most dangerous ones.

**Nothing touches quorum, fencing or node services.** This is the deliberate hole
in the feature. In a two-node cluster the system cannot distinguish a dead node
from an unreachable one — the classic split-brain ambiguity — and both wrong
answers are expensive: fencing a live node kills running guests, and starting its
guests elsewhere while it still runs them corrupts shared state. No autonomy level
should be able to resolve that ambiguity, so no capability offers it. The system
reports and escalates. SC-008 asserts the hole over the whole registry, so it
cannot be filled in by accident.

**Preconditions are re-evaluated at execution.** An investigation that took four
minutes has a four-minute-old picture. The guest may have migrated, the lock may
have been taken, the datastore may have filled. Every precondition re-reads
immediately before acting, and a changed target is a refusal rather than a
proceed.

**Graceful first, hard second, classified separately.** A restart is not one
action. Attempting an ACPI shutdown is middle-risk; pulling the power on a
running database is not. Modelling the escalation explicitly means an operator
can permit the first autonomously and require approval for the second, which is
the configuration most people actually want.

**Reclamation takes a list, never a policy.** "Delete the oldest snapshots until
there is room" is one bad night away from deleting the recovery point somebody
needed. The action takes explicit items; choosing them is a proposal a human or a
policy at the highest risk class approves.

## Phases

1. **Risk table and declaration.** The table; the declaration contract; failure
   at registration when incomplete; the assertion that table and registry agree.
2. **Preconditions.** Fresh-reading evaluation; the changed-target refusal; the
   quorum and two-node ambiguity refusals; the registry-wide prohibition
   assertions.
3. **Guest lifecycle.** Start, graceful shutdown, reboot, hard stop, suspend,
   resume, for both kinds; the graceful-to-hard escalation; unlock with the
   dead-task precondition; start verification including guest agent.
4. **Movement.** Migration with feasibility, online preference, refusal rather
   than silent offline, storage-visibility precondition; HA relocate as its own
   highest-class action.
5. **Storage.** Explicit-list reclamation; recovery-point classification;
   orphaned-volume removal with execution-time ownership check; the refusal to
   extend a pool.
6. **Backups and replication.** Backup retry with collision refusal; replication
   resync with rate limiting and stated link impact; the prohibition on deleting
   a backup to make room for one.
7. **Execution evidence.** Task identifier retention, log and outcome attachment,
   provider-error surfacing, the task-outcome-not-HTTP-status rule,
   per-resource serialisation.

## Risks

- **The risk table is too conservative and nothing is ever autonomous.**
  Mitigated by feature 040's configurable bound: an operator who wants middle-risk
  actions autonomous sets the bound there. The table describes the actions; the
  policy decides the posture.
- **A precondition re-read doubles the call count.** Accepted. The alternative is
  acting on a stale picture, and the reads are cheap relative to the write.
- **Somebody adds a fencing capability later.** Mitigated by SC-008 asserting
  over the whole registry rather than over a list, so a new capability in a
  prohibited category fails the suite.
