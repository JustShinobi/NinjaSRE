# Plan — 044 Proxmox Investigation Capabilities

## Technical context

| Concern | Choice |
|---|---|
| Location | `integrations/proxmox/tools/` for the tools, `capabilities/skills/proxmox/` for the methodology |
| Shape | The existing tool framework: declared schema, typed arguments, bounded result, read side-effect level |
| Skills | The existing skill format, with anti-patterns as a first-class section |
| Fixtures | The recorded cluster states from feature 044, extended with the specific degraded cases each tool needs |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| I — Evidence over assertion | A tool that concludes must show what it read. | Every tool returns the readings behind its answer, and NFR-003 requires it to state what it could not determine. A conclusion drawn from a reading that failed is not available. |
| III — Read-only by default | Everything here reads. | NFR-001, asserted structurally by SC-012. |
| IX — Capabilities are declared | New capabilities. | Declared schemas, typed arguments, declared bounds, declared required privileges. |
| II — Bounded autonomy | Tool results enter the model's context. | NFR-002 bounds every result, so a cluster with a thousand snapshots cannot exhaust a small model's context — which is feature 043's concern and this feature's obligation. |

## Architecture decisions

**Tools answer questions; they do not wrap endpoints.** `proxmox_quorum_status`
returns whether the cluster is quorate, by what margin, under what configuration,
and with what consequence. It reads four endpoints to do so. A tool per endpoint
would push the synthesis into the model, which is precisely where a small local
model does it worst and where the answer is least reproducible.

**The consequence is part of the answer.** "Not quorate" is a fact an operator
still has to interpret. "Not quorate, so the configuration filesystem is
read-only, so nothing can be started or migrated, and the running guests are
unaffected" is the same fact with the three inferences that always follow it.
Encoding them in the tool means they are correct every time rather than
rediscovered by the model each run.

**Every distinction that changes the remedy is a distinction the tool makes.**
Metadata exhaustion versus data exhaustion. Live lock versus orphaned lock. Host
memory pressure versus guest memory pressure. Guest filesystem full versus host
storage full. In each pair the readings look similar and the correct action is
completely different, and each is a case where an agent left to infer will
sometimes infer wrong.

**Reclaimable space always says what it protects.** This is the single most
dangerous tool in the feature: its output is a list of things that could be
deleted, and the most reclaimable item is very often the only recent recovery
point. Making "what this protects" a required field of every entry means the
dangerous suggestion cannot be made without its own warning attached.

**Anti-patterns are tested, not documented.** FR-025 lists four plausible wrong
moves. SC-011 requires a scenario for each in which following it would have been
wrong, so the skill's warning is exercised rather than asserted.

**Two-node gets its own skill.** The general cluster skill would have to hedge
every statement. A dedicated skill can state plainly what a two-node cluster does
when a node is lost, what configuration changes that, and what is safe to do in
the read-only state.

## Phases

1. **Cluster, quorum, corosync.** Quorum status with configuration and
   consequence, link health with flap detection, HA state with fencing, clock
   skew.
2. **Storage and ZFS.** Datastore usage with consumers, thin-pool metadata, ZFS
   pool health and capacity threshold, disk SMART with backing map, reclaimable
   space with protection, orphaned volumes, datastore-to-node availability.
3. **Guests.** Start diagnosis, lock liveness, resource pressure attribution,
   guest-agent filesystem versus host storage, task history, migration
   feasibility with blockers.
4. **Backups.** Coverage with gaps, failures, Proxmox Backup Server verification
   and pruning, replication lag as recovery-point exposure.
5. **Skills.** One per domain, plus the two-node skill; anti-patterns; routing to
   estate and episodic memory before concluding.
6. **Fixtures and proofs.** The degraded cases each success criterion needs, and
   the anti-pattern scenarios.

## Risks

- **Tools that synthesise can synthesise wrongly.** Mitigated by returning the
  underlying readings alongside the conclusion, so a wrong synthesis is visible
  in the trace rather than being the only thing recorded.
- **The two-node skill encodes advice that depends on the operator's
  configuration.** Mitigated by having the quorum tool report the configuration
  first, so the skill branches on a reading rather than on an assumption.
- **Bounded results hide the item that mattered.** Mitigated by bounding through
  ranking rather than truncation — the largest consumers, the oldest snapshots —
  and by stating that the result was bounded and by what.
