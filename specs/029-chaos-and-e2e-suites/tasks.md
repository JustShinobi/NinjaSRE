# Tasks — 029 Chaos and End-to-End Suites

## Phase 1 — Framework (test-first)

- **T001** Write the cleanup-on-interruption test: kill the runner mid-experiment,
  assert no fault remains active (SC-002). Red.
- **T002** Write the skip-without-infrastructure test (SC-007). Red.
- **T003** `chaos/framework/preflight.py`: cluster health check before injection
  (FR-007).
- **T004** `chaos/framework/injector.py`: Chaos Mesh manifest application (FR-003).
- **T005** `chaos/framework/validity.py`: probe confirming the fault produced its
  expected symptom (FR-006).
- **T006** `chaos/framework/cleanup.py`: deferred teardown on success, failure, and
  interruption; verify return to baseline (FR-005); confirm SC-002.
- **T007** `chaos/framework/lock.py`: cluster-level concurrency lock (FR-020).
- **T008** `chaos/runner.py`: inject, alert, investigate, score, clean up.
- **T009** Alert generation from the injected fault so the real pipeline entry
  point is exercised (FR-004).

## Phase 2 — Chaos experiments

Each: `chaos.yaml`, `alert.json`, `expected.yml` with a validity probe.

- **T010** [P] pod-kill. **T011** [P] container-kill. **T012** [P] cpu-stress.
- **T013** [P] memory-stress. **T014** [P] io-latency. **T015** [P] network-delay.
- **T016** [P] network-partition. **T017** [P] network-corrupt.
- **T018** [P] bandwidth-limit. **T019** [P] dns-error. **T020** [P] dns-random.
- **T021** [P] http-abort. **T022** [P] http-delay.
- **T023** [P] http-response-fault.
- **T024** Confirm SC-001: all fourteen inject, alert, investigate, score, clean
  up.

## Phase 3 — otel-demo

- **T025** `e2e/otel_demo/install.py`: demo application plus its observability
  stack (FR-008).
- **T026** [P] Fault: cart service failure.
- **T027** [P] Fault: product catalogue failure.
- **T028** [P] Fault: recommendation cache failure.
- **T029** [P] Fault: ad service failure.
- **T030** [P] Fault: payment failure.
- **T031** Expected root cause per fault for scoring (FR-011).
- **T032** `e2e/otel_demo/runner.py`: enable fault, trigger investigation, score,
  disable.
- **T033** Investigations use the real observability integrations against the
  demo's live telemetry (FR-010).
- **T034** Confirm SC-003: all five faults investigable end to end.

## Phase 4 — Cloud e2e

- **T035** `e2e/cloud/provisioning/`: declarative infrastructure with run-identifier
  tagging (FR-013).
- **T036** [P] Scenario: EKS.
- **T037** [P] Scenario: EC2.
- **T038** [P] Scenario: CloudWatch.
- **T039** [P] Scenario: Lambda.
- **T040** [P] Scenario: ECS.
- **T041** [P] Scenario: RDS.
- **T042** Teardown on success, failure, and interruption.
- **T043** `e2e/cloud/reaper.py`: tag-sweep orphan cleanup independent of any run
  (FR-014).
- **T044** `e2e/cloud/cost.py`: declared per-run bound with actual reported
  (FR-015).
- **T045** Confirm SC-004 with a tag sweep after a deliberately-interrupted run.
- **T046** Confirm SC-008: cost within declared bounds.

## Phase 5 — Scoring integration

- **T047** Apply feature 028's five axes to chaos and e2e runs (FR-016).
- **T048** Validity gating: an invalid experiment is reported, not scored as an
  agent failure; confirm SC-005.
- **T049** Cross-release comparability of real-run results (FR-018).
- **T050** Report distinguishing agent failures from experiment failures.

## Phase 6 — Capture procedure

- **T051** `e2e/capture.py`: extract telemetry from a run trace.
- **T052** Identifier scrubbing before any fixture is written (FR-022).
- **T053** Generate scenario fixtures and a draft answer key.
- **T054** Confirm SC-006: convert a real miss into a synthetic scenario that
  reproduces it.
- **T055** Document the capture procedure end to end (FR-017).

## Phase 7 — Operability

- **T056** One-command setup for Kind and for EKS (FR-021).
- **T057** One-command teardown for both.
- **T058** Clean skip with a clear message when no cluster is available (FR-019);
  confirm SC-007.
- **T059** `make chaos-*` and `make e2e-*` targets.
- **T060** Wire chaos and e2e into the scheduled and pre-release CI paths.
- **T061** Operator and contributor documentation for both suites.
- **T062** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

See `deviations.md` §1 for what "proven" means for a suite that needs
infrastructure `make verify` cannot create, and §7 for the one item that is
partial.

- [x] All fourteen chaos experiments complete the full cycle (SC-001)
- [x] Interruption leaves no active fault (SC-002)
- [x] All five otel-demo faults investigable (SC-003)
- [x] No leaked cloud resources after a tag sweep (SC-004)
- [x] Invalid experiments reported, not scored as agent failures (SC-005)
- [x] A real miss converted into a reproducing synthetic scenario (SC-006)
- [x] Suites skip cleanly without infrastructure (SC-007)
- [x] Cloud runs within declared cost bounds (SC-008)
- [x] `make verify` green — 8803 passed, 20 skipped

Not done, with reasons recorded:

- [ ] T062 `docs/provenance-map.md` / `make check-provenance` — deviations §8:
      the file is gitignored and the target does not exist.
- [ ] The six declarative cloud modules — deviations §7: everything the success
      criteria assert about provisioning, teardown, reaping, and cost is
      complete; the modules themselves need an account to be worth writing.
