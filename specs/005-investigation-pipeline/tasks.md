# Tasks — 005 Investigation Pipeline

## Phase 1 — State and contracts (test-first)

- **T001** `core/state/evidence.py`: `EvidenceEntry` with source, capability,
  arguments, payload, timestamp, provenance, value hints for budget eviction.
- **T002** `core/state/slices.py`: `ChatSlice`, `InvestigationSlice`,
  `EvidenceSlice`, `AccountingSlice`, `ApprovalSlice`, `MemorySlice` — frozen
  dataclasses.
- **T003** `core/state/agent_state.py`: envelope plus `apply_state_updates` as the
  single merge path.
- **T004** Stage protocol: `async (state) -> StateUpdates`, docstring-only body.
- **T005** Declare slice ownership per stage in one table module.
- **T006** Write the slice-purity test (red): no stage writes outside its declared
  slice (SC-004).
- **T007** `core/pipeline/state_factory.py`: initial state from a raw input plus
  team context.

## Phase 2 — Streaming

- **T008** `core/pipeline/streaming.py`: typed events — `stage_start`,
  `stage_end`, `thought`, `tool_start`, `tool_end`, `subagent_start`,
  `subagent_end`, `evidence`, `question`, `approval_request`, `message_queued`,
  `result`, `error` (FR-028).
- **T009** Emission points wired into `lifecycle.py` and the runtime bridge.
- **T010** Serialisation contract test: every event round-trips to JSON.
- **T011** Replay test: persisted events reconstruct the investigation view
  (SC-005).

## Phase 3 — Intake

- **T012** `core/domain/alerts/normalisation.py`: per-source adapters for
  Alertmanager, PagerDuty, Datadog, Grafana, Sentry, Opsgenie, generic webhook,
  plain text (FR-011).
- **T013** Contract test per adapter with a real payload fixture.
- **T014** `stages/intake/node.py`: one LLM call producing classification plus
  extracted fields (FR-008, FR-009).
- **T015** Noise threshold as a named constant; every decision recorded with
  confidence.
- **T016** Short-circuit on noise before any capability executes (FR-004); confirm
  SC-001.
- **T017** `stages/intake/window.py`: incident window with start, end, confidence
  (FR-010).
- **T018** Fallback when the window cannot be derived: a documented default span
  recorded as low confidence.
- **T019** `stages/intake/dedup.py`: link to a recent incident within the window
  rather than re-investigating (FR-012).
- **T020** Test: an alert storm of N duplicates produces one investigation and
  N−1 links.

## Phase 4 — Resolution and planning

- **T021** `stages/resolve_integrations.py`: build the `ResolvedCatalogue` from
  team configuration (FR-006).
- **T022** Zero-integration path producing an actionable outcome naming the
  integrations that would have served this alert source (FR-007); confirm SC-006.
- **T023** `stages/plan_evidence.py`: score, take top `tool_budget`, produce
  `PlannedAction` entries (FR-013).
- **T024** Written plan rationale recorded in state (FR-014).
- **T025** Test: an empty or low-confidence plan does not block the loop (FR-015).

## Phase 5 — Gathering

- **T026** `stages/gather_evidence.py`: invoke the canonical runtime with plan,
  catalogue, and incident context (FR-016).
- **T027** Evidence recording with full provenance (FR-017).
- **T028** Incident-window enforcement on time-bounded capability calls (FR-018).
- **T029** Bridge runtime events onto the pipeline stream.

## Phase 6 — Diagnosis

- **T030** `core/domain/diagnosis/taxonomy.py`: versioned `RootCauseCategory`
  registry with the initial vocabulary (FR-023).
- **T031** Test: the taxonomy version is recorded in every diagnosis.
- **T032** `stages/diagnose/models.py`: `Diagnosis` model with all fields from
  FR-020.
- **T033** `stages/diagnose/node.py`: structured-output call scoped to conclusion
  plus evidence (FR-019).
- **T034** `stages/diagnose/validation.py`: demote any claim not referencing a
  present evidence entry (FR-021).
- **T035** Corpus-wide assertion: every `validated` claim has backing (SC-003).
- **T036** `stages/diagnose/fallback.py`: documented degraded parser, its use
  recorded (FR-022).
- **T037** Test: forcing structured-output failure yields a usable fallback
  diagnosis with the fallback flag set.

## Phase 7 — Delivery and integration

- **T038** `stages/deliver.py`: format per destination and ship to all configured
  destinations (FR-024).
- **T039** Per-destination failure isolation with recording (FR-025).
- **T040** Fire `on_run_end` exactly once (FR-026); test the exactly-once property
  including on the error path.
- **T041** `core/pipeline/lifecycle.py`: stage ordering, merge, stage-identity
  error recording and re-raise (FR-001, FR-002, FR-003).
- **T042** Confirm the slice-purity test green (SC-004).
- **T043** End-to-end run against a synthetic scenario with mock backends; assert
  category match (SC-002).
- **T044** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Noise input costs zero capability executions (SC-001)
- [ ] Synthetic scenario produces a category-matching diagnosis (SC-002)
- [ ] Every validated claim is evidence-backed across the corpus (SC-003)
- [ ] Stage slice purity enforced (SC-004)
- [ ] Event replay reconstructs the investigation (SC-005)
- [ ] Zero-integration outcome is actionable and specific (SC-006)
- [ ] `make verify` green
