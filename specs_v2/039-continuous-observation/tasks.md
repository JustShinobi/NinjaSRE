# Tasks — 038 Continuous Observation and Incident Lifecycle

## Phase 1 — Signals

- **T-001** Failing contract test for the signal store: append, query by window,
  retention sweep, tenant isolation.
- **T-002** Signal model — named, typed, timestamped, resource-scoped, sourced.
- **T-003** Poller source calling an integration on an interval through the
  credential proxy; rate limits respected.
- **T-004** Estate-transition source, reading feature 038's health transitions.
- **T-005** External metrics query source (the shape feature 047 fills in).
- **T-006** Failing test: a signal that stopped arriving is distinguishable from
  one reporting a healthy value.
- **T-007** Retention bounded to the longest detector window; sweep tested.

## Phase 2 — Detector model

- **T-008** Detector declaration schema; validation with named errors.
- **T-009** Resolution through the hierarchical config service, so a team can add
  one without code. Contract test against the real config service.
- **T-010** Threshold, absence, rate-of-change and state-transition conditions,
  each unit-tested at its boundary.
- **T-011** Hysteresis with distinct fire and clear thresholds.
- **T-012** Failing test: a flapping signal reports flapping rather than firing
  per crossing.
- **T-013** Enable, disable, and dry-run against historical signals without
  firing.
- **T-014** Assert a detector cannot reference a capability whose side-effect
  level is anything but read.

## Phase 3 — Evaluation

- **T-015** Evaluation tick over the estate; lease-based claiming.
- **T-016** Failing test: restart mid-evaluation does not double-fire.
- **T-017** Failing test: two replicas produce one outcome.
- **T-018** Purity with respect to inputs; failing test that a detector replayed
  against historical signals reproduces exactly the firings that happened.
- **T-019** Failing test: a detector that throws surfaces as an attention item
  and is not silently skipped.
- **T-020** Benchmark: ten thousand resources × one hundred detectors within
  budget.

## Phase 4 — Incidents

- **T-021** Failing contract test for the incident store.
- **T-022** Incident model and the closed state set; assert no path assigns a
  state outside it.
- **T-023** Timeline with cause and actor on every transition.
- **T-024** Failing test: a condition crossing and holding opens exactly one
  incident; crossing and recovering inside the duration opens none.
- **T-025** Correlation by grouping key; failing test that one cause across fifty
  resources is one incident with fifty subjects.
- **T-026** Self-close after the recovery duration, recorded as self-resolved.
- **T-027** Human close with a required reason, at any state.
- **T-028** A subject going absent while its incident is open — test the
  behaviour is declared, not accidental.

## Phase 5 — Unification

- **T-029** Failing test: a webhook alert and a detected condition produce
  structurally identical incidents.
- **T-030** Rewire every `/webhooks/*` route to raise an incident rather than
  start a run directly.
- **T-031** Assert exactly one lifecycle constructs incidents, structurally.

## Phase 6 — Suppression

- **T-032** Maintenance windows from the estate suppress detectors on covered
  resources; failing test that suppression is recorded, not silent.
- **T-033** Suppression rules scoped by resource, kind, detector, team and time.
- **T-034** Global pause stopping all detection without unconfiguring; visible
  everywhere it matters.
- **T-035** A maintenance window spanning a daylight-saving change behaves as
  declared.

## Phase 7 — Dispatch and escalation

- **T-036** Objective derivation from incident and subjects; run links back to
  the incident.
- **T-037** Failing test: one hundred simultaneous incidents do not start one
  hundred simultaneous runs.
- **T-038** Per-team and global dispatch rate limits.
- **T-039** One run per correlation; a second firing does not start a second run.
- **T-040** Escalation through the existing registry; cancel on close, asserted.

## Phase 8 — Surfaces

- **T-041** Gateway endpoints: incident list, detail, close, suppress; detector
  list, enable, disable, dry-run. Contract tests for each.
- **T-042** CLI commands for the same.
- **T-043** Console incident and detector views inside feature 036's frame.

## Definition of done

- SC-001 through SC-010 each proven by a named test.
- Every webhook path migrated; one lifecycle asserted structurally.
- `make verify` green.
