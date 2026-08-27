# Tasks — 011 Strategy Synthesis

## Phase 1 — Model and contracts (test-first)

- **T001** `platform/memory/strategy/models.py`: `Strategy`, `StrategyKey`,
  `OperatorEdit` with source episode ids, count, timestamp, prompt version
  (FR-005).
- **T002** `platform/memory/strategy/policy.py`: per-team ablation switch (FR-017).
- **T003** Add `MIN_EPISODES_FOR_STRATEGY`, `STRATEGY_MAX_OUTPUT_TOKENS`,
  `STRATEGY_MAX_AGE_DAYS`, `STRATEGY_MAX_INPUT_EPISODES` to
  `config/constants/investigation.py`.
- **T004** Write the anti-pattern derivation test: a fixture with three resolved
  and two unresolved episodes; assert the anti-patterns section traces to the
  unresolved ones (SC-001). Red.
- **T005** Write the cache-hit test with an LLM call counter (SC-002). Red.
- **T006** Write the invalidation test (SC-003). Red.
- **T007** Write the concurrency test: N simultaneous requests, one generation
  (SC-004). Red.
- **T008** Write the ablation-baseline test (SC-006). Red.
- **T009** Write the synthesis-failure isolation test (SC-008). Red.

## Phase 2 — Component normalisation

- **T010** `strategy/normalisation.py`: suffix stripping, environment prefix and
  suffix stripping, replica/hash segment stripping, case and separator
  normalisation (FR-012).
- **T011** Operator alias map loaded from team configuration.
- **T012** Type is always part of the key, so `service:x` never merges with
  `database:x`.
- **T013** Conservative default: unmatched variants stay distinct (FR-013).
- **T014** Fixture table asserting both merge and non-merge directions; confirm
  SC-007.

## Phase 3 — Generation

- **T015** `strategy/prompt.py`: versioned synthesis prompt with the four required
  sections (FR-002).
- **T016** Anti-patterns section explicitly sourced from unresolved and
  low-effectiveness episodes, and labelled as such (FR-003).
- **T017** `strategy/generator.py`: structured synthesis over the scored episode
  set, bounded to `STRATEGY_MAX_OUTPUT_TOKENS` (FR-004).
- **T018** Input set bounded to `STRATEGY_MAX_INPUT_EPISODES`, taking the
  top-scored.
- **T019** Threshold enforcement with the reason recorded when unmet (FR-001).
- **T020** Failure isolation: synthesis errors leave episode recall working
  (FR-006); confirm SC-008.
- **T021** Guardrail filtering before persistence (FR-019).
- **T022** Confirm SC-001 anti-pattern derivation green.

## Phase 4 — Cache and invalidation

- **T023** `strategy/cache.py`: get-or-generate keyed on
  `(org, team, issue_type, component_key)` (FR-007).
- **T024** Cache hit returns without an LLM call (FR-008); confirm SC-002.
- **T025** Advisory lock on the strategy key; contended callers wait and read the
  winner's result (FR-010); confirm SC-004.
- **T026** Age-based regeneration at `STRATEGY_MAX_AGE_DAYS` (FR-011).
- **T027** `strategy/invalidation.py`: episode-write hook invalidating matching
  keys (FR-009); confirm SC-003.
- **T028** Org and team scoping on read and write (FR-018).
- **T029** Cross-team isolation test.

## Phase 5 — Delivery

- **T030** Extend the `memory-search` capability result to include matching
  strategies alongside episodes (FR-014).
- **T031** Label strategies distinctly as synthesised playbooks, never as single
  observations.
- **T032** Include episode count and date range so the agent can weigh the
  playbook (FR-015).
- **T033** Record strategy retrieval in the run trace, including whether the agent
  acted on it.

## Phase 6 — Operator edits, ablation, proof

- **T034** `OperatorEdit` storage: operator amendments marked and preserved across
  regeneration (FR-016).
- **T035** Test: regenerate a strategy carrying an operator edit; the edit
  survives and is attributed.
- **T036** Read/write API for the console (feature 021 consumes it).
- **T037** Wire the ablation switch into generation and retrieval; confirm SC-006.
- **T038** Register strategies as an ablation axis for feature 028, independent of
  episodic memory.
- **T039** Build the value measurement: a scenario family with prior episodes, run
  with episodes only versus episodes plus strategies; record the score and
  iteration delta (SC-005).
- **T040** Operator documentation: how strategies are generated, how to edit them,
  how to disable them, how to trace a claim to its source episodes.
- **T041** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [ ] Anti-patterns traceable to unresolved episodes (SC-001)
- [ ] Cache hit performs no LLM call (SC-002)
- [ ] Episode write invalidates the matching strategy (SC-003)
- [ ] Concurrent requests produce one generation (SC-004)
- [ ] Strategy value measured against the episodes-only baseline (SC-005)
- [ ] Disabled strategies match baseline (SC-006)
- [ ] Normalisation merges and separates correctly (SC-007)
- [ ] Synthesis failure leaves recall working (SC-008)
- [ ] `make verify` green
