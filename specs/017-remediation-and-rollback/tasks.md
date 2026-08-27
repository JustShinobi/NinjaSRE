# Tasks — 017 Remediation and Rollback

## Phase 1 — Gating proofs (test-first)

- **T001** Write the no-unapproved-write test: attempt every write-level capability
  through every entry point without approval or allow-list (SC-001). Red.
- **T002** Write the kill-switch immediacy test, including an already-approved
  action about to execute (SC-003). Red.
- **T003** Write the condition re-evaluation test: conditions hold at request time,
  not at execution time (SC-006). Red.
- **T004** Write the pre-execution plan persistence test across the whole
  remediation set (SC-002). Red.
- **T005** Write the divergence-detection test (SC-004). Red.
- **T006** Write the partial-success rollback scoping test (SC-005). Red.
- **T007** Write the rollback target-mismatch refusal test (SC-007). Red.
- **T008** Write the denial-continues-investigation test (SC-008). Red.
- **T009** Add remediation constants to `config/constants/security.py`: approval
  expiry, rollback window, autonomy rate limits, blast-radius ceiling.

## Phase 2 — Classification and gating

- **T010** `platform/remediation/models.py`: `RemediationAction`, `RollbackPlan`,
  `ExecutionRecord`, `StateSnapshot`.
- **T011** Level-to-approval-requirement mapping from org policy, default gating at
  `write_reversible` and above (FR-003).
- **T012** `platform/remediation/gating.py`: `pre_tool_use` binding that classifies
  and suspends (FR-004).
- **T013** Structured denial on refusal, investigation continues (FR-007); confirm
  SC-008.
- **T014** Re-assert the registry build failure on missing `side_effect_level`
  (FR-001).

## Phase 3 — Request construction

- **T015** `platform/remediation/request.py`: assemble target identity, current
  observed state, proposed change (FR-005).
- **T016** Blast-radius query against the topology graph at request time.
- **T017** Attach the evidence that motivated the action.
- **T018** Remediation-specific approval expiry with default-deny (FR-006).
- **T019** Decision-time permission re-check (FR-008), reusing feature 015.
- **T020** Conflicting-pending-action re-evaluation on the same target (FR-018).

## Phase 4 — Rollback

- **T021** `rollback/generator.py`: per-capability plan generation dispatch
  (FR-009).
- **T022** Persist the plan **before** execution begins (FR-010); confirm SC-002.
- **T023** No-derivable-plan path: refuse unless explicitly waived; audit the
  waiver (FR-011).
- **T024** `rollback/executor.py`: apply a recorded plan (FR-012).
- **T025** `rollback/verification.py`: refuse when the target no longer matches the
  recorded state (FR-014); confirm SC-007.
- **T026** Rollback result verification with loud failure reporting (FR-013).
- **T027** Rollback invocable from every surface within the configured window.

## Phase 5 — Execution and verification

- **T028** `platform/remediation/execution.py`: run through the sandbox profile and
  the credential proxy (FR-015).
- **T029** Per-target advisory lock serialising concurrent actions (FR-018).
- **T030** Partial-success recording per sub-target (FR-016).
- **T031** Rollback plan scoped to what actually changed; confirm SC-005.
- **T032** `platform/remediation/verification.py`: post-execution intended-versus-
  actual comparison with divergence reporting (FR-017); confirm SC-004.
- **T033** Execution record persisted into the run trace.

## Phase 6 — Autonomy

- **T034** `autonomy/allow_list.py`: entries scoped per team and action type
  (FR-019).
- **T035** Conditions: target pattern, time window, maximum blast radius, rate
  limit, environment (FR-020).
- **T036** `autonomy/evaluation.py`: conjunctive condition evaluation at execution
  time (FR-021); confirm SC-006.
- **T037** `autonomy/kill_switch.py`: immediate refusal overriding allow-lists and
  pending approvals (FR-022); confirm SC-003.
- **T038** Kill switch scoped at team and org level.
- **T039** Autonomous execution auditing identical to approved execution, plus
  team notification (FR-023).
- **T040** Confirm SC-001 no-unapproved-write green.

## Phase 7 — Capability set

- **T041** `capabilities/tools/remediation/restart_workload/`: read_state, apply,
  rollback, verify.
- **T042** [P] `rollback_deployment/`.
- **T043** [P] `scale_workload/`.
- **T044** [P] `cordon_drain_node/`.
- **T045** [P] `update_resource_limits/`.
- **T046** [P] `toggle_feature_flag/`.
- **T047** [P] `clear_cache/` — exercises the no-derivable-plan waiver path.
- **T048** Contract test suite parameterised over the remediation set asserting all
  four components exist and behave.
- **T049** Confirm SC-002 across the whole set.
- **T050** Operator documentation: side-effect levels, approval configuration,
  allow-list design, kill-switch usage, rollback procedure.
- **T051** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] No write executes without approval or a matching allow-list entry (SC-001)
- [ ] Every executed write had a persisted plan beforehand (SC-002)
- [ ] Kill switch refuses immediately, overriding everything (SC-003)
- [ ] Verification detects induced divergence (SC-004)
- [ ] Partial success produces a correctly-scoped plan (SC-005)
- [ ] Allow-listed action refused when conditions lapse (SC-006)
- [ ] Rollback refuses on target mismatch (SC-007)
- [ ] Denial lets the investigation conclude (SC-008)
- [ ] `make verify` green
