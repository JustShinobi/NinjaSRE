# Tasks — 010 Episodic Memory

## Phase 1 — Model and contracts (test-first)

- **T001** `platform/memory/models.py`: `Episode`, `Component`, `KeyFinding`,
  `ScoredEpisode` (FR-002, FR-004).
- **T002** Document the `resolved` semantics on the model, in the API, and in the
  UI contract (FR-003).
- **T003** `platform/memory/embeddings/port.py`: `Embedder` protocol.
- **T004** `platform/memory/policy.py`: `MemoryPolicy` with read/write ablation
  switches (FR-020).
- **T005** Write the one-episode-per-conversation test including a concurrent-turn
  race (SC-001). Red.
- **T006** Write the prompt-purity test: no episode content in the initial prompt
  (SC-002). Red.
- **T007** Write the ablation-identity test: memory disabled produces the baseline
  (SC-004). Red.
- **T008** Write the cross-team isolation test (SC-005). Red.
- **T009** Write the extraction-failure isolation test (SC-006). Red.

## Phase 2 — Embeddings

- **T010** `embeddings/local.py`: default local model, no egress.
- **T011** [P] `embeddings/provider.py`: cloud embedding providers behind the port.
- **T012** `embeddings/generations.py`: model and dimension recording per row
  (FR-018).
- **T013** Dimension-mismatch write failure — loud, not silent.
- **T014** Re-embed background generation swap with search available throughout
  (FR-019).
- **T015** Confirm SC-007: full memory function with a local embedder and no
  egress.

## Phase 3 — Extraction and effectiveness

- **T016** `platform/memory/extraction.py`: structured post-turn extraction of
  issue type, description, severity, components, key findings, resolved, root
  cause, summary (FR-005).
- **T017** Extraction token budget as a named constant.
- **T018** Failure isolation: extraction errors are logged and skipped, never
  raised into the run (FR-005); confirm SC-006.
- **T019** `platform/memory/effectiveness.py`: the documented formula with named
  weights and a stored formula version (FR-007).
- **T020** Test: the formula is monotonic in each input and bounded to [0, 1].
- **T021** Capability-sequence extraction from the tool trace (FR-014 input).
- **T022** Minimum-result-length skip with recording (FR-006).

## Phase 4 — Storage and finalisation

- **T023** `platform/memory/lifecycle.py`: `on_run_end` finalisation, exactly-once.
- **T024** Upsert by correlation id; repeat turns update (FR-001).
- **T025** Concurrency-safe upsert; confirm SC-001 under the race.
- **T026** Merge `capabilities_used` across turns without duplication.
- **T027** Guardrail filtering of episode content before persistence (FR-024).
- **T028** Org and team scoping on every write (FR-023).
- **T029** Embedding computed from issue type, description, summary, root cause
  (FR-016).

## Phase 5 — Retrieval and ranking

- **T030** `platform/memory/retrieval.py`: team-scoped vector similarity search
  (FR-012).
- **T031** `platform/memory/ranking.py`: weighted combination of similarity,
  resolved, component overlap, effectiveness, recency, with documented weights
  (FR-013).
- **T032** Golden test pinning ranking order for a fixed candidate set.
- **T033** Test: resolved, component-matching, high-effectiveness episodes
  outrank unresolved ones (acceptance scenario 6).
- **T034** Empty-result handling as a normal outcome (FR-015).
- **T035** Confirm SC-005 cross-team isolation green.

## Phase 6 — Capability and guidance

- **T036** `capabilities/tools/system/memory_search/tool.py`: typed capability with
  query, optional component and issue-type filters, full metadata,
  `side_effect_level=read` (FR-011).
- **T037** `results.py`: shape results to include findings and the capability
  sequence used (FR-014).
- **T038** `platform/memory/guidance.py`: root-prompt guidance instructing recall
  only after concrete evidence (FR-010).
- **T039** Wire guidance via `on_run_start`; confirm SC-002 prompt-purity green.
- **T040** Recall trace records: query, results, whether acted on (FR-022).

## Phase 7 — Ablation and proof

- **T041** Wire `MemoryPolicy` switches into read and write paths (FR-020).
- **T042** Confirm SC-004: memory disabled matches the pre-memory baseline within
  noise (FR-021).
- **T043** Build the repeat-scenario measurement: run a synthetic scenario, then
  run it again with memory populated; record the iteration-count delta (SC-003).
- **T044** Register memory as an ablation axis for the feature 028 harness.
- **T045** Confirm SC-008: re-embed 100k episodes with search continuously
  available.
- **T046** Operator documentation: what memory stores, what `resolved` means, how
  to ablate, how to purge.
- **T047** Episode purge and retention respecting feature 006 policies.
- **T048** Update `docs/provenance-map.md`; confirm `make check-provenance`.

## Definition of done

- [x] Exactly one episode per conversation under concurrency (SC-001)
- [x] No episode content in the initial prompt (SC-002)
- [x] Repeat-scenario iteration reduction measured and recorded (SC-003)
- [x] Memory-disabled runs match baseline (SC-004)
- [x] Cross-team retrieval impossible (SC-005)
- [x] Extraction failure never fails an investigation (SC-006)
- [x] Full function with a local embedder and no egress (SC-007)
- [~] 100k re-embed with continuous search availability (SC-008) — the
      generation-swap property (search up before, during, and after; atomic
      activation; a short generation never activated) is asserted over the memory
      re-embed path at a few hundred episodes in
      `tests/unit/platform/memory/test_embeddings.py`. The 100k *scale* half runs
      against a real PostgreSQL in `tests/contract/persistence/test_scale.py`,
      which is where an approximate index exists to be slow. Running the two
      together at 100k needs `make test-postgres` and is not covered.
- [x] `make verify` green
