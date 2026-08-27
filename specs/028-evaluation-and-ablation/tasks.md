# Tasks — 028 Evaluation and Ablation

## Phase 1 — Axis scorers (test-first)

- **T001** `scoring/axes/accuracy.py`: category match with equivalents, required
  keywords, forbidden categories, forbidden keywords (FR-002).
- **T002** Fixture: correct keywords but a forbidden category → accuracy fails
  (acceptance scenario 3).
- **T003** [P] `scoring/axes/evidence.py`: required sources collected, every
  validated claim references a real entry (FR-003).
- **T004** [P] `scoring/axes/adversarial.py`: ruling-out keywords present (FR-004).
- **T005** Fixture: correct root cause, missing ruling-out keywords → adversarial
  fails, accuracy passes (acceptance scenario 4).
- **T006** [P] `scoring/axes/cost.py`: tokens and wall clock against budget
  (FR-006).
- **T007** Test: each axis fails independently for the right reason.

## Phase 2 — Trajectory matching

- **T008** `scoring/matching.py`: `strict` mode.
- **T009** [P] `lcs` mode with `max_edit_distance` (FR-008).
- **T010** [P] `set` mode.
- **T011** Parallel batches compared as unordered sets within position (FR-009).
- **T012** `scoring/axes/trajectory.py`: distance, extra actions, redundant calls
  counted separately (FR-010), loops against `max_investigation_loops` (FR-005).
- **T013** Different-valid-route handling: reported as deviation, accuracy
  unaffected (FR-011); confirm SC-009.
- **T014** Golden test pinning matching behaviour for a fixed trajectory set.

## Phase 3 — Composite and reporting

- **T015** `scoring/composite.py`: `ScenarioScore` assembling all five axes;
  passes only when every configured axis passes (FR-007).
- **T016** Partial results always reported, never collapsed; confirm SC-001.
- **T017** `scoring/report.py`: `SuiteResult` aggregating scenarios.
- **T018** Variance reported with the mean across N attempts (FR-019).
- **T019** Reporting stratified by difficulty level and by failure mode.
- **T020** Human-readable and machine-readable report output.

## Phase 4 — Ablation

- **T021** `ablation/switches.py`: documented switches for episodic memory read,
  strategy synthesis, topology, knowledge base, masking, sub-agents, seed calls,
  capability planning (FR-012).
- **T022** Wire each switch to its owning feature's ablation control.
- **T023** `ablation/config.py`: declarative, reproducible configurations (FR-016).
- **T024** Test: an ablation run is identical to baseline in every other respect,
  verified by trace comparison (FR-013); confirm SC-004.
- **T025** `ablation/runner.py`: baseline plus one run per ablation.
- **T026** `ablation/report.py`: contribution per mechanism, per axis, per
  difficulty (FR-014).
- **T027** Prominent flag when an ablation improves results (FR-015).
- **T028** Confirm SC-003: the report quantifies memory, strategy, and topology
  contributions.

## Phase 5 — Regression gating

- **T029** `regression/baseline.py`: store a suite result with corpus version,
  referenceable by identifier (FR-021).
- **T030** `regression/compare.py`: per-scenario, per-axis delta (FR-017).
- **T031** `regression/gate.py`: variance-aware tolerance policy (FR-018, FR-019).
- **T032** Separate cost gate from correctness gate (FR-020).
- **T033** Confirm SC-006: a cost regression with unchanged accuracy fails the cost
  gate only.
- **T034** Run an unchanged codebase N times; confirm the gate does not fail on
  noise (SC-005).
- **T035** Introduce a deliberate accuracy regression; confirm the gate fails
  naming scenarios and axis (SC-002).
- **T036** `regression/ci.py`: CI entry point with baseline reference.
- **T037** Wire the gate into the scheduled CI job.

## Phase 6 — Benchmarks

- **T038** `benchmarks/adapter.py`: external benchmark port (FR-022).
- **T039** `benchmarks/cloudopsbench/`: reference implementation with dataset
  loading and case adaptation.
- **T040** `benchmarks/models/`: cross-model comparison across all nine providers
  (FR-023).
- **T041** Canonical-runtime guard: benchmarking a non-canonical runtime fails
  (FR-024); confirm SC-007.
- **T042** Confirm SC-008: cross-model table covering nine providers.
- **T043** `benchmarks/export.py`: README and release-note output (FR-025).
- **T044** `make benchmark` and `make benchmark-export` targets.

## Phase 7 — Proof

- **T045** Full ablation run across the corpus at every difficulty level.
- **T046** Produce the ablation report and review it for harmful mechanisms.
- **T047** Establish and store the first release baseline.
- **T048** Publish the first quantified learning claim: memory, strategy, and
  topology contributions with variance.
- **T049** Document the evaluation methodology so the numbers are reproducible by a
  third party.
- **T050** Confirm every success criterion SC-001 through SC-009.
- **T051** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Five independent axis scores per scenario (SC-001)
- [ ] Deliberate regression fails CI with scenarios and axis named (SC-002)
- [ ] Ablation report quantifies each mechanism by axis and difficulty (SC-003)
- [ ] Ablation runs differ from baseline only in the ablated mechanism (SC-004)
- [ ] Variance-aware gating does not fail on noise (SC-005)
- [ ] Cost regression caught independently (SC-006)
- [ ] Non-canonical-runtime benchmarking fails (SC-007)
- [ ] Cross-model table across nine providers (SC-008)
- [ ] Different-route trajectories reported as deviations (SC-009)
- [ ] First quantified learning claim published
- [ ] `make verify` green
