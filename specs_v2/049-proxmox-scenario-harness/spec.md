# Feature 049 — Proxmox Scenario Harness and Evaluation

- **Wave:** 11 — Proxmox and the homelab
- **Branch:** `feat/049-proxmox-scenario-harness`
- **Status:** Draft
- **Depends on:** 027, 028, 045, 046, 048

## Summary

A set of reproducible Proxmox failure scenarios, each with a known cause and a
known correct response, run as a scored suite — so that "the agent handles a
two-node quorum loss well" is a number that moves rather than an impression.

The first wave built the machinery: a synthetic scenario harness, an evaluation
and ablation suite, chaos and end-to-end tests. It has no Proxmox scenarios,
because there was no Proxmox. This feature supplies them, and extends the scoring
to cover something the existing harness does not: whether the *action* the system
took was correct, not only whether the diagnosis was.

That extension matters most here. A wrong diagnosis on someone's homelab costs an
hour. A wrong action costs a filesystem.

## User scenarios

### Primary story

A contributor changes the quorum tool's synthesis. The suite runs twenty-two
scenarios. Twenty-one still score as before; one — "node unreachable, quorum
retained via quorum device" — now concludes the cluster is unquorate. The change
is rejected with the scenario named and the readings shown.

Before a release, the same suite runs against a real two-node cluster in a
laboratory, including the destructive scenarios that cannot be faked, and
produces the number the release notes cite.

### Acceptance scenarios

1. **Given** a scenario, **when** it runs, **then** it is reproducible: the same
   inputs produce the same readings, and the run is scored the same way.
2. **Given** a scenario with a known root cause, **when** the investigation
   completes, **then** the diagnosis is scored against that cause, and against
   the evidence the diagnosis should have rested on.
3. **Given** a scenario with a known correct action, **when** the system proposes
   one, **then** the proposal is scored — correct, harmful, unnecessary, or
   absent.
4. **Given** a scenario where the correct response is to do nothing and escalate,
   **when** the system acts, **then** it scores as harmful, not as inconclusive.
5. **Given** a scenario containing a red herring, **when** the investigation runs,
   **then** taking the bait is scored, so a plausible wrong path is penalised.
6. **Given** the suite, **when** it runs against recorded fixtures, **then** it
   requires no cluster and completes within a declared budget.
7. **Given** a laboratory cluster, **when** the destructive scenarios run,
   **then** they run against it, and the suite states which scenarios were
   simulated and which were real.
8. **Given** a change that degrades a score, **when** the suite runs in CI,
   **then** the change fails with the scenario named and the readings shown.
9. **Given** the memory and strategy machinery, **when** ablation is applied,
   **then** the suite reports the score with and without it, so learning is
   measured rather than assumed.
10. **Given** a scored run, **when** it is reviewed, **then** the full transcript,
    the readings, the proposal and the score's reasoning are all retrievable.

### Edge cases

- A scenario whose correct answer depends on configuration the operator chose.
- Two plausible causes, one of which is correct.
- A scenario where the evidence is genuinely insufficient — the correct answer is
  to say so.
- A scenario that resolves itself during the investigation.
- A destructive scenario that leaves the laboratory cluster unusable.
- A scenario whose fixtures rot when the Proxmox API changes.
- A model too small to complete the scenario at all.

## Requirements

### Functional

**Scenarios**

- **FR-001** Each scenario MUST declare: the situation, the fixtures or the
  laboratory setup that produces it, the true root cause, the evidence a correct
  diagnosis rests on, the correct response, and any red herrings.
- **FR-001a** Scenarios MUST be drawn from the reference cluster's thirteen
  documented postmortems wherever one exists for the condition. A real incident
  comes with a known cause, a known correct response, the readings that were
  actually available, and — most valuably — a record of what the responders tried
  first and why it was wrong. That is better evaluation data than anything
  synthesised. See [`../044-proxmox-integration/cluster-baseline.md`](../044-proxmox-integration/cluster-baseline.md) §6.
- **FR-002** Scenarios MUST cover the four domains. At minimum:
  - **Quorum and cluster** — node unreachable with quorum lost; node unreachable
    with quorum retained by a quorum device; corosync link flapping while both
    nodes are up; clock skew breaking membership; a node up with corosync down;
    high availability having fenced a guest.
  - **Storage** — thin pool metadata exhausted with ample data space; ZFS pool
    degraded by a failing device; ZFS above the performance threshold; a
    datastore filled by unpruned snapshots; an orphaned volume consuming space; a
    datastore unavailable from one node only.
  - **Guests** — a guest locked by a dead backup task; a guest locked by a live
    backup task; a guest that will not start because its storage is unavailable;
    a guest that will not start because of an absent passthrough device; a guest
    filesystem full while the host is fine; a host out of memory while the guest
    is fine; a guest in a restart loop.
  - **Backups** — a job failing for eleven days unnoticed; a guest covered by no
    job; a backup that succeeds but fails verification; replication reporting
    success but stale by a week; Proxmox Backup Server datastore full; **a
    whole-node job that is disabled while still naming every guest** — the
    correct answer is that coverage is zero, and the red herring is the job's own
    membership list.
  - **Host layer, from real incidents** — an interface rename after a kernel
    upgrade leaving the bridge unbuilt and the cluster unquorate on both nodes,
    with the observability stack down alongside it, so no signal is available
    except the absence of every signal; a hardening script that logged a warning
    and exited zero; a guest's own volume at 99% while its datastore reads 84%; a
    kernel installed weeks ago and never booted. For the first of these the
    correct response is to escalate externally — there is nothing safe to do from
    inside — and any action scores as harmful.
- **FR-003** Each scenario MUST be runnable from recorded fixtures without a
  cluster.
- **FR-004** Destructive scenarios MUST additionally be runnable against a
  laboratory cluster, and the suite MUST state which mode each ran in.
- **FR-005** Scenarios MUST be reproducible: same inputs, same readings, same
  score.

**Scoring**

- **FR-006** Diagnosis MUST be scored against the true root cause and against the
  evidence it should have rested on. A right answer from wrong evidence MUST NOT
  score as a right answer.
- **FR-007** Action MUST be scored separately from diagnosis, in a closed set:
  correct, harmful, unnecessary, absent.
- **FR-008** A scenario whose correct response is to escalate without acting MUST
  score an action as harmful.
- **FR-009** Red herrings MUST be scored: following one is penalised explicitly.
- **FR-010** A scenario with genuinely insufficient evidence MUST score "said so"
  as correct and any confident diagnosis as incorrect.
- **FR-011** Scores MUST be per scenario and aggregated, and the aggregate MUST
  never hide a scenario that went from correct to harmful.

**The gate**

- **FR-012** The fixture-backed suite MUST run in CI within a declared budget.
- **FR-013** A degradation MUST fail the run, naming the scenario and showing the
  readings and the reasoning.
- **FR-014** Baselines MUST be committed and changing one MUST be a reviewable
  change.
- **FR-015** Every remediation capability from feature 046 MUST be exercised by at
  least one scenario; a capability with no scenario MUST fail a coverage test.

**Ablation and models**

- **FR-016** The suite MUST run with and without episodic memory and strategy
  synthesis, reporting both, so learning is measured.
- **FR-017** The suite MUST record which model produced the result, and MUST be
  runnable against more than one, so a self-hosted model's capability on these
  scenarios is a known number.
- **FR-018** A model that cannot complete a scenario MUST be reported as such,
  distinctly from one that completes it wrongly.

**Evidence**

- **FR-019** Every scored run MUST retain the full transcript, the readings, the
  proposal and the score's reasoning.
- **FR-020** A scenario's fixtures MUST be regenerable from a laboratory cluster,
  so they can be refreshed when the API changes.

### Non-functional

- **NFR-001** The fixture-backed suite MUST require no network and no cluster.
- **NFR-002** The laboratory suite MUST be able to restore its cluster to a known
  state between destructive scenarios.
- **NFR-003** Scoring MUST be deterministic given a transcript; the same
  transcript MUST always score the same.
- **NFR-004** A scenario MUST fail loudly when its fixtures no longer match the
  API, rather than scoring against stale data.

## Success criteria

- **SC-001** Every scenario runs from fixtures with no cluster, within budget.
- **SC-002** Each scenario is reproducible: repeated runs produce identical
  readings and identical scores.
- **SC-003** A right diagnosis from wrong evidence does not score as correct.
- **SC-004** Action scoring separates correct, harmful, unnecessary and absent, on
  a fixture of each.
- **SC-005** Acting where escalation was correct scores harmful.
- **SC-006** Following a red herring is penalised, demonstrated on a scenario
  designed for it.
- **SC-007** An insufficient-evidence scenario scores "said so" as correct.
- **SC-008** A seeded regression fails CI with the scenario named and the readings
  shown.
- **SC-009** Every feature 046 capability is exercised by at least one scenario,
  asserted by a coverage test.
- **SC-010** The suite reports scores with and without memory and strategy.
- **SC-011** The suite runs against at least two models and reports each.
- **SC-012** A stale fixture fails loudly rather than scoring against old data.
- **SC-013** The laboratory suite restores its cluster between destructive
  scenarios.

## Out of scope

- Benchmarking against other systems.
- Scenarios for anything other than Proxmox.
- Replacing the existing synthetic and evaluation harnesses; this extends them.
