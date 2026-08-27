# Tasks — 040 Closed-Loop Remediation

## Phase 1 — Verification declaration

- **T-001** Declare, on every remediation capability, the signals its effect
  appears in and the settle period before they are meaningful.
- **T-002** Validation at registration; a named error when a signal reference
  does not exist.
- **T-003** Failing test: a capability with no declared verification signal
  reports `unverifiable`, and whether it may run autonomously is a policy
  decision.
- **T-004** Coverage sweep over the seven existing remediation capabilities; a
  test fails when a new one lands undeclared.

## Phase 2 — Obligations

- **T-005** Failing contract test for the verification obligation store.
- **T-006** Capture the before values immediately prior to execution.
- **T-007** Durable obligation written by the executor with a due time; the run
  ends without waiting.
- **T-008** Lease-based claiming of due obligations; safe across replicas.
- **T-009** Failing test: verification survives a deployment restart between
  action and check.
- **T-010** The five outcomes — effective, ineffective, worsened, inconclusive,
  unverifiable — as a closed set.
- **T-011** Failing test: a signal that did not move enough reports
  `inconclusive`, never `effective`.
- **T-012** "Awaiting verification" state surfaced everywhere the action is
  displayed.
- **T-013** A settle period longer than the run's wall-clock ceiling works,
  asserted.

## Phase 3 — Rollback

- **T-014** Failing test: a `worsened` verification triggers the rollback plan
  automatically.
- **T-015** Rollback verified through the same mechanism.
- **T-016** Failing test: a failed rollback escalates at the highest severity,
  records both failures, and suspends autonomous action on the resource.
- **T-017** Suspension visible and clearable by a human; test autonomy resumes
  only after clearing.
- **T-018** A rollback no longer possible says so explicitly.
- **T-019** Failing test: an action interrupted by the kill switch reaches a
  consistent state, never half-applied.
- **T-020** Assert rollback does *not* fire on `ineffective` or `inconclusive`.

## Phase 4 — Effectiveness

- **T-021** Record effectiveness per resource, capability and condition.
- **T-022** Query surface by each dimension; benchmark over a year of history.
- **T-023** Historical effectiveness available to a proposal and visible to a
  reviewer.
- **T-024** Route effectiveness into episodic memory and strategy synthesis;
  assert no parallel learning store is introduced.

## Phase 5 — Recurrence

- **T-025** Windowed counting per resource and capability; restart-durable.
- **T-026** Failing test: the fourth identical remediation in the window raises a
  recurring-problem item.
- **T-027** Recurring-problem item distinct from an incident, closed by a change.
- **T-028** Suppression of autonomous repetition once raised; visible and
  clearable.
- **T-029** Count and window configurable per capability through the config
  service.

## Phase 6 — Concurrency and edge cases

- **T-030** Per-resource serialisation; the declared behaviour for the second
  arrival, tested both ways.
- **T-031** Failing test: a resource absent between action and verification
  yields `inconclusive`, not `effective`.
- **T-032** A remediation that succeeds but trips a different detector — assert
  the behaviour is declared.
- **T-033** An effect visible only in a signal other than the one that fired.

## Phase 7 — Surfaces

- **T-034** Timeline entries for proposal, resolution, execution, verification,
  rollback and recurrence, each with actor and cause.
- **T-035** Failing test: the audit record for one action carries the whole
  chain, asserted field by field.
- **T-036** Gateway endpoints for verification state, effectiveness history,
  recurring problems and suspension clearing. Contract tests.
- **T-037** CLI commands for the same.
- **T-038** Console: awaiting-verification state, before-and-after values,
  effectiveness history on the resource, recurring problems as their own view.

## Definition of done

- SC-001 through SC-011 each proven by a named test.
- Restart durability proven with a real restart.
- `make verify` green.
