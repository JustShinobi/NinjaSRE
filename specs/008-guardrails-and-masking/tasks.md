# Tasks — 008 Guardrails and Masking

## Phase 1 — Corpus and goldens (test-first)

- **T001** `tests/security/test_redos_corpus.py`: adversarial inputs per detector
  with a bounded execution-time assertion (SC-003). Red.
- **T002** Span-merge golden cases: same-start overlap, contained span, chained
  overlap; pin the representative rule (SC-004). Red.
- **T003** `tests/security/test_masking_boundary.py`: intercept every outbound
  provider request during a run; assert no unmasked identifier (SC-001). Red.
- **T004** `tests/security/test_external_surface_redaction.py`: drive errors
  through HTTP and chat sinks; assert no exception detail escapes (SC-006). Red.
- **T005** Round-trip test: report with masking on, restored, equals report with
  masking off for identifier content (SC-002). Red.

## Phase 2 — Masking

- **T006** `platform/masking/policy.py`: `MaskingPolicy`, four levels, custom
  patterns (FR-007).
- **T007** `platform/masking/detectors.py`: pod, namespace, cluster, service,
  deployment, hostname, IP, cloud account ID, ARN (FR-003).
- **T008** Contextual detectors requiring a recognised preceding label (FR-004).
- **T009** Test: generic words (`frontend`, `production`) are not masked without a
  label.
- **T010** Confirm SC-003 ReDoS corpus green.
- **T011** `platform/masking/mapping.py`: stable token allocation, bidirectional
  map, sensitive flag (FR-001, FR-002, FR-008).
- **T012** Test: the same identifier receives the same token across evidence
  sources within a run.
- **T013** `platform/masking/apply.py`: `mask()` and `unmask()` (FR-006).
- **T014** `platform/masking/context.py`: run-scoped masking context.
- **T015** Custom-pattern compilation with a timeout and ReDoS validation at load.
- **T016** Token-format collision check against the evidence corpus.

## Phase 3 — Guardrail engine

- **T017** `platform/guardrails/rules.py`: `GuardrailRule`, YAML schema, loader
  (FR-010).
- **T018** Hot reload via file watcher with last-known-good retention on parse
  failure (FR-011, FR-012); confirm SC-005.
- **T019** `platform/guardrails/engine.py`: scan with `MAX_SCAN_MATCHES` and
  `MAX_SCAN_INPUT_BYTES`, truncation recorded (FR-015).
- **T020** Deterministic span merging with widest-contributing-match
  representative rule (FR-014); confirm SC-004.
- **T021** Three actions: `redact`, `block`, `audit` (FR-013).
- **T022** `platform/guardrails/audit.py`: rule, action, location — never the
  matched value for `redact`/`block` (FR-018).
- **T023** `platform/guardrails/defaults/rules.yml`: API-key shapes, private keys,
  connection strings, JWTs (FR-019).
- **T024** Test: each default rule matches its shape and does not match benign
  lookalikes.

## Phase 4 — Hook integration

- **T025** `platform/guardrails/hooks.py`: `pre_tool_use` binding returning
  `Allow`/`Deny`/`Rewrite` (FR-016).
- **T026** `block` produces a structured denial the model can reason about
  (FR-017); test the model-visible shape.
- **T027** `post_tool_use` binding redacting tool results before they become
  evidence.
- **T028** Masking applied at the LLM boundary inside the provider call path
  (feature 002 integration point).
- **T029** `local_models_exempt` resolution from the provider descriptor per call.
- **T030** Confirm SC-001 masking boundary test green.

## Phase 5 — Sink boundary

- **T031** `platform/guardrails/sinks.py`: redaction at the persistence and
  transmission boundary (FR-021).
- **T032** External-surface exception redaction: generic message or exception type
  name only (FR-020).
- **T033** Local CLI path retaining full detail; test that it is not treated as an
  external surface.
- **T034** Authorisation-aware restoration when rendering reports.
- **T035** Confirm SC-006 external-surface test green.
- **T036** Confirm SC-002 lossless restoration test green.

## Phase 6 — Policy, operations, performance

- **T037** Per-team masking policy resolution (port to feature 013; static default
  until then).
- **T038** Masking and guardrail actions surfaced in the run trace.
- **T039** Performance: single-pass scanning where patterns allow; benchmark
  against a 10MB evidence payload (SC-007).
- **T040** Ablation switches: masking on/off and guardrails on/off, registered so
  the evaluation suite can isolate their effect.
- **T041** Operator documentation: rule authoring, policy levels, the measured
  quality trade-off per level.
- **T042** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] No unmasked identifier reaches an external provider (SC-001)
- [ ] Restoration is lossless (SC-002)
- [ ] Every detector survives the ReDoS corpus (SC-003)
- [ ] Span merging deterministic against goldens (SC-004)
- [ ] Malformed ruleset retains last-known-good (SC-005)
- [ ] No exception detail on external surfaces (SC-006)
- [ ] Masking within the performance budget on 10MB (SC-007)
- [ ] Ablation switches registered for the evaluation suite
- [ ] `make verify` green
