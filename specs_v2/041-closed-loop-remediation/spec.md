# Feature 041 — Closed-Loop Remediation

- **Wave:** 10 — Autonomous operation
- **Branch:** `feat/041-closed-loop-remediation`
- **Status:** Draft
- **Depends on:** 017, 038, 039, 040

## Summary

Acting, then finding out whether it worked, then dealing with the answer.

The first wave shipped the act half: an executor, a gating check, a rollback plan
per applier, an audit line, a notification. What it does not have is the loop —
nothing measures the effect, nothing rolls back automatically when the effect is
absent, nothing notices that this is the fourth time this week, and nothing
learns that the remediation which always works on this resource should be tried
first next time.

Without the loop, autonomy is a system that presses buttons and reports that it
pressed them. This feature makes the report say whether it helped.

## User scenarios

### Primary story

A container's filesystem fills. The system clears the reclaimable space, waits,
re-reads the signal, and confirms it dropped to sixty per cent. The incident
closes with the action, the before and after values, and the time it took.

The next week the same container fills again. It clears again, and this time the
signal does not move. The action is rolled back where rollback means anything,
the incident escalates to a human with "I tried this, it did not work, here is
what I saw", and the system records that this remediation does not work on this
resource — so next time it proposes something else, and says why.

By the fourth occurrence in a month, the system stops treating it as an incident
to fix and raises it as a recurring problem that needs a change, not a restart.

### Acceptance scenarios

1. **Given** an executed action, **when** it completes, **then** the signal it was
   meant to change is re-read after a declared settle period and compared to its
   value before.
2. **Given** a verification that shows the condition cleared, **when** it
   completes, **then** the action is recorded as effective, with before and after
   values.
3. **Given** a verification that shows no improvement, **when** it completes,
   **then** the action is recorded as ineffective and the incident is escalated
   rather than closed.
4. **Given** an action that made the signal worse, **when** verification detects
   it, **then** the rollback plan is executed automatically, and the rollback is
   itself verified.
5. **Given** a rollback that fails, **when** it fails, **then** the incident is
   escalated at the highest severity with both failures, and further autonomous
   action on that resource is suspended until a human clears it.
6. **Given** the same remediation applied to the same resource four times in a
   declared window, **when** the fourth occurs, **then** a recurring-problem item
   is raised, distinct from the incidents, and autonomous repetition is
   suppressed.
7. **Given** a remediation with a history on a resource, **when** a new incident
   proposes it, **then** its historical effectiveness on that resource is
   available to the decision.
8. **Given** an action that cannot be verified — no signal maps to it, **when**
   it is proposed, **then** that is stated, and the deployment's policy decides
   whether an unverifiable action may be autonomous.
9. **Given** an action executing when the kill switch engages, **when** it is
   mid-flight, **then** it completes or rolls back to a consistent state; it MUST
   NOT be abandoned half-applied.
10. **Given** any action, **when** it is complete, **then** the audit record
    carries: what was proposed, what resolved the level, what executed, what was
    verified, what the values were, and what happened next.
11. **Given** a verification still pending, **when** the console renders the
    incident, **then** it says the action is awaiting verification rather than
    saying it succeeded.

### Edge cases

- A signal whose settle period is longer than the run's wall-clock ceiling.
- A signal that recovers for reasons unrelated to the action.
- An action whose effect is only visible in a different signal from the one that
  fired.
- A rollback that is not possible because the world moved on.
- Two remediations in flight against the same resource.
- A resource going absent between action and verification.
- The deployment restarting between action and verification.
- A remediation that succeeds but causes a different detector to fire.

## Requirements

### Functional

**Verification**

- **FR-001** Every remediation capability MUST declare the signals its effect
  should be visible in, and a settle period before those signals are meaningful.
- **FR-002** After execution, the declared signals MUST be re-read after the
  settle period and compared to the values recorded immediately before.
- **FR-003** Verification MUST survive a deployment restart between action and
  check; it MUST be a durable scheduled obligation, not an in-process wait.
- **FR-004** A verification outcome MUST be one of: effective, ineffective,
  worsened, inconclusive, or unverifiable — a closed set.
- **FR-005** `inconclusive` MUST be distinct from `effective`. A signal that did
  not move enough to tell MUST NOT be reported as success.
- **FR-006** A capability with no declared verification signal MUST report
  `unverifiable`, and whether such an action may run autonomously MUST be a
  policy decision, not a default.
- **FR-007** Until verification completes, the action's state MUST be
  "awaiting verification" everywhere it is displayed.

**Rollback**

- **FR-008** A `worsened` verification MUST trigger the action's rollback plan
  automatically.
- **FR-009** A rollback MUST itself be verified, through the same mechanism.
- **FR-010** A failed rollback MUST escalate at the highest severity, MUST record
  both failures, and MUST suspend further autonomous action on that resource
  until a human clears the suspension.
- **FR-011** A rollback that is no longer possible MUST say so explicitly rather
  than failing silently or being skipped.
- **FR-012** An action interrupted by the kill switch MUST reach a consistent
  state — completed or rolled back — never half-applied.

**Effectiveness history**

- **FR-013** Every action MUST record its effectiveness against the resource, the
  capability, and the condition that prompted it.
- **FR-014** Effectiveness history MUST be queryable by resource, by capability,
  and by condition.
- **FR-015** When a remediation is proposed, its historical effectiveness in that
  context MUST be available to the proposing agent and visible to a human
  reviewer.
- **FR-016** History MUST feed the existing episodic memory and strategy
  synthesis rather than forming a parallel learning store.

**Recurrence**

- **FR-017** The same remediation on the same resource, more than a declared
  number of times in a declared window, MUST raise a recurring-problem item.
- **FR-018** A recurring-problem item MUST be distinct from an incident: it names
  a pattern, not an occurrence, and it is closed by a change, not by a
  remediation.
- **FR-019** Autonomous repetition MUST be suppressed once a recurrence is raised,
  and the suppression MUST be visible and clearable.
- **FR-020** Recurrence detection MUST survive restarts and MUST be per resource
  and capability, not global.

**Concurrency and safety**

- **FR-021** Two remediations MUST NOT execute against the same resource
  concurrently; the second MUST wait or be refused, and which it does MUST be
  declared.
- **FR-022** A resource that goes absent between action and verification MUST
  produce `inconclusive`, not `effective`.
- **FR-023** Every step — proposal, resolution, execution, verification,
  rollback, recurrence — MUST appear on the incident timeline and in the audit
  log with its actor and its cause.

### Non-functional

- **NFR-001** Verification obligations MUST be durable, claimed with a lease, and
  safe across replicas.
- **NFR-002** A settle period MUST NOT hold a run open; the run ends and the
  verification happens independently.
- **NFR-003** Effectiveness queries MUST answer within a declared budget over a
  year of history.
- **NFR-004** Nothing here may hold a credential; execution goes through the
  existing executor and the credential proxy.

## Success criteria

- **SC-001** An effective action closes its incident with before and after
  values.
- **SC-002** An ineffective action escalates rather than closing, with what was
  tried and what was seen.
- **SC-003** A worsened action rolls back automatically and verifies the
  rollback.
- **SC-004** A failed rollback escalates at the highest severity and suspends
  autonomy on the resource.
- **SC-005** Verification survives a deployment restart between action and check.
- **SC-006** An inconclusive verification is never reported as success.
- **SC-007** The fourth identical remediation in the window raises a
  recurring-problem item and suppresses further autonomous repetition.
- **SC-008** Historical effectiveness is available to a proposal and visible to a
  reviewer.
- **SC-009** Concurrent remediations against one resource are serialised or
  refused, as declared.
- **SC-010** An action interrupted by the kill switch reaches a consistent state.
- **SC-011** The audit record for one action carries the whole chain, asserted
  field by field.

## Out of scope

- Deciding whether to act — feature 040.
- Provider-specific remediations — feature 046.
- Changing the executor's own contract, which feature 017 owns.
