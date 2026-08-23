# Tasks — 027 Synthetic Scenario Harness

## Phase 1 — Schemas and loader (test-first)

- **T001** `tests/harness/schemas.py`: TypedDicts for `scenario.yml`,
  `alert.json`, evidence fixtures, and `answer.yml` (FR-001, FR-002, FR-003).
- **T002** Validators producing errors naming file and field (FR-004).
- **T003** Write the malformed-fixture tests, one per fixture type (SC-003). Red.
- **T004** `tests/harness/vocabularies.py`: controlled vocabularies for failure
  modes, evidence sources, trajectory actions, root-cause categories (FR-005).
- **T005** Validate the trajectory-action vocabulary against the live capability
  catalogue, so a renamed capability is a load error.
- **T006** `tests/harness/loader.py`: scenario discovery and fixture loading.
- **T007** Scenario inheritance via `base:` with override semantics (FR-006).
- **T008** Confirm SC-003: every malformed-fixture case reports file and field.

## Phase 2 — Mock backends

- **T009** `backends/base.py`: vendor-boundary interception on the real client path
  (FR-007).
- **T010** Empty-but-valid fallback of the correct shape for unmatched calls
  (FR-008).
- **T011** Call recording for trajectory scoring (FR-010).
- **T012** `backends/recording.py`: capture live responses into fixtures, with
  secret scrubbing (FR-011).
- **T013** [P] `backends/kubernetes.py`.
- **T014** [P] `backends/aws.py` (CloudWatch, EC2, EKS, RDS, Lambda, ECS).
- **T015** [P] `backends/datadog.py`.
- **T016** [P] `backends/grafana.py` and `backends/loki.py`.
- **T017** [P] `backends/prometheus.py`.
- **T018** [P] `backends/elasticsearch.py`.
- **T019** [P] `backends/postgres.py`.
- **T020** [P] `backends/github.py`.
- **T021** Backend registration so a new integration adds a module, not a change to
  the harness (FR-009).

## Phase 3 — Runner

- **T022** `tests/harness/runner.py`: execute one scenario through the canonical
  runtime and the real pipeline (FR-012).
- **T023** Assert the runner refuses a non-canonical runtime (feature 004, FR-023).
- **T024** `tests/harness/suite.py`: run a suite or a filtered subset (FR-013).
- **T025** N attempts per scenario for variance measurement (FR-014).
- **T026** No-credential, no-network execution (FR-016); confirm SC-001.
- **T027** CLI entry point mirroring the pytest path, sharing one loader and
  executor.

## Phase 4 — Determinism and offline

- **T028** `tests/harness/determinism.py`: temperature zero, fixed seeds where
  supported, provider configuration for reproducibility (FR-015).
- **T029** Confirm SC-002: identical trajectory across two runs.
- **T030** `tests/harness/offline.py`: record a model transcript during a live run.
- **T031** Replay a recorded transcript for zero-token execution (FR-017).
- **T032** Confirm SC-006: full suite in offline mode with zero token spend.

## Phase 5 — Verdict records

- **T033** `tests/harness/artifacts.py`: JSONL record per attempt with suite,
  scenario, attempt, outcome, difficulty, failure mode, agent root cause, full
  scoring detail (FR-018).
- **T034** Enabled by environment variable, off by default (FR-020).
- **T035** Confirm SC-004: have a contributor diagnose three induced failures from
  records alone, without re-running.

## Phase 6 — Corpus

- **T036** Port Tracer's EKS scenario suite; verify each loads and runs.
- **T037** [P] Port the RDS PostgreSQL suite.
- **T038** [P] Port the Grafana suite.
- **T039** [P] Port the Hermes suites.
- **T040** [P] Port the remaining suites.
- **T041** Assign and verify difficulty levels across the corpus (FR-021).
- **T042** Verify adversarial signals are present in the evidence for every level-2
  and above scenario (FR-022).
- **T043** Per-scenario solve-rate reporting so permanently-unsolved and trivially-
  solved scenarios are visible.
- **T044** Document the fixture recording procedure.

## Phase 7 — Integration and CI

- **T045** Per-integration scenario contribution path: fixtures and an answer key
  only (FR-009); confirm SC-005 by adding one without touching harness code.
- **T046** Wire the tier-1 offline suite into the pull-request CI path.
- **T047** Wire the full suite into a scheduled CI job.
- **T048** Confirm SC-007: results reportable by difficulty level with a visible
  gradient.
- **T049** Confirm SC-008: tier-1 suite within the CI time budget.
- **T050** `make test-synthetic` target with filtering and attempt-count options.
- **T051** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Full suite runs with no credentials or cloud access (SC-001)
- [ ] Identical trajectory across runs on a deterministic configuration (SC-002)
- [ ] Malformed fixtures fail with file-and-field messages (SC-003)
- [ ] Failures diagnosable from verdict records alone (SC-004)
- [ ] New integration scenarios need only fixtures and an answer key (SC-005)
- [ ] Offline mode runs with zero token spend (SC-006)
- [ ] Results reportable by difficulty with a visible gradient (SC-007)
- [ ] Tier-1 suite within the CI time budget (SC-008)
- [ ] `make verify` green
