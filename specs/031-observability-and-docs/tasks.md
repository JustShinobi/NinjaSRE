# Tasks — 031 Observability and Documentation

## Phase 1 — Telemetry foundation (test-first)

- **T001** Write the no-export test: default deployment observed by a network
  monitor exports nothing (SC-001). Red.
- **T002** Write the dependency-scan test: no telemetry or analytics package in the
  runtime set (SC-008). Red.
- **T003** Write the collector-outage test: export failure does not affect
  investigations (SC-003). Red.
- **T004** `platform/observability/config.py`: `TelemetryConfig`, disabled by
  default, operator-configured endpoint (FR-001, FR-002).
- **T005** `platform/observability/export.py`: OTLP export with failure isolation
  and a local drop counter (FR-004).
- **T006** Confirm SC-001 and SC-008.

## Phase 2 — Instrumentation

- **T007** `metrics/definitions.py`: all eight metric families from the plan table
  (FR-006).
- **T008** `metrics/cardinality.py`: allow-listed label sets enforced at instrument
  creation (FR-005).
- **T009** Cardinality load test with a synthetic high-cardinality workload
  (SC-004).
- **T010** `platform/observability/tracing.py`: spans for pipeline stages, loop
  iterations, capability invocations, sub-agent dispatches, storage access
  (FR-009).
- **T011** Correlation identifier propagation, including across sub-agent
  boundaries (FR-010).
- **T012** Propagation into external calls where the protocol allows.
- **T013** Confirm SC-002: all metric families and trace spans appear with a
  collector configured.

## Phase 3 — Cost and logging

- **T014** `metrics/cost.py`: attribution per run, team, and model (FR-007).
- **T015** Mid-run model-switch handling: separate per-model records summing to the
  run total; confirm SC-009.
- **T016** `platform/observability/logging.py`: `structlog` with a fixed field set
  (FR-011).
- **T017** Correlation identifier on every log line where one exists (FR-012).
- **T018** Guardrail filtering at emission (FR-013).
- **T019** Per-module log level configurable without restart (FR-014).
- **T020** Test: no module configures logging itself (feature 001 regression).

## Phase 4 — Operational visibility

- **T021** `deploy/dashboards/`: reference dashboard definitions for common
  observability stacks (FR-008).
- **T022** Cost report from the CLI, per team and per period (FR-023).
- **T023** [P] Cost report in the console.
- **T024** Integration health visible without a dashboard (FR-024).
- **T025** `platform/observability/diagnostics.py`: redacted diagnostic bundle —
  configuration without secrets, recent logs, health output, versions (FR-025).
- **T026** Test: the bundle contains no secret and no unmasked identifier.

## Phase 5 — Documentation generation

- **T027** `tools/generate_docs.py`: capability reference from metadata (FR-016).
- **T028** [P] Integration reference from the catalogue.
- **T029** [P] Configuration reference from the config schema (FR-017).
- **T030** `tools/check_docs_drift.py`: regenerate and fail on diff.
- **T031** Wire the drift check into `make verify`; confirm SC-005 by changing a
  capability without regenerating.
- **T032** Handle removed capabilities: generation drops the page and the drift
  check catches a stale reference.

## Phase 6 — Authored documentation

- **T033** Quickstart, executable end to end (FR-018).
- **T034** [P] Deployment guide: three profiles, upgrade, backup, keys, air-gapped.
- **T035** [P] Security model: credential proxy, masking, guardrails, sandbox
  profiles, approval model — each with the threat it addresses (FR-021).
- **T036** [P] Evaluation methodology, reproducible by a third party with exact
  commands and baseline references (FR-022).
- **T037** [P] Contributing guide: architecture, conventions, the seven-artefact
  integration anatomy.
- **T038** `tools/test_doc_examples.py`: extract and execute every documented code
  example (FR-020); confirm SC-007.
- **T039** `llms.txt`: machine-readable project summary.
- **T040** i18n structure so community translation of guides is possible with
  English as the normative source.

## Phase 7 — Verification

- **T041** Offline documentation build and serve (FR-019).
- **T042** New-operator quickstart validation: someone who did not write it reaches
  a successful investigation using only the quickstart (SC-006).
- **T043** Confirm SC-003 collector-outage isolation.
- **T044** Confirm SC-004 cardinality bounds under load.
- **T045** Confirm SC-009 cost attribution across a model switch.
- **T046** Documentation site published from the repository build.
- **T047** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Default deployment exports nothing (SC-001)
- [ ] All metric families and spans appear when enabled (SC-002)
- [ ] Collector outage does not affect investigations (SC-003)
- [ ] Cardinality bounded under high-cardinality load (SC-004)
- [ ] Drift check fails on stale generated docs (SC-005)
- [ ] A new operator succeeds using only the quickstart (SC-006)
- [ ] Every documented example passes its test (SC-007)
- [ ] No telemetry or analytics package in the runtime set (SC-008)
- [ ] Cost attribution correct across a model switch (SC-009)
- [ ] `make verify` green
