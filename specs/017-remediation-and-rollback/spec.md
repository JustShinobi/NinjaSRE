# Feature 017 — Remediation and Rollback

- **Wave:** 4 — Action Governance
- **Branch:** `feat/017-remediation-and-rollback`
- **Status:** Draft
- **Depends on:** 003, 004, 009, 012, 014, 015, 016
- **ADRs:** [0006](../../docs/adr/0006-read-only-by-default.md)

## Summary

Where the system is permitted to change production — and every mechanism that
stops it from doing so by accident. Read-only is the default. A write requires an
explicit human approval and a rollback plan recorded **before** execution.
Autonomy is opt-in per action type, allow-listed, and killable instantly.

## User scenarios

### Primary story

The agent concludes a pod is OOMKilled and proposes increasing its memory limit.
An approval request appears in the incident's Slack thread showing the target,
current state, proposed change, blast radius from the topology graph, and the
rollback plan. The on-call engineer approves. The change applies, is verified, and
is recorded with a one-click rollback available for the next hour.

### Acceptance scenarios

1. **Given** a capability with `side_effect_level` above `read_sensitive`, **when**
   the agent requests it, **then** execution suspends and an approval request is
   raised.
2. **Given** an approval request, **when** it is presented, **then** it shows
   target, current state, proposed change, blast radius, and the rollback plan.
3. **Given** an action with no derivable rollback plan, **when** approval is
   requested, **then** the request is refused unless the operator explicitly
   waives the requirement, and the waiver is audited.
4. **Given** approval is granted, **when** the action executes, **then** the
   rollback plan is persisted **before** execution begins.
5. **Given** an executed action, **when** rollback is invoked, **then** the
   recorded plan is applied and the result verified.
6. **Given** approval is denied or expires, **when** the loop resumes, **then** the
   agent receives a structured denial and continues reasoning without the action.
7. **Given** an action type on the autonomous allow-list, **when** the agent
   requests it within the allow-list's conditions, **then** it executes without
   approval and is fully audited.
8. **Given** the kill switch is activated, **when** any write is requested,
   **then** it is refused immediately regardless of allow-list or pending
   approval.
9. **Given** an executed action, **when** post-execution verification runs, **then**
   the actual resulting state is compared against the intended state and any
   divergence is reported.
10. **Given** a capability with no declared `side_effect_level`, **when** the
    registry builds, **then** the build fails — absence is never treated as read.

### Edge cases

- An approval granted after the incident already resolved itself.
- A rollback whose target state no longer exists.
- Concurrent approvals for conflicting actions on the same target.
- An action that partially succeeds (three of five pods restarted).
- A rollback that itself fails.
- The approver losing permission between request and decision.
- An allow-listed action whose conditions were met at request time but not at
  execution time.

## Requirements

### Functional

**Classification**

- **FR-001** Every capability MUST declare `side_effect_level`; the registry MUST
  fail the build on absence (enforced in feature 003, re-asserted here).
- **FR-002** Levels MUST be: `read`, `read_sensitive`, `write_reversible`,
  `write_irreversible`, `destructive`.
- **FR-003** Policy MUST map levels to approval requirements, configurable per org
  (feature 015), with a default requiring approval at `write_reversible` and above.

**Approval**

- **FR-004** A gated action MUST suspend the loop and raise an approval request
  through feature 015's machinery.
- **FR-005** The request MUST include: target identity, current observed state,
  proposed change, blast radius from the topology graph, rollback plan, and the
  evidence that motivated it.
- **FR-006** Approval MUST have a shorter expiry than configuration changes,
  appropriate to incident timescales, with a default-deny outcome.
- **FR-007** A denial or expiry MUST return a structured result the agent can
  reason about, and the investigation MUST continue.
- **FR-008** Approval permission MUST be re-checked at decision time.

**Rollback**

- **FR-009** Every write-level capability MUST provide a rollback-plan generator.
- **FR-010** The plan MUST be generated and persisted **before** execution.
- **FR-011** An action with no derivable plan MUST be refused unless explicitly
  waived, with the waiver audited.
- **FR-012** Rollback MUST be invocable from every surface for a configurable
  window after execution.
- **FR-013** Rollback MUST verify its own result and report failure loudly.
- **FR-014** A rollback whose target no longer matches the recorded state MUST
  refuse and report, rather than applying blindly.

**Execution**

- **FR-015** Execution MUST run in the configured sandbox profile through the
  credential proxy.
- **FR-016** Partial success MUST be recorded per sub-target, and the rollback plan
  MUST cover only what actually changed.
- **FR-017** Post-execution verification MUST compare actual against intended
  state and report divergence.
- **FR-018** Concurrent actions on the same target MUST be serialised, and a
  conflicting pending action MUST be re-evaluated.

**Autonomy**

- **FR-019** An autonomous allow-list MUST be opt-in per action type, scoped per
  team.
- **FR-020** An allow-list entry MUST support conditions: target patterns, time
  windows, maximum blast radius, and a rate limit.
- **FR-021** Conditions MUST be re-evaluated at execution time, not only at request
  time.
- **FR-022** A kill switch MUST refuse all writes immediately, overriding
  allow-lists and pending approvals.
- **FR-023** Autonomous executions MUST be audited identically to approved ones and
  MUST notify the team.

**Capability set**

- **FR-024** The MVP MUST ship these remediation capabilities, all gated:
  restart workload, rollback deployment, scale workload, cordon or drain node,
  update resource limits, toggle feature flag, and clear cache.
- **FR-025** Each MUST provide: current-state reader, change applier, rollback
  generator, and post-execution verifier.

### Key entities

| Entity | Description |
|---|---|
| **RemediationAction** | A proposed production change with target, intent, and evidence |
| **RollbackPlan** | The recorded steps to reverse an action, generated pre-execution |
| **ExecutionRecord** | Outcome, per-sub-target results, verification, timings |
| **AllowListEntry** | An action type plus conditions permitting autonomous execution |
| **KillSwitch** | Team- and org-scoped immediate write refusal |
| **StateSnapshot** | Observed target state before and after execution |

## Success criteria

- **SC-001** No write-level capability can execute without a recorded approval or a
  matching allow-list entry — asserted by attempting it through every entry point.
- **SC-002** A rollback plan exists and is persisted before execution for every
  executed write, verified across the whole remediation capability set.
- **SC-003** The kill switch refuses writes immediately, including one already
  approved and about to execute.
- **SC-004** Post-execution verification detects an induced divergence between
  intended and actual state.
- **SC-005** A partially-successful action produces a rollback plan covering only
  what changed.
- **SC-006** An allow-listed action whose conditions stopped holding between
  request and execution is refused.
- **SC-007** Rollback refuses when the target no longer matches the recorded state.
- **SC-008** Denial or expiry lets the investigation continue and reach a
  conclusion.

## Out of scope

- Approval workflow machinery (feature 015 — reused here)
- Surface rendering of approvals (features 021, 022)
- Sandbox implementation (feature 009)

## Clarifications

| Question | Resolution |
|---|---|
| Why require a rollback plan before execution rather than after? | A plan written after a failure is authored under pressure with incomplete information. Written before, it is a design artefact the approver can evaluate — and its absence is itself a signal the action is riskier than it appears. |
| Is the autonomous allow-list a contradiction of read-only by default? | No — it is an explicit, scoped, revocable exception a team opts into per action type, with conditions re-evaluated at execution (FR-021) and a kill switch above it (FR-022). The default remains deny. |
| What if rollback fails? | FR-013: it reports loudly. There is no automatic retry or escalation, because a failed rollback needs human judgement, not more automation. |
| Why a shorter approval expiry than for config changes? | Incident timescales. An approval that arrives forty minutes late may apply to a system that has already changed. Default-deny on expiry is the safe direction. |
