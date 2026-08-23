# Tasks — 047 Homelab Profile and Cluster Guardian

## Phase 1 — The profile

- **T-001** Homelab profile beside the existing ones: one compose file, one
  command, full stack on one host.
- **T-002** Declare the memory and CPU footprint; failing soak test asserting the
  deployment stays within it while idle over a long run.
- **T-003** Component set: database, gateway, console, credential proxy,
  scheduler, observer. Assert multi-team-only components are absent.
- **T-004** Local model endpoint as first-class configuration, verified through
  feature 043's probe at setup.
- **T-005** Backup and restore of the deployment's own state, one command each;
  failing test that a restore round-trips.
- **T-006** Failing test: upgrade preserves estate, detectors, policies,
  incidents and history, and reports any changed shipped detector definition.
- **T-007** Failing test: host restart resumes the observer, the scheduler and
  pending verification obligations, losing no incident.
- **T-008** Assert the profile works with no inbound internet connectivity.

## Phase 2 — Topology detection

- **T-009** Detect single-node, two-node and multi-node topologies.
- **T-010** Failing test: two-node detectors activate on a two-node topology and
  not on a three-node one.
- **T-011** Failing test: a single-node installation runs with no cluster
  detectors firing spuriously.

## Phase 3 — Cluster detectors

- **T-012** Quorum lost; quorum margin zero — one loss from unquorate.
- **T-013** Corosync link degraded; corosync link lost.
- **T-014** Node unreachable; node clock skew beyond corosync tolerance.
- **T-015** High-availability fencing occurred.
- **T-016** Cluster node running a divergent Proxmox version.
- **T-017** Two-node quorum survival configuration — whether a single node loss
  costs quorum and how that is mitigated.

## Phase 4 — Storage detectors

- **T-018** Datastore usage thresholds.
- **T-019** Thin pool metadata usage, separate from data usage.
- **T-020** ZFS pool degraded; ZFS pool faulted.
- **T-021** ZFS capacity above the performance-degradation threshold.
- **T-022** Scrub overdue.
- **T-023** SMART attributes predicting failure.
- **T-024** Growth trending to full within a declared horizon.

## Phase 5 — Guest detectors

- **T-025** Guest stopped that was expected running.
- **T-026** Guest locked beyond a threshold.
- **T-027** Guest restart loop.
- **T-028** Sustained memory or CPU saturation.
- **T-029** Guest filesystem full as reported by its agent.
- **T-030** Guest with no recent successful backup.

## Phase 6 — Backup detectors

- **T-031** Backup job failed; backup job did not run when scheduled.
- **T-032** Guest covered by no backup job.
- **T-033** Backup verification failed.
- **T-034** Proxmox Backup Server datastore near full.
- **T-035** Garbage collection or prune overdue.
- **T-036** Replication lag beyond the declared recovery-point objective.

## Phase 7 — Maintenance detectors

- **T-037** Certificate expiring.
- **T-038** Pending package updates, security updates distinguished, beyond a
  threshold.
- **T-039** Node requiring reboot after a kernel update.

## Phase 8 — Detector set proofs

- **T-040** Failing test per detector: fires on a fixture representing its
  condition, does not fire on a fixture representing health.
- **T-041** Failing test: every shipped detector has a threshold, a stated
  rationale and a remedy; one without fails.
- **T-042** Thresholds overridable per deployment and per resource without
  editing the shipped set.
- **T-043** Detector documentation visible in the console, not only in a file.

## Phase 9 — Posture and windows

- **T-044** Failing test: the default posture on a fresh deployment is
  propose-only.
- **T-045** The recommended preset as a named, inspectable policy document.
- **T-046** Applying any posture shows feature 040's preview against recent
  history first.
- **T-047** Backup-window detection offered as freeze windows without the
  operator having to know they need one.

## Phase 10 — Notification, heartbeat, self-awareness

- **T-048** Telegram, Discord and email as first-class sinks; no corporate
  account required.
- **T-049** Message content: what happened, what was done, what was not and why,
  what is needed.
- **T-050** Failing test: a problem resolving before acknowledgement sends the
  resolution.
- **T-051** Failing test: a storm becomes one digest, not many messages.
- **T-052** Bounded escalation that ends.
- **T-053** Outbound heartbeat on an interval to a channel the operator chooses.
- **T-054** Failing test: the deployment detects it runs on the cluster it
  manages and reports a problem affecting itself rather than appearing healthy.

## Phase 11 — Load

- **T-055** Measure and declare the total call rate detection adds to the
  cluster; assert it stays within the declared bound.

## Definition of done

- SC-001 through SC-013 each proven by a named test.
- Every shipped detector has a firing fixture and a healthy fixture.
- `make verify` green.
