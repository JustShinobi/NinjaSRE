# Tasks — 016 Agent Runs, Traces, and Scheduler

## Phase 1 — Contracts and proofs (test-first)

- **T001** Write the replay-completeness test: capture the live-observed view and
  the replayed view of the same run; assert equality (SC-001). Red.
- **T002** Write the exactly-once claiming test: three replicas, one hundred
  firings, one execution each (SC-002). Red.
- **T003** Write the lease-expiry test: kill a replica mid-execution, assert
  re-claim and interrupted marking (SC-003). Red.
- **T004** Write the reconnection test: disconnect mid-run, reconnect with a
  cursor, assert every missed event exactly once (SC-004). Red.
- **T005** Write the crash-recovery test: run crashes, leaves a usable interrupted
  record (SC-005). Red.
- **T006** Write the removed-capability replay test (SC-006). Red.
- **T007** Write DST tests for spring-forward and fall-back (SC-007). Red.
- **T008** Add run and scheduler constants to `config/constants/`: payload caps,
  lease duration, heartbeat interval, global and per-team concurrency, retention
  windows.

## Phase 2 — Recording

- **T009** `platform/runs/recorder.py`: run record with identity, team, trigger,
  principal, times, status, summary (FR-001).
- **T010** Turn persistence with model, token counts, cost, duration, selection
  rationale (FR-002).
- **T011** Capability-call persistence with arguments, result, duration, outcome,
  evidence, error class (FR-003).
- **T012** Nested sub-agent runs linked to the parent (FR-004).
- **T013** Trace events for guardrail actions, masking actions, budget evictions
  (FR-005).
- **T014** Guardrail filtering before persistence (FR-006).
- **T015** `platform/runs/truncation.py`: payload caps with explicit truncation
  markers (FR-007).
- **T016** Interrupted-run marking on crash (FR-008); confirm SC-005.

## Phase 3 — Replay

- **T017** `platform/runs/replay.py`: reconstruct the client view from the event
  log (FR-009).
- **T018** Graceful degradation for removed capabilities using recorded metadata
  (FR-010); confirm SC-006.
- **T019** Expose per-turn selection rationale in replay (FR-011).
- **T020** Confirm SC-001 replay-completeness green.

## Phase 4 — Streaming

- **T021** Append-only event log per run with a monotonic cursor
  (`platform/runs/cursor.py`).
- **T022** `platform/runs/stream.py`: in-process pub/sub attach (FR-012).
- **T023** Cross-replica bridge via Postgres `LISTEN`/`NOTIFY`.
- **T024** Reconnect catch-up: replay from cursor, then attach live (FR-013);
  confirm SC-004.
- **T025** Multi-client observation of one run (FR-014).
- **T026** Backpressure handling for a slow consumer.

## Phase 5 — Scheduler core

- **T027** `platform/scheduler/models.py`: `ScheduledJob`, `Claim`.
- **T028** `platform/scheduler/cron.py`: expression evaluation with IANA timezone
  (FR-015).
- **T029** DST handling: spring-forward shift, fall-back single fire (FR-021);
  confirm SC-007.
- **T030** `platform/scheduler/claiming.py`: conditional lease insert keyed on
  `(job_id, fire_time)` (FR-016).
- **T031** Heartbeat renewal while executing.
- **T032** Confirm SC-002 exactly-once across three replicas.
- **T033** `platform/scheduler/executor.py`: run a claimed job through the
  pipeline, resolving effective configuration at execution time (FR-019).
- **T034** Scheduled runs produce the same runs, traces, episodes, and reports as
  interactive ones (FR-023).

## Phase 6 — Scheduler robustness

- **T035** `platform/scheduler/concurrency.py`: global and per-team semaphores
  (FR-018).
- **T036** Queueing rather than overwhelming when limits are reached.
- **T037** `platform/scheduler/misfire.py`: skip / run-once / run-all policy
  (FR-020).
- **T038** `platform/scheduler/reaper.py`: expired-lease detection, interrupted
  marking, re-claimability (FR-017); confirm SC-003.
- **T039** Deleted-team handling: job disabled with a recorded reason (FR-022).
- **T040** Schedule management API for the console.

## Phase 7 — Retention and integration

- **T041** `platform/runs/retention.py`: per-class retention (FR-024).
- **T042** Removal preserves run summaries and audit entries (FR-025); confirm
  SC-008.
- **T043** Unified run history across interactive and scheduled runs.
- **T044** Run history query API: filter by team, status, trigger, time range,
  outcome.
- **T045** Cost and usage aggregation per run, per team, per period.
- **T046** Operator documentation: trace retention, schedule configuration,
  misfire policy, concurrency tuning.
- **T047** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Replayed view matches the live view (SC-001)
- [ ] Exactly-once firing across three replicas over 100 firings (SC-002)
- [ ] Killed replica releases its job; run marked interrupted (SC-003)
- [ ] Reconnection delivers missed events exactly once (SC-004)
- [ ] Crashed runs leave usable interrupted records (SC-005)
- [ ] Replay survives removed capabilities (SC-006)
- [ ] DST produces neither double fire nor silent skip (SC-007)
- [ ] Retention preserves summaries and audit (SC-008)
- [ ] `make verify` green
