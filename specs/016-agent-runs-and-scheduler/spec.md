# Feature 016 — Agent Runs, Traces, and Scheduler

- **Wave:** 3 — Control Plane
- **Branch:** `feat/016-agent-runs-and-scheduler`
- **Status:** Draft
- **Depends on:** 004, 005, 006, 013, 014
- **Blocks:** 020, 021, 028

## Summary

Two things that share a lifecycle: the durable record of every investigation
(replayable turn by turn, tool call by tool call) and the scheduler that runs
investigations on a recurring basis with distributed claiming and concurrency
limits.

## User scenarios

### Primary story

An engineer opens an investigation that ran overnight and replays it: each thought,
each capability call with arguments and results, each sub-agent dispatch, each
guardrail action, each budget eviction. Separately, a nightly DR-validation
investigation runs on a schedule across three agent replicas without ever running
twice.

### Acceptance scenarios

1. **Given** an investigation runs, **when** it completes, **then** the run, its
   turns, its capability calls, and its evidence are durably persisted.
2. **Given** a persisted run, **when** it is replayed, **then** the reconstruction
   is complete enough to understand every decision, with no missing steps.
3. **Given** a run in progress, **when** a client subscribes, **then** it receives
   live events and, on reconnect, the events it missed.
4. **Given** a recurring job configured, **when** its schedule fires, **then**
   exactly one replica claims and executes it.
5. **Given** a claiming replica dies mid-execution, **when** its lease expires,
   **then** another replica may claim the job and the partial run is marked
   interrupted.
6. **Given** concurrency limits, **when** more jobs are due than the limit allows,
   **then** execution queues rather than overwhelming the system.
7. **Given** a scheduled job whose team configuration changed, **when** it next
   runs, **then** it uses the current effective configuration.
8. **Given** a trace containing sensitive content, **when** it is persisted,
   **then** guardrails have already filtered it.
9. **Given** retention policy, **when** it runs, **then** traces older than the
   window are removed while their runs' summary records and audit entries remain.

### Edge cases

- A run that crashes before writing its final state.
- A trace whose tool result payload is very large.
- Clock drift across replicas affecting schedule firing.
- A schedule whose cron expression would fire during a DST transition.
- A job whose team was deleted.
- Replay of a run whose capability no longer exists.
- Two schedules configured to fire simultaneously with a concurrency limit of one.

## Requirements

### Functional

**Run and trace persistence**

- **FR-001** Every investigation MUST create a run record with: identity, team,
  trigger source, principal, start and end time, status, and outcome summary.
- **FR-002** Each turn MUST persist: model, prompt token count, completion token
  count, cost, duration, and the capability calls it produced.
- **FR-003** Each capability call MUST persist: name, arguments, result, duration,
  outcome, evidence produced, and error classification.
- **FR-004** Sub-agent dispatches MUST persist as nested runs linked to their
  parent, with their own turns and calls.
- **FR-005** Guardrail actions, masking actions, and budget evictions MUST be
  persisted as trace events.
- **FR-006** Trace content MUST pass the guardrail engine before persistence.
- **FR-007** Large payloads MUST be stored with a size cap and an explicit
  truncation marker — never silently cut.
- **FR-008** A run that crashes MUST leave a run record marked `interrupted` with
  whatever was captured.

**Replay**

- **FR-009** A persisted run MUST be replayable into the same view a live client
  saw.
- **FR-010** Replay MUST work for a run whose capabilities have since changed or
  been removed, degrading to recorded metadata.
- **FR-011** Replay MUST expose the selection rationale for each turn, so a
  reviewer can see why capabilities were chosen.

**Live streaming and reconnection**

- **FR-012** A client MUST be able to subscribe to a live run and receive events
  as they occur.
- **FR-013** On reconnect, a client MUST receive events it missed, identified by a
  cursor.
- **FR-014** Multiple clients MUST be able to observe the same run.

**Scheduler**

- **FR-015** Recurring investigations MUST be configurable with a cron expression
  and a timezone.
- **FR-016** Execution MUST use distributed claiming with leases, so exactly one
  replica runs a due job.
- **FR-017** An expired lease MUST make the job claimable again, and the abandoned
  run MUST be marked interrupted.
- **FR-018** Concurrency MUST be limited globally and per team by named constants.
- **FR-019** A job MUST resolve current effective configuration at execution time,
  not at configuration time.
- **FR-020** Misfires (jobs due while the system was down) MUST follow a
  configurable policy: skip, run once, or run all.
- **FR-021** DST transitions MUST be handled explicitly so a job neither
  double-fires nor silently skips.
- **FR-022** A job whose team was deleted MUST be disabled with a recorded reason,
  not silently dropped.
- **FR-023** Job execution results MUST be visible in the same run history as
  interactive investigations.

**Retention**

- **FR-024** Trace retention MUST be configurable per data class.
- **FR-025** Removing a trace MUST preserve the run summary record and all audit
  entries.

### Key entities

| Entity | Description |
|---|---|
| **AgentRun** | One investigation execution with identity, trigger, principal, status |
| **Turn** | One model call with usage, cost, and the calls it produced |
| **CapabilityCall** | One capability execution with arguments, result, and outcome |
| **TraceEvent** | Guardrail, masking, budget, or lifecycle occurrence |
| **ScheduledJob** | A recurring investigation definition |
| **Claim** | A lease binding a job execution to a replica |
| **Cursor** | A client's position in a run's event stream |

## Success criteria

- **SC-001** A replayed run is complete: a test compares the replayed view against
  the live-observed view and they match.
- **SC-002** A scheduled job fires exactly once across three concurrent replicas
  over a hundred firings.
- **SC-003** A replica killed mid-execution releases its job within the lease
  window, and the abandoned run is marked interrupted.
- **SC-004** A client disconnecting and reconnecting mid-run receives every missed
  event exactly once.
- **SC-005** A run that crashes leaves a usable interrupted record.
- **SC-006** Replay works for a run referencing a since-removed capability.
- **SC-007** DST transitions produce neither a double fire nor a silent skip —
  verified for both spring-forward and fall-back.
- **SC-008** Retention removes traces while preserving run summaries and audit
  entries.

## Out of scope

- The runtime that produces the events (feature 004)
- REST and SSE transport (feature 020)
- Replay UI (feature 021)
- Evaluation over traces (feature 028)

## Clarifications

| Question | Resolution |
|---|---|
| Why is trace completeness a hard requirement rather than best-effort? | Constitution Article I. An investigation whose reasoning cannot be reconstructed cannot be audited, evaluated, or learned from. The trace is the evidence. |
| Why lease-based claiming rather than a lock? | Leases survive replica death. A lock held by a crashed process blocks the job until manual intervention, which is exactly the wrong behaviour for a scheduled DR validation. |
| Are scheduled runs different from interactive ones? | Only in trigger and principal. They produce the same runs, traces, memory episodes, and reports (FR-023), so nothing downstream needs to distinguish them. |
| How large can a trace get? | Bounded by FR-007's payload cap with explicit truncation markers, and by retention (FR-024). A truncated payload that says so is acceptable; a silently cut one is not. |
