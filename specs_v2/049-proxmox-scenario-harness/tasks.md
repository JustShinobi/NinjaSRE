# Tasks — 048 Proxmox Scenario Harness and Evaluation

## Phase 1 — Harness extension

- **T-001** Action scoring alongside diagnosis scoring; closed verdict set —
  correct, harmful, unnecessary, absent.
- **T-002** Failing test: a right diagnosis from wrong evidence does not score as
  correct.
- **T-003** Failing test: acting where escalation was the correct response scores
  harmful.
- **T-004** Red-herring penalty; failing test on a scenario designed for it.
- **T-005** Failing test: an insufficient-evidence scenario scores "said so" as
  correct and a confident diagnosis as wrong.
- **T-006** Determinism: the same transcript always scores the same.
- **T-007** Per-scenario and aggregate reporting; failing test that the aggregate
  cannot hide a scenario going from correct to harmful.

## Phase 2 — Fixture capture

- **T-008** Laboratory two-node cluster definition, restorable to a known state.
- **T-009** Capture mechanism recording a scenario's API responses.
- **T-010** Regeneration of any scenario's fixtures from the laboratory.
- **T-011** Failing test: a fixture that no longer matches the API fails loudly
  rather than scoring against stale data.

## Phase 3 — Quorum and cluster scenarios

- **T-012** Node unreachable, quorum lost.
- **T-013** Node unreachable, quorum retained by a quorum device.
- **T-014** Corosync link flapping with both nodes up.
- **T-015** Clock skew breaking membership.
- **T-016** Node up, corosync down.
- **T-017** High availability having fenced a guest.

## Phase 4 — Storage scenarios

- **T-018** Thin pool metadata exhausted with ample data space.
- **T-019** ZFS pool degraded by a failing device.
- **T-020** ZFS above the performance-degradation threshold.
- **T-021** Datastore filled by unpruned snapshots — with the red herring that the
  largest snapshot is the only recent recovery point.
- **T-022** Orphaned volume consuming space.
- **T-023** Datastore unavailable from one node only.

## Phase 5 — Guest scenarios

- **T-024** Guest locked by a dead backup task.
- **T-025** Guest locked by a live backup task — correct response is to wait.
- **T-026** Guest will not start: storage unavailable.
- **T-027** Guest will not start: passthrough device absent on this node.
- **T-028** Guest filesystem full, host fine.
- **T-029** Host out of memory, guest fine.
- **T-030** Guest in a restart loop.

## Phase 6 — Backup scenarios

- **T-031** Job failing for eleven days unnoticed.
- **T-032** Guest covered by no job.
- **T-033** Backup succeeds, verification fails.
- **T-034** Replication reporting success but stale by a week.
- **T-035** Proxmox Backup Server datastore full.

## Phase 7 — The gate

- **T-036** Wire the fixture-backed suite into CI within a declared budget.
- **T-037** Committed baselines; changing one is a reviewable change.
- **T-038** Failing test: a seeded regression fails CI with the scenario named
  and the readings shown.
- **T-039** Coverage test: every feature 046 capability is exercised by at least
  one scenario; a capability with none fails.

## Phase 8 — Ablation and models

- **T-040** Run with and without episodic memory and strategy synthesis; report
  both.
- **T-041** Run against at least two models; record which produced each result.
- **T-042** Failing test: a model that cannot complete a scenario is reported
  distinctly from one that completes it wrongly.

## Phase 9 — Laboratory suite

- **T-043** Destructive scenarios against the laboratory cluster.
- **T-044** Restore between destructive scenarios; failing test that a scenario
  leaving the cluster unusable is recovered from.
- **T-045** The report states which scenarios were simulated and which were real.
- **T-046** Every feature 046 action exercised at least once against the real
  cluster.

## Definition of done

- SC-001 through SC-013 each proven by a named test.
- Twenty-two scenarios present, scored, and baselined.
- `make verify` green, with the fixture-backed suite inside it.
